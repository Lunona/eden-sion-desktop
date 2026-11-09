from __future__ import annotations

from pathlib import Path
import json
import threading
import time
import uuid

from pet_memory import MemoryService, Scope
from pet_memory.types import dumps, string
from .models import CharacterProfile, CoreError, ReplyPlan, require
from .presentation import PresentationScheduler
from .providers import OfflineDemoModel
from .state import CharacterState
from .store import CoreStore


class CompanionRuntime:
    """One companion, ordered events, bounded generation and explicit delivery ACKs."""
    def __init__(self, data_dir, *, owner_id="local-user", companion_id="my-companion", session_id="main",
                 profile=None, model=None, memory_options=None, start_ticker=True,
                 scheduler=None, state_clock=time.time, history_char_budget=6000):
        self.owner = string(owner_id, "owner_id", 128)
        self.pet = string(companion_id, "companion_id", 128)
        self.session = string(session_id, "session_id", 128)
        self.path = Path(data_dir).resolve()
        self.path.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.closed = False
        self.paused = False
        self.phase = "idle"
        self.generation = 0
        self.current = None
        self.pending = None
        self._deletion_size = None
        self.inflight = set()
        self.model = model or OfflineDemoModel()
        require(isinstance(history_char_budget, int) and 0 <= history_char_budget <= 32000,
                "invalid_budget", "短期历史预算无效")
        self.history_char_budget = history_char_budget
        self.scheduler = scheduler or PresentationScheduler()
        self.ticker = None
        self.memory = MemoryService(self.path / "memory.sqlite", **(memory_options or {}))
        try:
            self.store = CoreStore(self.path / "core.sqlite")
            saved, revision = self.store.profile(self.owner, self.pet)
            if saved is None:
                saved = CharacterProfile.parse(profile) if profile is not None else CharacterProfile()
                revision = self.store.set_profile(self.owner, self.pet, saved, 0)
            self.profile, self.profile_revision = saved, revision
            self.state = CharacterState(self.store, self.owner, self.pet, state_clock)
            self._sync_identity()
            self.store.recover(self.owner, self.pet)
            self._reconcile_deleted_context()
            self.memory.start_worker()
            self._emit("runtime.ready", None, {"mode": self.model.mode, "profile_revision": revision})
        except BaseException:
            if hasattr(self, "store"):
                self.store.close()
            self.memory.close()
            raise
        if start_ticker:
            self.ticker = threading.Thread(target=self._ticker, name="companion-timeline", daemon=True)
            self.ticker.start()

    def scope(self):
        return Scope(self.owner, self.pet, self.profile.world_ids, self.session)

    def _sync_identity(self):
        scope = self.scope()
        # Profile edits are host-owned; inspect the mirror using its prior scope
        # to allow an explicit host edit to expand or shrink readable worlds.
        with self.memory.lock:
            row = self.memory.db.execute("SELECT profile,revision FROM identities WHERE owner=? AND pet=?",
                                         (self.owner, self.pet)).fetchone()
        if row and row[0] == dumps(self.profile.memory_identity()):
            return
        self.memory.set_identity(scope, self.profile.memory_identity(), expected_revision=row[1] if row else None)

    def _emit(self, kind, tid, payload=None):
        return self.store.event(self.owner, self.pet, kind, tid, payload or {})

    def _reconcile_deleted_context(self):
        journal = self.memory.journal_path
        size = journal.stat().st_size if journal.exists() else 0
        if size == self._deletion_size:
            return []
        changed = []
        # The signed ledger is shared recovery evidence across the two local DBs.
        with self.memory.lock:
            entries = self.memory._read_deletions()
        for entry in entries:
            if entry["owner"] != self.owner or entry["pet"] != self.pet:
                continue
            turns = {s["event_id"][2:] for s in entry["spans"] if s["event_id"].startswith("u:")}
            changed.extend(self.store.redact(self.owner, self.pet, turns, entry["memory_ids"], entry["id"]))
        self._deletion_size = size
        if self.current and self.current["turn_id"] in changed:
            self._cancel("memory_erased")
            self._phase("idle")
        return changed

    def _publish_cues(self, events):
        for event in events:
            self._emit(event["type"], event["turn_id"], {**event["payload"], "generation": event["generation"]})

    def _phase(self, phase, tid=None):
        self.phase = phase
        self._emit("dialogue.status", tid, {"phase": phase})
        if phase in {"thinking", "waiting_for_provider", "idle", "paused"}:
            expression = "thoughtful" if phase in {"thinking", "waiting_for_provider"} and "thoughtful" in self.scheduler.expressions else "neutral"
            self._emit("expression.set", tid, {"name": expression, "generation": self.generation})

    def _cancel(self, reason):
        self._publish_cues(self.scheduler.cancel(reason))
        if self.current:
            job = self.current
            job["cancel"].set()
            row = self.store.turn(self.owner, self.pet, job["turn_id"])
            if row and row["status"] not in {"completed", "failed", "interrupted"}:
                if row["status"] != "redacted":
                    self.store.update_turn(self.owner, self.pet, job["turn_id"], "interrupted", error=reason)
                    if row["reply"]:
                        self._record_heard(job, row["reply"])
                self._emit("turn.interrupted", job["turn_id"], {"reason": reason, "generation": job["generation"]})
        self.pending = None
        self.current = None

    def _record_heard(self, job, text):
        if text:
            scope = Scope(self.owner, self.pet, self.profile.world_ids, job["session"])
            try:
                self.memory.observe(scope, "a:" + job["turn_id"], text, role="assistant")
            except Exception:
                # The accepted user event remains durable; no false memory ACK.
                self._emit("memory.write_failed", job["turn_id"], {"code": "assistant_source_not_saved"})

    def send(self, text, *, turn_id=None):
        text = string(text, "text", 8000)
        tid = string(turn_id or uuid.uuid4().hex, "turn_id", 100)
        with self.lock:
            require(not self.closed, "closed", "组件已关闭")
            require(not self.paused, "paused", "当前已暂停，请先恢复")
            prior, created = self.store.accept_turn(self.owner, self.pet, tid, self.session, text, self.model.mode)
            if not created:
                return {"status": prior["status"], "turn_id": tid, "duplicate": True, "visible_reply": prior["reply"]}
            try:
                self.memory.observe(self.scope(), "u:" + tid, text, role="user")
                if callable(getattr(self,'prepare_memory_source',None)):
                    self.prepare_memory_source('u:'+tid)
            except Exception:
                self.store.update_turn(self.owner, self.pet, tid, "failed", error="memory_source_failed")
                raise CoreError("memory_source_failed", "消息来源未能保存，本轮尚未开始") from None
            self._cancel("new_user_message")
            self.generation += 1
            job = {"turn_id": tid, "text": text, "session": self.session, "generation": self.generation,
                   "cancel": threading.Event(), "plan": None, "presenting": False, "memory_version": None,
                   "profile_revision": self.profile_revision}
            self.current = job
            self.state.apply(CharacterState.classify(text), "input:" + tid)
            self._emit("turn.accepted", tid, {"generation": self.generation, "mode": self.model.mode})
            self._phase("thinking", tid)
            self._launch(job)
            return {"status": "accepted", "turn_id": tid, "generation": self.generation, "duplicate": False}

    def _launch(self, job):
        if len(self.inflight) >= 2:
            self.pending = job
            self._phase("waiting_for_provider", job["turn_id"])
            return
        self.inflight.add(job["generation"])
        threading.Thread(target=self._run, args=(job,), name="companion-generation", daemon=True).start()

    def _is_current(self, job):
        return not self.closed and self.current is job and not job["cancel"].is_set()

    def _run(self, job):
        try:
            for attempt in range(2):
                with self.lock:
                    if not self._is_current(job):
                        return
                    self._reconcile_deleted_context()
                    if not self._is_current(job):
                        return
                    self.store.update_turn(self.owner, self.pet, job["turn_id"], "generating")
                    scope = Scope(self.owner, self.pet, self.profile.world_ids, job["session"])
                    history = [r for r in self.store.history(self.owner, self.pet, session=job["session"], limit=12)
                               if r["id"] != job["turn_id"] and r["status"] != "redacted" and r["context_valid"]]
                    request = {"text": job["text"], "profile": self.profile.as_dict(), "profile_revision": self.profile_revision,
                               "state": self.state.snapshot(),
                               "turn_id": job["turn_id"], "generation": job["generation"]}
                # A verified local command has its own response and requires no
                # recall provider or dialogue model.
                local = getattr(self.model, "local_reply", None)
                local_text = local(job["turn_id"]) if callable(local) else None
                memory = ({"hits": [], "snapshot_version": self.memory.health(scope)["snapshot_version"]}
                          if local_text is not None else self.memory.recall(
                              scope, job["text"], current_event_id="u:" + job["turn_id"], token_budget=1800))
                request["memory"] = memory
                with self.lock:
                    if not self._is_current(job):
                        return
                    prior = [(row, json.loads(row["used_memories"])) for row in history]
                    references = self.memory.document_references(scope, {mid for _, ids in prior for mid in ids})
                    bounded, used = [], 0
                    document_versions = set()
                    history_replies = []
                    source_filter = getattr(self.model, 'source_filter', None)
                    for row, ids in reversed(prior):
                        sources = [references[mid] for mid in ids if mid in references]
                        if any(not active for _, active in sources):
                            continue
                        reply=row["reply"]
                        refs=row["context_sources"]
                        if reply and refs and callable(source_filter) and not source_filter(scope,json.loads(refs)):
                            reply=None
                        size = len(row["text"]) + len(reply or "")
                        if used + size > self.history_char_budget:
                            break
                        if reply and refs:
                            history_replies.append(row["id"])
                        bounded.append({**{key: row[key] for key in ("id", "text", "status", "created", "mode")}, "reply":reply})
                        document_versions.update(root for root, _ in sources)
                        used += size
                    request["history"] = list(reversed(bounded))
                    if callable(source_filter):
                        request["_history_replies"] = history_replies
                    self._emit("memory.recalled", job["turn_id"], {"count": len(memory["hits"]),
                        "sources": sorted({h["knowledge_layer"] for h in memory["hits"]}),
                        "snapshot_version": memory["snapshot_version"]})
                plan = ReplyPlan.parse({"text": local_text} if local_text is not None
                                       else self.model.generate(request, job["cancel"]))
                with self.lock:
                    if not self._is_current(job):
                        return
                    fresh = self.memory.health(scope)["snapshot_version"]
                    if fresh != memory["snapshot_version"] or self.profile_revision != request["profile_revision"]:
                        if attempt == 0:
                            self._emit("turn.context_refreshed", job["turn_id"], {})
                            continue
                        raise CoreError("context_changed", "记忆刚刚更新，请重试这条消息")
                    local_mode = "local_command" if local_text is not None else None
                    used_ids = [h["memory_id"] for h in memory["hits"]]
                    if local_text is None:
                        used_ids = list(dict.fromkeys([*used_ids, *sorted(document_versions)]))
                    self.store.ready(self.owner, self.pet, job["turn_id"], plan.text, used_ids, mode=local_mode,
                                     context_sources=request.get('_reply_sources'))
                    job["plan"] = plan
                    job["memory_version"] = fresh
                    job["profile_revision"] = self.profile_revision
                    self._phase("ready", job["turn_id"])
                    self._emit("reply.ready", job["turn_id"], {"generation": job["generation"], "plan": plan.as_dict(),
                        "mode": local_mode or self.model.mode, "delivery_ack_required": True})
                    return
        except Exception as exc:
            with self.lock:
                if self._is_current(job):
                    code = getattr(exc, "code", "model_failed")
                    self.store.update_turn(self.owner, self.pet, job["turn_id"], "failed", error=code)
                    self._emit("turn.failed", job["turn_id"], {"code": code, "generation": job["generation"]})
                    self.current = None
                    self._phase("idle")
        finally:
            with self.lock:
                self.inflight.discard(job["generation"])
                if not self.closed and self.pending and self._is_current(self.pending):
                    pending = self.pending
                    self.pending = None
                    self._launch(pending)

    def can_present(self, turn_id, generation):
        with self.lock:
            job = self.current
            return bool(job and job["turn_id"] == turn_id and job["generation"] == generation and self._is_current(job)
                        and job["plan"] is not None and job["profile_revision"] == self.profile_revision
                        and job["memory_version"] == self.memory.health(self.scope())["snapshot_version"])

    def acknowledge(self, turn_id, generation, visible_chars, *, completed=False):
        with self.lock:
            require(isinstance(visible_chars, int) and not isinstance(visible_chars, bool) and visible_chars >= 0
                    and isinstance(completed, bool), "invalid_ack", "显示确认无效")
            if not self.can_present(turn_id, generation):
                if self.current and self.current["turn_id"] == turn_id and self.current["generation"] == generation:
                    self._cancel("stale_context")
                    self._phase("idle")
                return {"status": "ignored_stale"}
            job = self.current
            plan = job["plan"]
            row = self.store.turn(self.owner, self.pet, turn_id)
            require(len(row["reply"] or "") <= visible_chars <= len(plan.text), "invalid_ack", "显示进度不能后退或超过正文")
            require(not completed or visible_chars == len(plan.text), "invalid_ack", "完整确认须覆盖整条回复")
            if row["status"] == "completed":
                return {"status": "completed", "duplicate": True}
            self.store.update_turn(self.owner, self.pet, turn_id, "completed" if completed else "presenting", reply=plan.text[:visible_chars])
            if visible_chars and not job["presenting"]:
                job["presenting"] = True
                self._publish_cues(self.scheduler.start(turn_id, plan, generation))
                self._phase("presenting", turn_id)
                self._publish_cues(self.scheduler.tick())
            if completed:
                self._record_heard(job, plan.text)
                self.state.apply("neutral", "completion:" + turn_id, completed=True)
                self._emit("turn.delivered", turn_id, {"visible_chars": visible_chars, "generation": generation})
                if self.scheduler.status()["active"] is None:
                    self.current = None
                    self._phase("idle")
            return {"status": "completed" if completed else "presenting", "visible_chars": visible_chars}

    def interrupt(self, reason="user_interrupt"):
        with self.lock:
            require(not self.closed, "closed", "组件已关闭")
            reason = string(reason, "reason", 100)
            self._cancel(reason)
            self.generation += 1
            self._phase("paused" if self.paused else "idle")
            return {"status": "interrupted"}

    def pause(self, enabled=True):
        require(isinstance(enabled, bool), "invalid_input", "暂停开关无效")
        with self.lock:
            self.paused = enabled
            self.interrupt("paused" if enabled else "resumed")
            return {"status": "paused" if enabled else "idle"}

    def new_session(self, session_id):
        session_id = string(session_id, "session_id", 128)
        with self.lock:
            self.interrupt("session_changed")
            self.session = session_id
            self._emit("session.changed", None, {"session_id": session_id})
            return {"status": "ok", "session_id": session_id}

    def retry(self, turn_id):
        with self.lock:
            require(not self.closed and not self.paused, "paused", "组件已关闭或暂停")
            row = self.store.turn(self.owner, self.pet, turn_id)
            require(row is not None and row["status"] in {"failed", "interrupted"}, "invalid_retry", "该消息不可重试")
            require(not row["reply"], "partial_delivery", "已有部分内容显示，请发送新消息继续交流")
            require(row["session"] == self.session, "session_mismatch", "请在原会话中重试")
            self._cancel("retry")
            self.store.reset_turn(self.owner, self.pet, turn_id)
            self.generation += 1
            job = {"turn_id": turn_id, "text": row["text"], "session": self.session, "generation": self.generation,
                   "cancel": threading.Event(), "plan": None, "presenting": False, "memory_version": None,
                   "profile_revision": self.profile_revision}
            self.current = job
            self._phase("thinking", turn_id)
            self._launch(job)
            return {"status": "accepted", "turn_id": turn_id, "generation": self.generation}

    def set_profile(self, profile, *, expected_revision):
        p = CharacterProfile.parse(profile)
        with self.lock:
            require(not self.closed, "closed", "组件已关闭")
            require(expected_revision == self.profile_revision, "revision_conflict", "角色设定版本已变化")
            self._cancel("profile_changed")
            revision = self.store.set_profile(self.owner, self.pet, p, expected_revision)
            self.profile, self.profile_revision = p, revision
            try:
                self._sync_identity()
            except Exception:
                self.paused = True
                self._phase("paused")
                raise CoreError("identity_sync_failed", "身份同步未完成，组件已暂停；重启后会重试同步") from None
            self._emit("profile.changed", None, {"revision": revision})
            self._phase("paused" if self.paused else "idle")
            return {"status": "committed", "revision": revision}

    def forget_memory(self, memory_id, expected_revision):
        with self.lock:
            self._cancel("memory_erased")
            result = self.memory.forget(self.scope(), memory_id, expected_revision=expected_revision)
            ids = set(result["memory_ids"])
            redacted = self._reconcile_deleted_context()
            self._emit("memory.erased", None, {"memory_ids": sorted(ids), "redacted_turns": redacted})
            self._phase("idle")
            return {**result, "redacted_turns": redacted}

    def correct_memory(self, memory_id, text, expected_revision, *, mode="change", value=None, source_candidate=None):
        with self.lock:
            self._cancel("memory_corrected")
            before = self.memory.inspect(self.scope(), memory_id=memory_id, status="all")["items"]
            result = self.memory.correct(self.scope(), memory_id, text, expected_revision=expected_revision,
                                         mode=mode, value=value, source_candidate=source_candidate)
            turn_ids = {e["event_id"][2:] for item in before for e in item["evidence"] if e["event_id"].startswith("u:")}
            self.store.invalidate_context(self.owner, self.pet, turn_ids, [memory_id, *result.get("invalidated_memory_ids", [])])
            self._emit("memory.corrected", None, {"memory_id": memory_id, "revision": result["revision"]})
            self._phase("idle")
            return result

    def remember(self, text, *, world_id="real", knowledge_layer="shared_experience", kind="note",
                 predicate="", value=None, qualifiers=None, expires_at=None):
        with self.lock:
            require(not self.closed, "closed", "组件已关闭")
            self._cancel("memory_added")
            result = self.memory.remember(self.scope(), text, world_id=world_id, knowledge_layer=knowledge_layer,
                kind=kind, predicate=predicate, value=value, qualifiers=qualifiers, expires_at=expires_at,
                role="document" if knowledge_layer == "canon" else "user",
                subject="companion" if knowledge_layer == "canon" else "user")
            self._emit("memory.added", None, {"memory_id": result["memory_id"], "knowledge_layer": knowledge_layer})
            self._phase("paused" if self.paused else "idle")
            return result

    def audio_started(self, turn_id, generation, duration, segment=0):
        with self.lock:
            if not self.current or self.current["turn_id"] != turn_id or self.current["generation"] != generation:
                return {"status": "ignored_stale"}
            events = self.scheduler.audio_started(turn_id, generation, duration, segment)
            self._publish_cues(events)
            return {"status": "accepted" if events else "ignored_stale"}

    def mouth(self, turn_id, generation, level, segment=0):
        with self.lock:
            events = self.scheduler.mouth(turn_id, generation, level, segment)
            self._publish_cues(events)
            return {"status": "accepted" if events else "ignored_stale"}

    def audio_ended(self, turn_id, generation):
        with self.lock:
            if not self.current or self.current["turn_id"] != turn_id or self.current["generation"] != generation:
                return {"status": "ignored_stale"}
            return self.interrupt("audio_ended")

    def tick(self):
        with self.lock:
            if self.closed:
                return
            events = self.scheduler.tick()
            self._publish_cues(events)
            if any(e["type"] == "presentation.completed" for e in events):
                if self.current and self.store.turn(self.owner, self.pet, self.current["turn_id"])["status"] == "completed":
                    self.current = None
                    self._phase("paused" if self.paused else "idle")

    def _ticker(self):
        while not self.stop.wait(0.05):
            try:
                self.tick()
            except Exception:
                if self.closed:
                    return

    def poll(self, after=0, limit=100):
        with self.lock:
            require(not self.closed, "closed", "组件已关闭")
            self._reconcile_deleted_context()
            return self.store.poll(self.owner, self.pet, after, limit)

    def desktop_dialogue_context(self):
        with self.lock:
            require(not self.closed, "closed", "组件已关闭")
            self._reconcile_deleted_context()
            rows = self.store.history(self.owner, self.pet, session=self.session, limit=8)
            recent = [row for row in rows if row["context_valid"] and row["reply"]
                      and row["status"] in {"completed", "interrupted"}]
            return [{"user": row["text"][:220], "assistant": row["reply"][:260],
                     "outcome": (row["mode"] or "").removeprefix("desktop:")
                     if (row["mode"] or "").startswith("desktop:") else None}
                    for row in recent[-4:]]

    def record_desktop_receipt(self, turn_id, text, reply, outcome):
        tid = string(turn_id, "turn_id", 100)
        prompt = string(text, "text", 2000)
        message = string(reply, "reply", 600)
        require(outcome in {"submitted", "confirmed", "unconfirmed", "failed", "cancelled"},
                "invalid_input", "电脑操作回执状态无效")
        with self.lock:
            require(not self.closed, "closed", "组件已关闭")
            return self.store.record_desktop_receipt(self.owner, self.pet, self.session, tid,
                                                     prompt, message, outcome)

    def history(self, limit=30):
        with self.lock:
            require(not self.closed, "closed", "组件已关闭")
            self._reconcile_deleted_context()
            rows = self.store.history(self.owner, self.pet, session=self.session, limit=limit)
            # Planned but unacknowledged text is never presented as delivered history.
            return [{k: r[k] for k in ("id", "text", "reply", "status", "created", "mode")} for r in rows]

    def status(self):
        with self.lock:
            require(not self.closed, "closed", "组件已关闭")
            return {"version": "0.1.0", "phase": self.phase, "mode": self.model.mode, "session_id": self.session,
                    "profile": self.profile.as_dict(), "profile_revision": self.profile_revision,
                    "state": self.state.snapshot(), "presentation": self.scheduler.status(),
                    "inflight_generations": len(self.inflight), "queued_latest": self.pending is not None,
                    "event_cursor": self.store.cursor(self.owner, self.pet),
                    "memory": self.memory.health(self.scope())}

    def close(self):
        with self.lock:
            if self.closed:
                return
            self._cancel("runtime_closed")
            self.closed = True
            self.stop.set()
        if self.ticker and self.ticker is not threading.current_thread():
            self.ticker.join(timeout=1)
        self.memory.close()
        self.store.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
