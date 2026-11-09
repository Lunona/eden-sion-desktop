from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import queue
import sqlite3
import threading
import time
import uuid

from .types import (MemoryError, Scope, canonical_text, cosine, dumps, fingerprint, normalized, now,
                    require, string, terms, timestamp, vector)

LAYERS = {"canon", "realworld", "shared_experience", "story_branch"}
KINDS = {"preference", "episode", "relationship", "plan", "observation", "temporary", "note"}
ROLES = {"user", "assistant", "document", "host"}
SINGLE_PREDICATES = {"preferred_name", "drink_sweetness", "reply_length", "project_status",
                     "occupation", "plan_status", "current_drink", "proactive_focus", "affinity"}


class MemoryService:
    """One local writer, SQLite transactions, and source-backed revisions.

    The host supplies Scope. The JSONL transport is a trusted local-process API;
    it is not an authentication boundary for untrusted network clients.
    """

    def __init__(self, database: str | Path, *, extractor=None, embedder=None,
                 token_counter=None, semantic_threshold: float = 0.45,
                 retrieval_timeout: float = 0.8):
        self.path = Path(database).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.worker = None
        self.extractor = extractor
        self.embedder = embedder
        self.token_counter = token_counter
        self.semantic_threshold = semantic_threshold
        self.retrieval_timeout = retrieval_timeout
        self.remote_slots = threading.BoundedSemaphore(2)
        self.closed = False
        self.recovery_failed = False
        self._file_lock = self.path.with_suffix(self.path.suffix + ".lock").open("a+b")
        try:
            self._file_lock.seek(0)
            if os.name == "nt":
                import msvcrt
                if self._file_lock.read(1) == b"":
                    self._file_lock.write(b"0")
                    self._file_lock.flush()
                self._file_lock.seek(0)
                msvcrt.locking(self._file_lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._file_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._file_lock.close()
            raise MemoryError("already_running", "该数据库已有组件进程，请使用同一进程接口") from None
        try:
            self.key_path = self.path.with_suffix(self.path.suffix + ".deletion.key")
            self.journal_path = self.path.with_suffix(self.path.suffix + ".deletions.jsonl")
            if not self.key_path.exists():
                require(not self.journal_path.exists(), "missing_deletion_key", "删除清单的校验密钥缺失")
                with self.key_path.open("xb") as f:
                    f.write(os.urandom(32))
                    f.flush()
                    os.fsync(f.fileno())
            self.secret = self.key_path.read_bytes()
            require(len(self.secret) == 32, "invalid_deletion_key", "删除清单校验密钥无效")
            self.db = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False, timeout=10)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA secure_delete=ON")
            self.db.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
            require(self.db.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()[0] == "1",
                    "schema_version", "数据库版本不兼容")
            key_id = hashlib.sha256(self.secret).hexdigest()
            stored_key = self.db.execute("SELECT value FROM settings WHERE key='deletion_key_id'").fetchone()
            require(not stored_key or stored_key[0] == key_id, "missing_deletion_key", "数据库须与对应删除清单及校验密钥一起保存")
            self.db.execute("INSERT OR IGNORE INTO settings VALUES('deletion_key_id',?)", (key_id,))
            require(self.journal_path.exists() or not self.db.execute("SELECT 1 FROM replayed_deletions LIMIT 1").fetchone(),
                    "missing_deletion_log", "当前数据库的删除清单缺失")
            with self._tx():
                self.db.execute("UPDATE jobs SET status='pending' WHERE status='running'")
                self._replay_deletions()
        except BaseException:
            if hasattr(self, "db"):
                self.db.close()
            self._file_lock.close()
            raise

    @contextmanager
    def _tx(self):
        with self.lock:
            require(not self.closed, "closed", "组件已关闭")
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def close(self):
        self.stop.set()
        if self.worker and self.worker is not threading.current_thread():
            self.worker.join(timeout=5)
        with self.lock:
            if not self.closed:
                self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self.db.close()
                self.closed = True
                self._file_lock.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _scope(self, value, world=None) -> Scope:
        require(not self.recovery_failed, "recovery_failed", "恢复未完成，请先修复备份或删除清单")
        scope = Scope.parse(value)
        with self.lock:
            profile = self.db.execute("SELECT profile FROM identities WHERE owner=? AND pet=?",
                                      (scope.owner_id, scope.companion_id)).fetchone()
            if profile:
                allowed = set(json.loads(profile[0])["visible_world_ids"])
                require(set(scope.visible_world_ids) <= allowed, "world_forbidden", "请求超出角色的可读世界范围")
        if world is not None:
            require(world in scope.visible_world_ids, "world_forbidden", "该世界不在请求范围内")
        return scope

    def _ensure_scope(self, s):
        self.db.execute("INSERT OR IGNORE INTO scopes(owner,pet) VALUES(?,?)", (s.owner_id, s.companion_id))

    def _bump(self, s, generation=False):
        self._ensure_scope(s)
        self.db.execute("UPDATE scopes SET version=version+1,generation=generation+? WHERE owner=? AND pet=?",
                        (int(generation), s.owner_id, s.companion_id))

    def _state(self, s):
        row = self.db.execute("SELECT version,generation FROM scopes WHERE owner=? AND pet=?",
                              (s.owner_id, s.companion_id)).fetchone()
        return tuple(row) if row else (0, 0)

    def _digest(self, text):
        return hmac.new(self.secret, canonical_text(text).encode("utf-8"), hashlib.sha256).hexdigest()

    def _operation(self, s, request_id, operation, payload):
        if request_id is None:
            return None
        string(request_id, "request_id", 128)
        row = self.db.execute("SELECT * FROM operations WHERE owner=? AND pet=? AND key=?",
                              (s.owner_id, s.companion_id, request_id)).fetchone()
        if not row:
            return None
        require(row["operation"] == operation and row["fingerprint"] == hashlib.sha256(dumps(payload).encode()).hexdigest(),
                "idempotency_conflict", "同一请求 ID 被用于不同内容")
        result = json.loads(row["result"])
        mid = result.get("memory_id")
        if mid:
            require(not self.db.execute("SELECT 1 FROM deleted WHERE owner=? AND pet=? AND id=?",
                                       (s.owner_id, s.companion_id, mid)).fetchone(),
                    "deleted", "此请求对应的记忆已经清除")
        return result

    def _save_operation(self, s, request_id, operation, payload, result):
        if request_id is not None:
            self.db.execute("INSERT INTO operations VALUES(?,?,?,?,?,?)",
                            (s.owner_id, s.companion_id, request_id, operation,
                             hashlib.sha256(dumps(payload).encode()).hexdigest(), dumps(result)))
        return result

    def set_identity(self, scope, profile: dict, *, expected_revision: int | None = None):
        s = Scope.parse(scope)
        require(isinstance(profile, dict), "invalid_identity", "角色身份必须是对象")
        allowed_fields = {"name", "origin", "self_description", "canon_entity_id", "knows_origin",
                          "visible_world_ids", "story_progress"}
        require(not (set(profile) - allowed_fields), "invalid_identity", "角色身份包含未知字段")
        p = dict(profile)
        p["name"] = string(p.get("name"), "name", 128)
        p["origin"] = string(p.get("origin", "未指定作品"), "origin", 256)
        p["self_description"] = string(p.get("self_description", ""), "self_description", 1500, True)
        p["canon_entity_id"] = string(p.get("canon_entity_id", s.companion_id), "canon_entity_id", 128)
        require(isinstance(p.get("knows_origin", True), bool), "invalid_identity", "knows_origin 必须是布尔值")
        p["knows_origin"] = p.get("knows_origin", True)
        worlds = p.get("visible_world_ids", list(s.visible_world_ids))
        p["visible_world_ids"] = list(Scope(s.owner_id, s.companion_id, worlds).visible_world_ids)
        require(set(s.visible_world_ids) <= set(p["visible_world_ids"]), "invalid_identity", "身份不包含当前请求世界")
        p["story_progress"] = p.get("story_progress", {})
        require(isinstance(p["story_progress"], dict) and all(
            k in p["visible_world_ids"] and isinstance(v, int) and not isinstance(v, bool) and v >= 0
            for k, v in p["story_progress"].items()), "invalid_identity", "剧情进度应是世界 ID 到非负章节数的映射")
        with self._tx():
            row = self.db.execute("SELECT revision FROM identities WHERE owner=? AND pet=?",
                                  (s.owner_id, s.companion_id)).fetchone()
            revision = row[0] if row else 0
            require(expected_revision == revision or (not row and expected_revision is None),
                    "revision_conflict", "角色身份版本已变化")
            self.db.execute("INSERT OR REPLACE INTO identities VALUES(?,?,?,?)",
                            (s.owner_id, s.companion_id, dumps(p), revision + 1))
            self._bump(s, True)
        return {"status": "committed", "revision": revision + 1}

    def identity(self, scope):
        s = self._scope(scope)
        with self.lock:
            row = self.db.execute("SELECT profile,revision FROM identities WHERE owner=? AND pet=?",
                                  (s.owner_id, s.companion_id)).fetchone()
            return {"profile": json.loads(row[0]), "revision": row[1]} if row else {"profile": None, "revision": 0}

    def add_alias(self, scope, entity: str, alias: str, world_id="real"):
        s = self._scope(scope, world_id)
        entity, alias = string(entity, "entity", 128), string(alias, "alias", 128)
        with self._tx():
            self.db.execute("INSERT OR IGNORE INTO aliases VALUES(?,?,?,?,?)",
                            (s.owner_id, s.companion_id, world_id, entity, alias))
            self._bump(s)
        return {"status": "committed"}

    def _event(self, s, event_id, text, role, world, layer, occurred_at, excluded=False, allow_relearn=False):
        require(role in ROLES and layer in LAYERS, "invalid_input", "事件角色或知识来源无效")
        self._scope(s, world)
        event_id = string(event_id, "event_id", 128)
        text = string(text, "text", 32000)
        date = timestamp(occurred_at)
        row = self.db.execute("SELECT * FROM events WHERE owner=? AND pet=? AND id=?",
                              (s.owner_id, s.companion_id, event_id)).fetchone()
        if row:
            require(row["text"] == text and row["world"] == world and row["layer"] == layer
                    and row["role"] == role and (occurred_at is None or row["occurred_at"] == date),
                    "event_conflict", "事件 ID 已用于其他内容，或该来源已被清除")
            return row
        require(allow_relearn or not self.db.execute("SELECT 1 FROM blocked_texts WHERE owner=? AND pet=? AND digest=?",
                                   (s.owner_id, s.companion_id, self._digest(text))).fetchone(),
                "deleted", "该内容属于已经清除的来源")
        self._ensure_scope(s)
        cursor = self.db.execute("INSERT INTO events(id,owner,pet,session,world,layer,role,text,occurred_at,recorded_at,excluded) "
                                 "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                                 (event_id, s.owner_id, s.companion_id, s.session_id, world, layer, role,
                                  text, date, now(), int(excluded)))
        return self.db.execute("SELECT * FROM events WHERE seq=?", (cursor.lastrowid,)).fetchone()

    def observe(self, scope, event_id: str, text: str, *, role="user", world_id="real",
                knowledge_layer="shared_experience", occurred_at=None, exclude_from_memory=False):
        s = self._scope(scope, world_id)
        require(isinstance(exclude_from_memory, bool), "invalid_input", "排除标记必须为布尔值")
        with self._tx():
            event = self._event(s, event_id, text, role, world_id, knowledge_layer, occurred_at, exclude_from_memory)
            if not event["excluded"] and role in {"user", "document", "host"}:
                self.db.execute("INSERT OR IGNORE INTO jobs(owner,pet,event_id,kind) VALUES(?,?,?,'extract')",
                                (s.owner_id, s.companion_id, event_id))
            return {"status": "accepted", "event_id": event_id,
                    "queued": not bool(event["excluded"]) and role != "assistant"}

    def _source(self, s, event_id, quote):
        event = self.db.execute("SELECT * FROM events WHERE owner=? AND pet=? AND id=?",
                                (s.owner_id, s.companion_id, event_id)).fetchone()
        require(event is not None and not event["excluded"], "blocked_source", "来源不存在或已排除")
        self._scope(s, event["world"])
        quote = string(quote, "quote", 16000)
        # Ambiguous repeated substrings are not silently attributed to the wrong span.
        starts = []
        start = event["text"].find(quote)
        while start >= 0:
            end = start + len(quote)
            if not any(start < b and end > a for a, b in json.loads(event["exclusions"])):
                starts.append(start)
            start = event["text"].find(quote, start + 1)
        require(bool(starts), "blocked_source", "记忆依据必须是未被撤回的来源原文")
        return event, starts[0], starts[0] + len(quote)

    def remember(self, scope, text: str, *, event_id=None, quote=None, kind="note", world_id="real",
                 knowledge_layer="shared_experience", subject="user", predicate="", value=None,
                 qualifiers=None, pinned=False, valid_from=None, event_at=None, expires_at=None,
                 role="user", parent_ids=None, request_id=None, allow_relearn=False):
        s = self._scope(scope, world_id)
        require(isinstance(allow_relearn, bool) and (not allow_relearn or (event_id is None and role == "user")),
                "invalid_relearn", "重新记住须由宿主提交新的用户明确记忆")
        payload = dict(text=text, event_id=event_id, quote=quote, kind=kind, world_id=world_id,
                       knowledge_layer=knowledge_layer, subject=subject, predicate=predicate, value=value,
                       qualifiers=qualifiers, pinned=pinned, valid_from=valid_from, event_at=event_at,
                       expires_at=expires_at, role=role, parent_ids=parent_ids, allow_relearn=allow_relearn)
        with self._tx():
            prior = self._operation(s, request_id, "remember", payload)
            if prior:
                return prior
            text = string(text, "text")
            if event_id is None:
                event_id = "manual_" + (request_id or uuid.uuid4().hex)
                self._event(s, event_id, text, role, world_id, knowledge_layer, valid_from, allow_relearn=allow_relearn)
                quote = text
            else:
                require(quote is not None, "missing_evidence", "指定来源事件时必须提供原文依据 quote")
            event, start, end = self._source(s, event_id, quote)
            require(event["world"] == world_id and event["layer"] == knowledge_layer,
                    "source_mismatch", "记忆来源与所属世界不一致")
            result = self._store(s, text, event, start, end, kind=kind, subject=subject,
                                 predicate=predicate, value=value, qualifiers=qualifiers, pinned=pinned,
                                 valid_from=valid_from, event_at=event_at, expires_at=expires_at,
                                 parent_ids=parent_ids, allow_relearn=allow_relearn)
            return self._save_operation(s, request_id, "remember", payload, result)

    def _store(self, s, text, event, start, end, *, kind="note", subject="user", predicate="", value=None,
               qualifiers=None, pinned=False, valid_from=None, event_at=None, expires_at=None,
               parent_ids=None, memory_id=None, revision=1, allow_relearn=False, review_required=False):
        text = string(text, "text")
        require(kind in KINDS, "invalid_input", "记忆类型无效")
        require(isinstance(pinned, bool), "invalid_input", "pinned 必须是布尔值")
        subject, predicate = string(subject, "subject", 128), string(predicate, "predicate", 128, True)
        qualifiers = {} if qualifiers is None else qualifiers
        require(isinstance(qualifiers, dict) and len(dumps(qualifiers)) <= 3000,
                "invalid_input", "限定条件无效或过长")
        if "chapter" in qualifiers:
            require(isinstance(qualifiers["chapter"], int) and not isinstance(qualifiers["chapter"], bool)
                    and qualifiers["chapter"] >= 0, "invalid_input", "章节必须是非负整数")
        require(len(dumps(value)) <= 3000, "invalid_input", "属性值过长")
        vf = timestamp(valid_from or event["occurred_at"])
        ea = timestamp(event_at) if event_at else None
        expiry = timestamp(expires_at) if expires_at else None
        if kind == "temporary" and expiry is None:
            expiry = (datetime.fromisoformat(vf) + timedelta(hours=24)).isoformat(timespec="microseconds")
        require(expiry is None or expiry > vf, "invalid_time", "过期时间必须晚于生效时间")
        role = event["role"]
        verification = {"user": "explicit_user", "document": "canon_source" if event["layer"] == "canon" else "document_source",
                        "host": "host_verified", "assistant": "assistant_statement"}[role]
        if role == "assistant":
            require(kind in {"episode", "note"} and not predicate,
                    "unverified_action", "桌宠回复不能作为用户事实或操作完成的依据")
            subject = "companion"
        require(not predicate or value is not None, "missing_value", "结构化事实必须提供属性值")
        require(allow_relearn or not self.db.execute("SELECT 1 FROM blocked_texts WHERE owner=? AND pet=? AND digest=?",
                                   (s.owner_id, s.companion_id, self._digest(text))).fetchone(),
                "deleted", "该记忆内容已被清除")
        fact = fingerprint(dumps([subject, predicate, qualifiers])) if predicate else ""
        if memory_id is None:
            existing = self.db.execute("SELECT * FROM memories WHERE owner=? AND pet=? AND world=? AND layer=? "
                "AND ((?=1 AND status='candidate') OR (?=0 AND status IN ('active','candidate'))) "
                "AND kind=? AND subject=? AND predicate=? AND qualifiers=? "
                "AND (expires_at IS NULL OR expires_at>?) "
                "AND ((?='assistant' AND verification='assistant_statement') OR (?<>'assistant' AND verification<>'assistant_statement')) "
                "AND (?<>'episode' OR PRIMARY_SOURCE=?) "
                "AND (text_hash=? OR (fact_key<>'' AND fact_key=? AND value_json=?)) ORDER BY (status='active') DESC,revision DESC LIMIT 1",
                (s.owner_id, s.companion_id, event["world"], event["layer"], int(review_required), int(review_required),
                 kind, subject, predicate, dumps(qualifiers), now(),
                 role, role, kind, event["id"], fingerprint(text), fact, dumps(value))).fetchone()
            if existing:
                added = self.db.execute("INSERT OR IGNORE INTO evidence VALUES(?,?,?,?,?)",
                    (existing["rowid"], event["seq"], start, end, event["text"][start:end])).rowcount
                newly_pinned = pinned and not existing["pinned"]
                if newly_pinned:
                    self.db.execute("UPDATE memories SET pinned=1 WHERE rowid=?", (existing["rowid"],))
                if added or newly_pinned:
                    if callable(getattr(self, 'on_store', None)):
                        self.on_store(existing['rowid'],event,event['text'][start:end])
                    self._bump(s)
                return {"status": "committed" if existing["status"]=="active" else "needs_clarification",
                        "memory_id": existing["id"], "revision": existing["revision"], "duplicate": True}
        mid = memory_id or uuid.uuid4().hex
        require(not self.db.execute("SELECT 1 FROM deleted WHERE owner=? AND pet=? AND id=?",
                                   (s.owner_id, s.companion_id, mid)).fetchone(), "deleted", "该记忆 ID 已清除")
        parent_ids = parent_ids or []
        require(isinstance(parent_ids, list) and len(parent_ids) <= 16, "invalid_input", "依赖来源过多")
        for parent in parent_ids:
            require(parent != mid and parent not in self._descendants(s, [mid]),
                    "dependency_cycle", "记忆依赖不能形成循环")
            self._memory(s, parent)
        status = "candidate" if review_required else "active"
        if predicate in SINGLE_PREDICATES:
            conflict = self.db.execute("SELECT id FROM memories WHERE owner=? AND pet=? AND world=? AND layer=? "
                "AND fact_key=? AND status='active' AND (expires_at IS NULL OR expires_at>?) AND value_json<>? AND id<>? LIMIT 1",
                (s.owner_id, s.companion_id, event["world"], event["layer"], fact, now(), dumps(value), mid)).fetchone()
            if conflict:
                status = "candidate"
        cursor = self.db.execute("""INSERT INTO memories(id,revision,owner,pet,session,world,layer,kind,text,
            subject,predicate,value_json,qualifiers,fact_key,text_hash,status,verification,pinned,
            valid_from,event_at,expires_at,created_at,PRIMARY_SOURCE) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (mid, revision, s.owner_id, s.companion_id, s.session_id, event["world"], event["layer"], kind, text,
             subject, predicate, dumps(value), dumps(qualifiers), fact, fingerprint(text), status,
             verification, int(pinned), vf, ea, expiry, now(), event["id"]))
        rid = cursor.lastrowid
        self.db.execute("INSERT INTO evidence VALUES(?,?,?,?,?)", (rid, event["seq"], start, end, event["text"][start:end]))
        if callable(getattr(self, 'on_store', None)):
            self.on_store(rid,event,event['text'][start:end])
        for parent in parent_ids:
            self.db.execute("INSERT OR IGNORE INTO links VALUES(?,?,?,?)", (s.owner_id, s.companion_id, parent, mid))
        self._index(rid, text + " " + subject + " " + predicate + " " + dumps(value))
        if self.embedder and status=="active":
            self.db.execute("INSERT INTO jobs(owner,pet,memory_id,revision,kind) VALUES(?,?,?,?,'embed')",
                            (s.owner_id, s.companion_id, mid, revision))
        self._bump(s)
        return {"status": "committed" if status == "active" else "needs_clarification",
                "memory_id": mid, "revision": revision, "duplicate": False}

    def _index(self, rid, text):
        self.db.execute("DELETE FROM memory_fts WHERE rowid=?", (rid,))
        self.db.execute("INSERT INTO memory_fts(rowid,tokens) VALUES(?,?)", (rid, " ".join(terms(text))))

    def _memory(self, s, memory_id, include_archived=False):
        row = self.db.execute("SELECT * FROM memories WHERE owner=? AND pet=? AND id=? ORDER BY revision DESC LIMIT 1",
                              (s.owner_id, s.companion_id, memory_id)).fetchone()
        require(row is not None and row["status"] != "deleted" and row["world"] in s.visible_world_ids,
                "not_found", "记忆不存在或不在请求范围")
        if not include_archived:
            require(row["status"] in {"active", "candidate"}, "inactive_memory", "该记忆当前已失效")
        return row

    def document_references(self, scope, memory_ids):
        """Resolve document versions used by prior answers, including archived ones."""
        s = self._scope(scope)
        rows = {}
        with self.lock:
            def find(memory_id):
                if memory_id not in rows:
                    rows[memory_id] = self.db.execute(
                        "SELECT world,status,kind,qualifiers FROM memories WHERE owner=? AND pet=? AND id=? "
                        "ORDER BY revision DESC LIMIT 1", (s.owner_id, s.companion_id, memory_id)
                    ).fetchone()
                return rows[memory_id]

            references = {}
            for memory_id in memory_ids:
                row = find(memory_id)
                if not row or row["kind"] != "note" or row["world"] not in s.visible_world_ids:
                    continue
                qualifiers = json.loads(row["qualifiers"])
                root_id = memory_id if qualifiers.get("document_root") is True else qualifiers.get("document_id")
                if not isinstance(root_id, str):
                    continue
                root = find(root_id)
                current = bool(root and root["world"] == row["world"] and root["status"] == "active"
                               and root["kind"] == "note" and json.loads(root["qualifiers"]).get("document_root") is True
                               and row["status"] == "active")
                references[memory_id] = (root_id, current)
            return references

    def _exclude_evidence(self, rid):
        for e in self.db.execute("SELECT * FROM evidence WHERE memory_row=?", (rid,)).fetchall():
            row = self.db.execute("SELECT exclusions FROM events WHERE seq=?", (e["event_seq"],)).fetchone()
            spans = json.loads(row[0])
            if [e["start"], e["end"]] not in spans:
                spans.append([e["start"], e["end"]])
                self.db.execute("UPDATE events SET exclusions=? WHERE seq=?", (dumps(spans), e["event_seq"]))

    def _current_evidence(self, rid):
        for row in self.db.execute("""SELECT e.*,v.start AS evidence_start,v.end AS evidence_end,v.quote
                FROM evidence v JOIN events e ON e.seq=v.event_seq
                WHERE v.memory_row=? AND e.excluded=0 ORDER BY e.seq""",(rid,)):
            start, end = row["evidence_start"], row["evidence_end"]
            if row["text"][start:end] == row["quote"] and not any(
                    start < b and end > a for a, b in json.loads(row["exclusions"])):
                return row, start, end
        return None

    def _descendants(self, s, roots):
        seen, pending = set(roots), list(roots)
        while pending:
            parent = pending.pop()
            for row in self.db.execute("SELECT child_id FROM links WHERE owner=? AND pet=? AND parent_id=?",
                                       (s.owner_id, s.companion_id, parent)):
                if row[0] not in seen:
                    seen.add(row[0])
                    pending.append(row[0])
        return seen

    def correct(self, scope, memory_id: str, text: str, *, expected_revision: int,
                mode="change", effective_at=None, value=None, request_id=None, source_candidate=None):
        s = self._scope(scope)
        require(mode in {"change", "retract"}, "invalid_input", "纠错模式必须是 change 或 retract")
        text = string(text, "text")
        date = timestamp(effective_at)
        payload = dict(memory_id=memory_id, text=text, expected_revision=expected_revision,
                       mode=mode, effective_at=effective_at, value=value)
        if source_candidate is not None:
            payload["source_candidate"] = list(source_candidate)
        with self._tx():
            prior = self._operation(s, request_id, "correct", payload)
            if prior:
                return prior
            old = self._memory(s, memory_id)
            require(old["revision"] == expected_revision, "revision_conflict", "记忆版本已变化，请重新读取")
            require(date >= old["valid_from"], "invalid_time", "变更时间早于原版本，请使用合适的纠错时间")
            evidence = None
            if source_candidate is not None:
                candidate_id, candidate_revision = source_candidate
                candidate = self._memory(s, candidate_id)
                require(old["status"] == "active" and candidate["revision"] == candidate_revision and candidate["status"] == "candidate"
                        and candidate["fact_key"] and candidate["fact_key"] == old["fact_key"]
                        and candidate["world"] == old["world"] and candidate["layer"] == old["layer"]
                        and candidate["text"] == text and json.loads(candidate["value_json"]) == value
                        and (candidate["expires_at"] is None or candidate["expires_at"] > date),
                        "revision_conflict", "待确认记忆已变化，请重新读取")
                evidence = self._current_evidence(candidate["rowid"])
                require(evidence is not None, "evidence_required", "待确认记忆的依据已失效")
            self._exclude_evidence(old["rowid"])
            self.db.execute("UPDATE memories SET status=?,valid_to=? WHERE rowid=?",
                            ("superseded" if mode == "change" else "retracted", date, old["rowid"]))
            invalidated = self._descendants(s, [memory_id]) - {memory_id}
            for child in invalidated:
                rows = self.db.execute("SELECT rowid FROM memories WHERE owner=? AND pet=? AND id=? AND status='active'",
                                       (s.owner_id, s.companion_id, child)).fetchall()
                for row in rows:
                    self._exclude_evidence(row[0])
                self.db.execute("UPDATE memories SET status='retracted' WHERE owner=? AND pet=? AND id=? AND status='active'",
                                (s.owner_id, s.companion_id, child))
            if evidence is None:
                ev = self._event(s, "correction_" + (request_id or uuid.uuid4().hex), text, "user",
                                 old["world"], old["layer"], date)
                start, end = 0, len(text)
            else:
                ev, start, end = evidence
                self.db.execute("UPDATE memories SET status='retracted',valid_to=? WHERE rowid=?",
                                (date, candidate["rowid"]))
            expiry = candidate["expires_at"] if evidence is not None else old["expires_at"]
            result = self._store(s, text, ev, start, end, kind=old["kind"], subject=old["subject"],
                predicate=old["predicate"], value=value if value is not None else json.loads(old["value_json"]),
                qualifiers=json.loads(old["qualifiers"]), pinned=bool(old["pinned"]), valid_from=date,
                event_at=old["event_at"], expires_at=expiry, memory_id=memory_id, revision=expected_revision + 1)
            self._bump(s, True)
            result["invalidated_memory_ids"] = sorted(invalidated)
            return self._save_operation(s, request_id, "correct", payload, result)

    def _public(self, row):
        return {"memory_id": row["id"], "revision": row["revision"], "kind": row["kind"], "text": row["text"],
                "world_id": row["world"], "knowledge_layer": row["layer"], "subject": row["subject"],
                "predicate": row["predicate"], "value": json.loads(row["value_json"]),
                "qualifiers": json.loads(row["qualifiers"]), "status": row["status"],
                "verification": row["verification"], "pinned": bool(row["pinned"]),
                "valid_from": row["valid_from"], "valid_to": row["valid_to"], "event_at": row["event_at"],
                "expires_at": row["expires_at"], "created_at": row["created_at"]}

    def inspect(self, scope, *, memory_id=None, status="active", limit=50, offset=0):
        s = self._scope(scope)
        require(isinstance(limit, int) and 1 <= limit <= 500 and isinstance(offset, int) and offset >= 0,
                "invalid_input", "分页范围无效")
        require(status in {"active", "all", "candidate", "archived", "superseded", "retracted"},
                "invalid_input", "状态无效")
        with self.lock:
            marks = ",".join("?" for _ in s.visible_world_ids)
            args = [s.owner_id, s.companion_id, *s.visible_world_ids]
            where = f"owner=? AND pet=? AND world IN ({marks}) AND status<>'deleted'"
            if memory_id is not None:
                where += " AND id=?"
                args.append(memory_id)
            if status != "all":
                where += " AND status=?"
                args.append(status)
            rows = self.db.execute(f"SELECT * FROM memories WHERE {where} ORDER BY created_at DESC,revision DESC LIMIT ? OFFSET ?",
                                   [*args, limit, offset]).fetchall()
            items = []
            for row in rows:
                item = self._public(row)
                item["evidence"] = [dict(e) for e in self.db.execute("SELECT e.id AS event_id,v.start,v.end,v.quote "
                    "FROM evidence v JOIN events e ON e.seq=v.event_seq WHERE v.memory_row=?", (row["rowid"],))]
                items.append(item)
            return {"items": items, "version": self._state(s)[0], "offset": offset}

    def _visible_rows(self, s, as_of=None, layers=None):
        date = timestamp(as_of)
        marks = ",".join("?" for _ in s.visible_world_ids)
        args = [s.owner_id, s.companion_id, *s.visible_world_ids, date, date, date]
        status = "status IN ('active','superseded')" if as_of else "status='active'"
        query = f"SELECT * FROM memories WHERE owner=? AND pet=? AND world IN ({marks}) AND {status} "
        query += "AND valid_from<=? AND (valid_to IS NULL OR valid_to>?) AND (expires_at IS NULL OR expires_at>?)"
        rows = self.db.execute(query, args).fetchall()
        profile = self.identity(s)["profile"]
        progress = profile.get("story_progress", {}) if profile else {}
        if layers is not None:
            rows = [r for r in rows if r["layer"] in layers]
        if progress:
            rows = [r for r in rows if r["world"] not in progress or
                    json.loads(r["qualifiers"]).get("chapter", 0) <= progress[r["world"]]]
        # Derived observations require all parents to be available in the same read scope.
        links = list(self.db.execute("SELECT parent_id,child_id FROM links WHERE owner=? AND pet=?",
                                     (s.owner_id, s.companion_id)))
        if not links:
            return rows
        while True:
            ids = {r["id"] for r in rows}
            blocked = {r[1] for r in links if r[0] not in ids}
            filtered = [r for r in rows if r["id"] not in blocked]
            if len(filtered) == len(rows):
                return rows
            rows = filtered

    def _bounded(self, fn):
        require(self.remote_slots.acquire(blocking=False), "provider_busy", "检索服务忙")
        results = queue.Queue(maxsize=1)
        def run():
            try:
                results.put((True, fn()))
            except Exception as exc:
                results.put((False, exc))
            finally:
                self.remote_slots.release()
        threading.Thread(target=run, daemon=True).start()
        try:
            ok, value = results.get(timeout=self.retrieval_timeout)
        except queue.Empty:
            raise MemoryError("provider_timeout", "检索服务超过本轮等待预算") from None
        if not ok:
            raise MemoryError("provider_error", "检索服务暂时不可用") from None
        return value

    def has_indexed_vectors(self, scope, model_id, *, historical=False):
        s = self._scope(scope)
        marks = ",".join("?" for _ in s.visible_world_ids)
        statuses = "('active','superseded')" if historical else "('active')"
        with self.lock:
            return self.db.execute(f"""SELECT 1 FROM memories m JOIN vectors v ON v.memory_row=m.rowid
                WHERE v.model=? AND m.owner=? AND m.pet=? AND m.world IN ({marks}) AND m.status IN {statuses} LIMIT 1""",
                (model_id, s.owner_id, s.companion_id, *s.visible_world_ids)).fetchone() is not None

    def _context_item(self, row, item):
        sources = [r[0] for r in self.db.execute(
            "SELECT DISTINCT e.id FROM evidence v JOIN events e ON e.seq=v.event_seq WHERE v.memory_row=?",
            (row["rowid"],))]
        item["source_event_ids"] = sources
        keys = ("memory_id", "revision", "text", "world_id", "knowledge_layer", "valid_from",
                "valid_to", "event_at", "verification", "expires_at", "source_event_ids")
        return {key: item[key] for key in keys}

    def recall(self, scope, query: str, *, top_k=8, token_budget=1200, as_of=None,
               knowledge_layers=None, time_from=None, time_to=None, current_event_id=None,
               include_reading_interpretations=False):
        s = self._scope(scope)
        query = string(query, "query", 4000)
        require(isinstance(top_k, int) and 1 <= top_k <= 30 and isinstance(token_budget, int)
                and 0 <= token_budget <= 32000, "invalid_input", "召回预算无效")
        if knowledge_layers is not None:
            require(isinstance(knowledge_layers, list) and set(knowledge_layers) <= LAYERS,
                    "invalid_input", "知识来源过滤无效")
        lower, upper = timestamp(time_from) if time_from else None, timestamp(time_to) if time_to else None
        require(not lower or not upper or lower <= upper, "invalid_time", "时间范围起止颠倒")
        degraded = []
        qvec = None
        semantic_deadline = time.monotonic() + self.retrieval_timeout
        embedder = self.embedder
        query_encoder = getattr(embedder, "embed_query", None)
        if embedder and (not query_encoder or self.has_indexed_vectors(s, embedder.model_id, historical=bool(as_of))):
            try:
                embed_query = query_encoder or embedder.embed
                qvec = vector(self._bounded(lambda: embed_query(query)))
            except Exception:
                degraded.append("semantic")
        with self.lock:
            # Hold the lock from scope revalidation through context construction.
            self._scope(s)
            rows = self._visible_rows(s, as_of, knowledge_layers)
            if not include_reading_interpretations:
                rows = [row for row in rows if json.loads(row["qualifiers"]).get("reading_note") != "interpretation"]
            current_claims = []
            if current_event_id is not None:
                from .extraction import RuleExtractor
                event = self.db.execute("SELECT * FROM events WHERE owner=? AND pet=? AND id=? AND session=?",
                    (s.owner_id, s.companion_id, current_event_id, s.session_id)).fetchone()
                require(event is not None and event["world"] in s.visible_world_ids, "not_found", "当前事件不在请求范围")
                if event["role"] == "user" and not event["excluded"] and not json.loads(event["exclusions"]):
                    for candidate in RuleExtractor().extract(dict(event)):
                        if candidate.get("predicate") in SINGLE_PREDICATES:
                            key = fingerprint(dumps([candidate.get("subject", "user"), candidate["predicate"], candidate.get("qualifiers", {})]))
                            rows = [r for r in rows if not (r["world"] == event["world"] and r["fact_key"] == key
                                    and r["value_json"] != dumps(candidate["value"]))]
                            current_claims.append({"text": candidate["quote"], "event_id": event["id"], "status": "current_user_statement"})
            if lower or upper:
                rows = [r for r in rows if (not lower or (r["event_at"] or r["valid_from"]) >= lower)
                        and (not upper or (r["event_at"] or r["valid_from"]) <= upper)]
            by_id = {r["rowid"]: r for r in rows}
            channels = []
            qt = terms(query)
            if qt and by_id:
                match = " OR ".join('"' + t.replace('"', '""') + '"' for t in qt)
                # Scope/validity filtering occurs BEFORE each route's LIMIT.
                marks = ",".join("?" for _ in by_id)
                found = self.db.execute(f"SELECT rowid,bm25(memory_fts) AS score FROM memory_fts "
                    f"WHERE memory_fts MATCH ? AND rowid IN ({marks}) ORDER BY score LIMIT 30", [match, *by_id]).fetchall()
                channels.append(("keyword", [r[0] for r in found]))
            # Substrings cover one- and two-character names independently of FTS.
            nq = normalized(query)
            alias_entities = set()
            for alias in self.db.execute("SELECT * FROM aliases WHERE owner=? AND pet=?",
                                         (s.owner_id, s.companion_id)):
                if alias["world"] in s.visible_world_ids and normalized(alias["alias"]) in nq:
                    alias_entities.add(alias["entity"])
            exact = []
            if by_id:
                marks = ",".join("?" for _ in by_id)
                exact = [r[0] for r in self.db.execute(f"SELECT rowid FROM memories WHERE instr(lower(text),?)>0 "
                    f"AND rowid IN ({marks}) ORDER BY valid_from DESC LIMIT 30", [query.casefold(), *by_id])]
            exact.extend(r["rowid"] for r in rows if r["subject"] in alias_entities and r["rowid"] not in exact)
            if exact:
                channels.append(("entity_or_exact", exact[:30]))
            if qvec is not None:
                candidates = []
                model = embedder.model_id
                marks = ",".join("?" for _ in by_id)
                cursor = self.db.execute(f"SELECT memory_row,vector FROM vectors WHERE model=? AND memory_row IN ({marks})",
                                         [model, *by_id]) if by_id else []
                if hasattr(embedder, "rank_stored"):
                    candidates, partial = embedder.rank_stored(qvec, cursor, self.semantic_threshold, semantic_deadline)
                    if partial:degraded.append("semantic_budget")
                else:
                    for rid, stored in cursor:
                        if time.monotonic() > semantic_deadline:
                            degraded.append("semantic_budget")
                            break
                        if stored:
                            score = cosine(qvec, json.loads(stored))
                            if score >= self.semantic_threshold:
                                candidates.append((score, rid))
                candidates.sort(reverse=True)
                channels.append(("semantic", [rid for _, rid in candidates[:30]]))
            if lower or upper:
                channels.append(("time", [r["rowid"] for r in sorted(rows, key=lambda r: r["event_at"] or r["valid_from"], reverse=True)[:30]]))
            scores, reasons = {}, {}
            for name, ids in channels:
                for rank, rid in enumerate(ids, 1):
                    scores[rid] = scores.get(rid, 0) + 1 / (60 + rank)
                    reasons.setdefault(rid, []).append(name)
            ranked = sorted(scores, key=lambda rid: (scores[rid] + 0.002 * by_id[rid]["pinned"], by_id[rid]["valid_from"]), reverse=True)
            if callable(getattr(self, 'rank_extension', None)):
                try:
                    proposed=self.rank_extension(s,query,rows,scores,reasons)
                    require(isinstance(proposed,list) and len(proposed)==len(set(proposed)) and all(rid in by_id and rid in scores for rid in proposed),'invalid_ranking','关联检索返回无效候选')
                    ranked=proposed
                except Exception:
                    degraded.append('associative_index')
            identity = self.identity(s)
            profile = identity["profile"]
            brief = ({"name": profile["name"], "origin": profile["origin"],
                      "knows_origin": profile["knows_origin"], "self_description": profile["self_description"]}
                     if profile else None)
            context = {"identity": brief, "current_turn": current_claims, "memories": []}
            counter = self.token_counter or (lambda t: len(t.encode("utf-8")))
            def count():
                value = counter(dumps(context))
                require(isinstance(value, int) and value >= 0, "invalid_token_counter", "分词器计数必须是非负整数")
                return value
            if count() > token_budget:
                context["identity"] = None
            if count() > token_budget:
                context["current_turn"] = []
            hits = []
            for rid in ranked:
                row = by_id[rid]
                if row["kind"] != "episode" and any(fingerprint(row["text"]) == fingerprint(h["text"]) and row["world"] == h["world_id"] for h in hits):
                    continue
                item = self._public(row)
                part = self._context_item(row, item)
                context["memories"].append(part)
                if count() > token_budget:
                    context["memories"].pop()
                    continue
                item.update(match_reasons=reasons[rid], score=round(scores[rid], 6))
                hits.append(item)
                self.db.execute("UPDATE memories SET access_count=access_count+1,last_accessed_at=? WHERE rowid=?", (now(), rid))
                if len(hits) >= top_k:
                    break
            rendered = dumps(context) if count() <= token_budget else ""
            used = counter(rendered) if rendered else 0
            pending = self.db.execute("SELECT count(*) FROM jobs WHERE owner=? AND pet=? AND kind='extract' AND status IN ('pending','running','failed')",
                                      (s.owner_id, s.companion_id)).fetchone()[0]
            candidates = sum(r[0] for r in self.db.execute("SELECT count(*) FROM memories WHERE owner=? AND pet=? AND status='candidate' AND world IN (" +
                ",".join("?" for _ in s.visible_world_ids) + ")", [s.owner_id, s.companion_id, *s.visible_world_ids]))
            return {"protocol": "memory.v1", "status": "ok" if hits else "no_match", "hits": hits,
                    "context": rendered, "snapshot_version": self._state(s)[0], "identity_revision": identity["revision"],
                    "pending_extraction_jobs": pending, "conflict_count": candidates, "degraded_channels": degraded,
                    "token_usage": {"used": used, "budget": token_budget, "is_estimate": self.token_counter is None,
                                    "method": "host_tokenizer" if self.token_counter else "utf8_bytes_conservative"}}

    def _deletion_entry(self, s, memory_id):
        ids = self._descendants(s, [memory_id])
        digests, spans = set(), []
        # Include other memories that depend on the very same source span.
        while True:
            extra = set()
            for mid in list(ids):
                for row in self.db.execute("SELECT * FROM memories WHERE owner=? AND pet=? AND id=?", (s.owner_id, s.companion_id, mid)).fetchall():
                    if row["text"]:
                        digests.add(self._digest(row["text"]))
                    for e in self.db.execute("SELECT v.*,e.id AS eid FROM evidence v JOIN events e ON e.seq=v.event_seq WHERE v.memory_row=?", (row["rowid"],)).fetchall():
                        spans.append({"event_id": e["eid"], "start": e["start"], "end": e["end"]})
                        digests.add(self._digest(e["quote"]))
                        event = self.db.execute("SELECT text FROM events WHERE seq=?", (e["event_seq"],)).fetchone()
                        digests.add(self._digest(event[0]))
                        for other in self.db.execute("SELECT m.id FROM evidence v JOIN memories m ON m.rowid=v.memory_row "
                            "WHERE v.event_seq=? AND v.start<? AND v.end>?", (e["event_seq"], e["end"], e["start"])):
                            extra.add(other[0])
            updated = self._descendants(s, ids | extra)
            if updated == ids:
                break
            ids = updated
        return {"id": uuid.uuid4().hex, "owner": s.owner_id, "pet": s.companion_id,
                "memory_ids": sorted(ids), "digests": sorted(digests), "spans": spans, "time": now()}

    def _write_deletion(self, entry):
        body = dumps(entry)
        signed = dumps({"entry": entry, "mac": hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()})
        with self.journal_path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(signed + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _apply_deletion(self, entry):
        if self.db.execute("SELECT 1 FROM replayed_deletions WHERE id=?", (entry["id"],)).fetchone():
            return
        owner, pet = entry["owner"], entry["pet"]
        ids = self._descendants(Scope(owner, pet), entry["memory_ids"])
        for digest in entry["digests"]:
            self.db.execute("INSERT OR IGNORE INTO blocked_texts VALUES(?,?,?)", (owner, pet, digest))
        for mid in ids:
            self.db.execute("INSERT OR IGNORE INTO deleted VALUES(?,?,?)", (owner, pet, mid))
            for row in self.db.execute("SELECT rowid FROM memories WHERE owner=? AND pet=? AND id=?", (owner, pet, mid)).fetchall():
                rid = row[0]
                self.db.execute("DELETE FROM vectors WHERE memory_row=?", (rid,))
                self.db.execute("DELETE FROM memory_fts WHERE rowid=?", (rid,))
                self.db.execute("DELETE FROM evidence WHERE memory_row=?", (rid,))
            self.db.execute("UPDATE memories SET text='',value_json='null',qualifiers='{}',subject='',predicate='',fact_key='',text_hash='',PRIMARY_SOURCE=NULL,status='deleted' "
                            "WHERE owner=? AND pet=? AND id=?", (owner, pet, mid))
            self.db.execute("UPDATE jobs SET status='cancelled',error=NULL WHERE owner=? AND pet=? AND memory_id=?", (owner, pet, mid))
        grouped = {}
        for span in entry["spans"]:
            grouped.setdefault(span["event_id"], []).append((span["start"], span["end"]))
        for eid, spans in grouped.items():
            event = self.db.execute("SELECT * FROM events WHERE owner=? AND pet=? AND id=?", (owner, pet, eid)).fetchone()
            if event:
                text = list(event["text"])
                exclusions = json.loads(event["exclusions"])
                for a, b in spans:
                    for index in range(a, min(b, len(text))):
                        text[index] = " "
                    if [a, b] not in exclusions:
                        exclusions.append([a, b])
                self.db.execute("UPDATE events SET text=?,exclusions=? WHERE seq=?", ("".join(text), dumps(exclusions), event["seq"]))
        self._bump(Scope(owner, pet), True)
        self.db.execute("INSERT INTO replayed_deletions VALUES(?)", (entry["id"],))

    def _replay_deletions(self):
        for entry in self._read_deletions():
            self._apply_deletion(entry)

    def _read_deletions(self):
        if not self.journal_path.exists():
            return []
        entries = []
        for line in self.journal_path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
                entry = record["entry"]
                expected = hmac.new(self.secret, dumps(entry).encode(), hashlib.sha256).hexdigest()
                require(hmac.compare_digest(expected, record["mac"]), "invalid_deletion_log", "删除清单校验失败")
                entries.append(entry)
            except (KeyError, ValueError, TypeError):
                raise MemoryError("invalid_deletion_log", "删除清单损坏，已停止读取以避免旧内容恢复") from None
        return entries

    def forget(self, scope, memory_id: str, *, expected_revision: int, mode="erase"):
        s = self._scope(scope)
        require(mode in {"erase", "archive"}, "invalid_input", "清除模式无效")
        with self._tx():
            row = self._memory(s, memory_id, include_archived=True)
            require(row["revision"] == expected_revision, "revision_conflict", "记忆版本已变化")
            if mode == "archive":
                self.db.execute("UPDATE memories SET status='archived' WHERE owner=? AND pet=? AND id=? AND status IN ('active','candidate')",
                                (s.owner_id, s.companion_id, memory_id))
                self._exclude_evidence(row["rowid"])
                self._bump(s, True)
                return {"status": "archived", "memory_id": memory_id}
            entry = self._deletion_entry(s, memory_id)
            # Durable ledger first: a crash before DB commit is rolled forward on restart.
            self._write_deletion(entry)
            self.recovery_failed = True
            self._apply_deletion(entry)
            result = {"status": "erased", "memory_ids": entry["memory_ids"],
                      "backup_status": "older_backups_may_contain_content_restore_replays_deletions"}
        self.recovery_failed = False
        return result

    def backup(self, destination):
        target = Path(destination).resolve()
        require(target != self.path and not target.exists(), "invalid_backup", "备份目标须是不存在的新文件")
        target.parent.mkdir(parents=True, exist_ok=True)
        with self.lock:
            with closing(sqlite3.connect(target)) as db:
                self.db.backup(db)
        return {"status": "created", "path": str(target), "deletion_ledger": "keep_current_sidecar_files"}

    def restore(self, source):
        source = Path(source).resolve()
        require(source.is_file() and source != self.path, "invalid_backup", "备份来源无效")
        with self.lock:
            # Check the non-rollbackable ledger before exposing any restored data.
            entries = self._read_deletions()
            old_versions = {(r["owner"], r["pet"]): (r["version"], r["generation"])
                            for r in self.db.execute("SELECT * FROM scopes")}
            with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as db:
                row = db.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()
                require(row and row[0] == "1", "invalid_backup", "备份格式不兼容")
                self.recovery_failed = True
                db.backup(self.db)
            with self._tx():
                for entry in entries:
                    self._apply_deletion(entry)
                restored = {(r["owner"], r["pet"]): (r["version"], r["generation"])
                            for r in self.db.execute("SELECT * FROM scopes")}
                for owner, pet in old_versions.keys() | restored.keys():
                    version = max(old_versions.get((owner, pet), (0, 0))[0], restored.get((owner, pet), (0, 0))[0]) + 1
                    generation = max(old_versions.get((owner, pet), (0, 0))[1], restored.get((owner, pet), (0, 0))[1]) + 1
                    self.db.execute("INSERT OR REPLACE INTO scopes VALUES(?,?,?,?)", (owner, pet, version, generation))
                self.db.execute("UPDATE jobs SET status='pending' WHERE status='running'")
            self.recovery_failed = False
        return {"status": "restored", "deletions_replayed": True}

    def export(self, scope):
        s = self._scope(scope)
        with self.lock:
            items = self.inspect(s, status="all", limit=500)["items"]
            total = self.db.execute("SELECT count(*) FROM memories WHERE owner=? AND pet=? AND status<>'deleted' AND world IN (" +
                ",".join("?" for _ in s.visible_world_ids) + ")", [s.owner_id, s.companion_id, *s.visible_world_ids]).fetchone()[0]
            for offset in range(500, total, 500):
                items.extend(self.inspect(s, status="all", limit=500, offset=offset)["items"])
            return {"format": "pet-memory.export.v1", "identity": self.identity(s), "memories": items,
                    "exported_at": now(), "scope": s.as_dict()}

    def import_data(self, scope, data, *, dry_run=True):
        s = self._scope(scope)
        require(isinstance(data, dict) and data.get("format") == "pet-memory.export.v1",
                "invalid_import", "导入格式无效")
        require(isinstance(data.get("memories"), list) and len(data["memories"]) <= 50000,
                "invalid_import", "导入记录无效或过多")
        require(data.get("scope", {}).get("owner_id") == s.owner_id and
                data.get("scope", {}).get("companion_id") == s.companion_id,
                "invalid_import", "导入归属不一致，需要宿主另行迁移")
        planned, blocked, seen = [], 0, set()
        with self._tx():
            for item in data["memories"]:
                require(isinstance(item, dict), "invalid_import", "导入条目必须是对象")
                mid = string(item.get("memory_id"), "memory_id", 128)
                world = item.get("world_id")
                self._scope(s, world)
                text = string(item.get("text"), "text")
                require(item.get("kind") in KINDS and item.get("knowledge_layer") in LAYERS
                        and isinstance(item.get("revision"), int) and not isinstance(item["revision"], bool) and item["revision"] >= 1
                        and isinstance(item.get("qualifiers"), dict) and isinstance(item.get("pinned"), bool),
                        "invalid_import", "导入条目的类型、版本或限定条件无效")
                string(item.get("subject"), "subject", 128)
                string(item.get("predicate"), "predicate", 128, True)
                timestamp(item.get("valid_from"))
                if item.get("event_at"):
                    timestamp(item["event_at"])
                if item.get("expires_at"):
                    timestamp(item["expires_at"])
                if mid in seen:
                    continue
                seen.add(mid)
                if self.db.execute("SELECT 1 FROM deleted WHERE owner=? AND pet=? AND id=?", (s.owner_id, s.companion_id, mid)).fetchone() or self.db.execute(
                    "SELECT 1 FROM blocked_texts WHERE owner=? AND pet=? AND digest=?", (s.owner_id, s.companion_id, self._digest(text))).fetchone():
                    blocked += 1
                    continue
                if self.db.execute("SELECT 1 FROM memories WHERE owner=? AND pet=? AND id=?", (s.owner_id, s.companion_id, mid)).fetchone():
                    continue
                # Import only current active entries; retired revisions are never promoted.
                if item.get("status") != "active":
                    continue
                if item["qualifiers"].get("reading_note") == "interpretation":
                    require(item.get("verification") == "assistant_statement" and item["kind"] == "note" and not item["predicate"],
                            "invalid_import", "读后解读的来源类型无效")
                planned.append(item)
            if not dry_run:
                for item in planned:
                    eid = "import_" + item["memory_id"]
                    role = "assistant" if item["qualifiers"].get("reading_note") == "interpretation" else "document"
                    ev = self._event(s, eid, item["text"], role, item["world_id"], item["knowledge_layer"], item["valid_from"])
                    self._store(s, item["text"], ev, 0, len(item["text"]), kind=item["kind"], subject=item["subject"],
                        predicate=item["predicate"], value=item["value"], qualifiers=item["qualifiers"], pinned=item["pinned"],
                        valid_from=item["valid_from"], event_at=item.get("event_at"), expires_at=item.get("expires_at"), memory_id=item["memory_id"],
                        revision=item["revision"])
            extension = getattr(self, 'import_extension', None)
            if callable(extension):
                extension(s, data, planned, dry_run)
            return {"status": "preview" if dry_run else "imported", "count": len(planned), "blocked": blocked,
                    "note": "仅导入当前有效条目；原始对话及身份不自动覆盖"}

    def health(self, scope):
        s = self._scope(scope)
        with self.lock:
            jobs = {r[0]: r[1] for r in self.db.execute("SELECT status,count(*) FROM jobs WHERE owner=? AND pet=? GROUP BY status", (s.owner_id, s.companion_id))}
            return {"protocol": "memory.v1", "version": "0.1.0", "status": "ok", "snapshot_version": self._state(s)[0],
                    "capabilities": {"keyword": True, "temporal": True, "multi_world": True,
                                     "automatic_extraction": "provider" if self.extractor else "conservative_rules",
                                     "semantic": bool(self.embedder), "tokenizer": bool(self.token_counter)},
                    "jobs": jobs, "worker_running": bool(self.worker and self.worker.is_alive())}

    def reindex(self, scope, *, only_missing=False):
        s = self._scope(scope)
        with self._tx():
            rows = self._visible_rows(s)
            embedder = self.embedder
            indexed, pending = set(), set()
            if only_missing and embedder:
                indexed = {row[0] for row in self.db.execute("SELECT memory_row FROM vectors WHERE model=?", (embedder.model_id,))}
                pending = {tuple(row) for row in self.db.execute("""SELECT memory_id,revision FROM jobs
                    WHERE owner=? AND pet=? AND kind='embed' AND status='pending'""", (s.owner_id, s.companion_id))}
            queued = 0
            for row in rows:
                if not only_missing:
                    self._index(row["rowid"], row["text"] + " " + row["subject"] + " " + row["predicate"] + " " + row["value_json"])
                if embedder and row["rowid"] not in indexed and (row["id"],row["revision"]) not in pending:
                    self.db.execute("INSERT INTO jobs(owner,pet,memory_id,revision,kind) VALUES(?,?,?,?,'embed')",
                                    (s.owner_id, s.companion_id, row["id"], row["revision"]))
                    queued += 1
            return {"status": "queued" if queued else "completed", "count": queued if only_missing else len(rows)}

    def jobs(self, scope, *, retry_failed=False):
        s = self._scope(scope)
        with self._tx():
            if retry_failed:
                self.db.execute("UPDATE jobs SET status='pending',attempts=0,next_at=0 WHERE owner=? AND pet=? AND status='failed'",
                                (s.owner_id, s.companion_id))
            return {"items": [dict(r) for r in self.db.execute("SELECT id,event_id,memory_id,kind,status,attempts,error FROM jobs "
                "WHERE owner=? AND pet=? ORDER BY id DESC LIMIT 100", (s.owner_id, s.companion_id))]}

    def _extract_batches(self, limit, retry_failed, ready_only):
        counts = {"completed": 0, "failed": 0, "skipped": 0, "rescheduled": 0}
        while sum(counts.values()) < limit:
            if self.stop.is_set():
                break
            with self._tx():
                statuses = "('pending','failed')" if retry_failed else "('pending')"
                pending = self.db.execute(f"SELECT j.*,e.world,e.session,e.layer,e.recorded_at FROM jobs j JOIN events e "
                    f"ON e.owner=j.owner AND e.pet=j.pet AND e.id=j.event_id WHERE j.kind='extract' AND j.status IN {statuses} "
                    "AND j.next_at<=? AND j.attempts<4 ORDER BY j.id LIMIT 1000", (time.time(),)).fetchall()
                groups = {}
                for row in pending:
                    key = (row["owner"], row["pet"], row["world"], row["session"], row["layer"])
                    groups.setdefault(key, []).append(row)
                selected = None
                for group in groups.values():
                    latest = max(datetime.fromisoformat(j["recorded_at"]).timestamp() for j in group)
                    if not ready_only or len(group) >= 6 or time.time() - latest >= max(0,min(60,getattr(self.extractor,'batch_wait_seconds',60))):
                        selected = group[:min(6, limit - sum(counts.values()))]
                        break
                if not selected:
                    break
                first = selected[0]
                s = Scope(first["owner"], first["pet"], (first["world"],), first["session"])
                generation = self._state(s)[1]
                events = []
                for job in selected:
                    self.db.execute("UPDATE jobs SET status='running',attempts=attempts+1,error=NULL WHERE id=?", (job["id"],))
                    event = dict(self.db.execute("SELECT * FROM events WHERE owner=? AND pet=? AND id=?",
                        (job["owner"], job["pet"], job["event_id"])).fetchone())
                    safe = list(event["text"])
                    for a, b in json.loads(event["exclusions"]):
                        for index in range(a, min(b, len(safe))):
                            safe[index] = " "
                    event["text"] = "".join(safe) if not event["excluded"] else ""
                    events.append(event)
            try:
                self._scope(s)
                results = self.extractor.extract_batch(events) if any(e["text"].strip() for e in events) else {e["id"]: [] for e in events}
                require(isinstance(results, dict) and set(results) == {e["id"] for e in events}, "invalid_extraction", "批量提取来源不完整")
                with self._tx():
                    self._scope(s)
                    if generation != self._state(s)[1]:
                        for job in selected:
                            self.db.execute("UPDATE jobs SET status='pending',attempts=attempts-1 WHERE id=?", (job["id"],))
                        counts["rescheduled"] += len(selected)
                        continue
                    ready = getattr(self.extractor, 'ready_to_commit', None)
                    require(not callable(ready) or ready(), 'memory_deferred', '等待当前回复完成后继续整理')
                    for event, job in zip(events, selected):
                        candidates = results[event["id"]]
                        require(isinstance(candidates, list) and len(candidates) <= 20, "invalid_extraction", "批量提取内容无效")
                        for candidate in candidates:
                            allowed={"quote", "kind", "subject"}
                            if getattr(self.extractor,'structured_rules',False):allowed|={'predicate','value','qualifiers','expires_at','review_required'}
                            require(isinstance(candidate, dict) and set(candidate) <= allowed and "quote" in candidate,
                                    "invalid_extraction", "批量提取包含未授权字段")
                            ev, a, b = self._source(s, event["id"], candidate["quote"])
                            self._store(s, candidate["quote"], ev, a, b, **{k: v for k, v in candidate.items() if k != "quote"})
                        self.db.execute("UPDATE jobs SET status='completed',error=NULL WHERE id=?", (job["id"],))
                counts["completed"] += len(selected)
            except Exception as exc:
                with self._tx():
                    if getattr(exc,'code','')=='memory_deferred':
                        for job in selected:
                            self.db.execute("UPDATE jobs SET status='pending',attempts=MAX(0,attempts-1),error=NULL,next_at=? WHERE id=?",(time.time()+2,job['id']))
                        counts['rescheduled']+=len(selected)
                        continue
                    for job in selected:
                        self.db.execute("UPDATE jobs SET status='failed',error=?,next_at=? WHERE id=?",
                            (getattr(exc, "code", type(exc).__name__), time.time() + 2 ** (job["attempts"] + 1), job["id"]))
                counts["failed"] += len(selected)
        return counts

    def process_pending(self, *, limit=20, retry_failed=False, ready_only=False):
        from .extraction import RuleExtractor
        require(isinstance(limit, int) and 1 <= limit <= 1000, "invalid_input", "任务批次数无效")
        batching = self.extractor is not None and hasattr(self.extractor, "extract_batch")
        counts = (self._extract_batches(limit, retry_failed, ready_only) if batching else
                  {"completed": 0, "failed": 0, "skipped": 0, "rescheduled": 0})
        for _ in range(limit - sum(counts.values())):
            if self.stop.is_set():
                break
            with self._tx():
                statuses = "('pending','failed')" if retry_failed else "('pending')"
                extra = " AND kind<>'extract'" if batching else ""
                job = self.db.execute(f"SELECT * FROM jobs WHERE status IN {statuses} AND next_at<=? AND attempts<4{extra} ORDER BY id LIMIT 1", (time.time(),)).fetchone()
                if not job:
                    break
                self.db.execute("UPDATE jobs SET status='running',attempts=attempts+1,error=NULL WHERE id=?", (job["id"],))
                if job["kind"] == "extract":
                    event = self.db.execute("SELECT * FROM events WHERE owner=? AND pet=? AND id=?", (job["owner"], job["pet"], job["event_id"])).fetchone()
                    s = Scope(job["owner"], job["pet"], (event["world"],), event["session"])
                    generation = self._state(s)[1]
                    safe = list(event["text"])
                    for a, b in json.loads(event["exclusions"]):
                        for i in range(a, min(b, len(safe))):
                            safe[i] = " "
                    event_data = dict(event)
                    event_data["text"] = "".join(safe)
                else:
                    memory = self.db.execute("SELECT * FROM memories WHERE owner=? AND pet=? AND id=? AND revision=? AND status='active'",
                                             (job["owner"], job["pet"], job["memory_id"], job["revision"])).fetchone()
                    embedder = self.embedder
            try:
                if job["kind"] == "extract":
                    candidates = (self.extractor or RuleExtractor()).extract(event_data) if not event["excluded"] else []
                    require(isinstance(candidates, list) and len(candidates) <= 20, "invalid_extraction", "提取结果无效")
                    with self._tx():
                        self._scope(s)
                        if generation != self._state(s)[1]:
                            self.db.execute("UPDATE jobs SET status='pending',attempts=attempts-1 WHERE id=?", (job["id"],))
                            counts["rescheduled"] += 1
                            continue
                        for candidate in candidates:
                            require(isinstance(candidate, dict) and "quote" in candidate, "invalid_extraction", "提取结果缺少原文依据")
                            allowed = {"quote", "kind", "subject", "predicate", "value", "qualifiers", "event_at", "expires_at"}
                            require(set(candidate) <= allowed, "invalid_extraction", "提取模型试图写入未授权字段")
                            ev, a, b = self._source(s, event["id"], candidate["quote"])
                            options = {k: v for k, v in candidate.items() if k != "quote"}
                            # Store the original quote, not an ungrounded model paraphrase.
                            self._store(s, candidate["quote"], ev, a, b, **options)
                        self.db.execute("UPDATE jobs SET status='completed',error=NULL WHERE id=?", (job["id"],))
                else:
                    if memory is None or embedder is None:
                        with self._tx():
                            self.db.execute("UPDATE jobs SET status='cancelled' WHERE id=?", (job["id"],))
                        counts["skipped"] += 1
                        continue
                    embedding = vector(embedder.embed(memory["text"]))
                    with self._tx():
                        current = self.db.execute("SELECT status,id,revision,text FROM memories WHERE rowid=?", (memory["rowid"],)).fetchone()
                        still_current = current and tuple(current) == ("active", memory["id"], memory["revision"], memory["text"])
                        state = "completed" if still_current else "cancelled"
                        changed = self.db.execute("UPDATE jobs SET status=?,error=NULL WHERE id=? AND status='running'",
                                                  (state, job["id"])).rowcount
                        if changed and still_current:
                            self.db.execute("INSERT OR REPLACE INTO vectors VALUES(?,?,?,?)",
                                (memory["rowid"], embedder.model_id, len(embedding), dumps(embedding)))
                    if not changed or not still_current:
                        counts["skipped"] += 1
                        continue
                counts["completed"] += 1
            except Exception as exc:
                with self._tx():
                    # Error bodies may contain provider credentials; persist codes only.
                    changed = self.db.execute("UPDATE jobs SET status='failed',error=?,next_at=? WHERE id=? AND status='running'",
                                              (getattr(exc, "code", type(exc).__name__), time.time() + min(60, 2 ** (job["attempts"] + 1)), job["id"])).rowcount
                counts["failed" if changed else "skipped"] += 1
        return counts

    def start_worker(self, interval=2.0):
        require(isinstance(interval, (int, float)) and interval >= 0.1, "invalid_input", "维护间隔无效")
        if self.worker and self.worker.is_alive():
            return
        def loop():
            while not self.stop.wait(interval):
                try:
                    self.process_pending(limit=20, retry_failed=True, ready_only=True)
                except Exception:
                    if self.closed:
                        break
        self.worker = threading.Thread(target=loop, name="pet-memory-worker", daemon=True)
        self.worker.start()
