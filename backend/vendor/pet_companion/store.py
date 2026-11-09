from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
import threading
import time

from pet_memory.types import dumps
from .models import CharacterProfile, require


class CoreStore:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        INSERT OR IGNORE INTO metadata VALUES('version','1');
        CREATE TABLE IF NOT EXISTS profiles(owner TEXT,pet TEXT,revision INTEGER,body TEXT,
            PRIMARY KEY(owner,pet));
        CREATE TABLE IF NOT EXISTS states(owner TEXT,pet TEXT,body TEXT,PRIMARY KEY(owner,pet));
        CREATE TABLE IF NOT EXISTS state_inputs(owner TEXT,pet TEXT,event_id TEXT,
            PRIMARY KEY(owner,pet,event_id));
        CREATE TABLE IF NOT EXISTS applied_deletions(owner TEXT,pet TEXT,id TEXT,
            PRIMARY KEY(owner,pet,id));
        CREATE TABLE IF NOT EXISTS turns(owner TEXT,pet TEXT,id TEXT,session TEXT,text TEXT,
            status TEXT,reply TEXT,error TEXT,created REAL,updated REAL,mode TEXT,
            planned_reply TEXT,used_memories TEXT NOT NULL DEFAULT '[]',context_valid INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY(owner,pet,id));
        CREATE TABLE IF NOT EXISTS journal(seq INTEGER PRIMARY KEY AUTOINCREMENT,
            owner TEXT,pet TEXT,type TEXT,turn_id TEXT,payload TEXT,created REAL);
        """)
        require(self.db.execute("SELECT value FROM metadata WHERE key='version'").fetchone()[0] == "1",
                "schema_version", "对话数据版本不兼容")
        columns={r[1] for r in self.db.execute('PRAGMA table_info(turns)')}
        if 'context_valid' not in columns:
            self.db.execute('ALTER TABLE turns ADD COLUMN context_valid INTEGER NOT NULL DEFAULT 1')
        if 'context_sources' not in columns:
            self.db.execute('ALTER TABLE turns ADD COLUMN context_sources TEXT')

    @contextmanager
    def tx(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def profile(self, owner, pet):
        with self.lock:
            row = self.db.execute("SELECT revision,body FROM profiles WHERE owner=? AND pet=?", (owner, pet)).fetchone()
            return (CharacterProfile.parse(json.loads(row[1])), row[0]) if row else (None, 0)

    def set_profile(self, owner, pet, value, expected_revision):
        profile = CharacterProfile.parse(value)
        with self.tx():
            _, revision = self.profile(owner, pet)
            require(revision == expected_revision, "revision_conflict", "角色设定版本已变化")
            self.db.execute("INSERT OR REPLACE INTO profiles VALUES(?,?,?,?)",
                            (owner, pet, revision + 1, dumps(profile.as_dict())))
        return revision + 1

    def state(self, owner, pet):
        with self.lock:
            row = self.db.execute("SELECT body FROM states WHERE owner=? AND pet=?", (owner, pet)).fetchone()
            return json.loads(row[0]) if row else None

    def save_state(self, owner, pet, value, event_id=None):
        with self.tx():
            if event_id is not None:
                changed = self.db.execute("INSERT OR IGNORE INTO state_inputs VALUES(?,?,?)", (owner, pet, event_id)).rowcount
                if not changed:
                    return False
            self.db.execute("INSERT OR REPLACE INTO states VALUES(?,?,?)", (owner, pet, dumps(value)))
            return True

    def accept_turn(self, owner, pet, tid, session, text, mode):
        with self.tx():
            row = self.db.execute("SELECT * FROM turns WHERE owner=? AND pet=? AND id=?", (owner, pet, tid)).fetchone()
            if row:
                require(row["text"] == text and row["session"] == session, "idempotency_conflict", "同一消息 ID 不能用于不同内容")
                return dict(row), False
            date = time.time()
            self.db.execute("INSERT INTO turns(owner,pet,id,session,text,status,created,updated,mode) VALUES(?,?,?,?,?,'accepted',?,?,?)",
                            (owner, pet, tid, session, text, date, date, mode))
            return None, True

    def record_desktop_receipt(self, owner, pet, session, tid, text, reply, outcome):
        with self.tx():
            date = time.time()
            return self.db.execute(
                "INSERT INTO turns(owner,pet,id,session,text,reply,status,created,updated,mode) "
                "VALUES(?,?,?,?,?,?,'completed',?,?,?) ON CONFLICT(owner,pet,id) DO NOTHING",
                (owner, pet, tid, session, text, reply, date, date, "desktop:" + outcome)).rowcount == 1

    def update_turn(self, owner, pet, tid, status, reply=None, error=None):
        with self.tx():
            self.db.execute("UPDATE turns SET status=?,reply=COALESCE(?,reply),error=?,updated=? WHERE owner=? AND pet=? AND id=?",
                            (status, reply, error, time.time(), owner, pet, tid))

    def ready(self, owner, pet, tid, text, memory_ids, *, mode=None, context_sources=None):
        with self.tx():
            self.db.execute("UPDATE turns SET status='ready',planned_reply=?,used_memories=?,context_sources=?,mode=COALESCE(?,mode),updated=? WHERE owner=? AND pet=? AND id=?",
                            (text, dumps(memory_ids), dumps(context_sources) if context_sources is not None else None, mode, time.time(), owner, pet, tid))

    def turn(self, owner, pet, tid):
        with self.lock:
            row = self.db.execute("SELECT * FROM turns WHERE owner=? AND pet=? AND id=?", (owner, pet, tid)).fetchone()
            return dict(row) if row else None

    def reset_turn(self, owner, pet, tid):
        with self.tx():
            self.db.execute("UPDATE turns SET status='accepted',reply=NULL,planned_reply=NULL,error=NULL,used_memories='[]',context_sources=NULL,context_valid=1,updated=? "
                            "WHERE owner=? AND pet=? AND id=?", (time.time(), owner, pet, tid))

    def redact(self, owner, pet, turn_ids, memory_ids, deletion_id=None):
        with self.tx():
            if deletion_id and self.db.execute("SELECT 1 FROM applied_deletions WHERE owner=? AND pet=? AND id=?",
                                              (owner, pet, deletion_id)).fetchone():
                return []
            changed = []
            for row in self.db.execute("SELECT * FROM turns WHERE owner=? AND pet=?", (owner, pet)).fetchall():
                if row["id"] in turn_ids or set(json.loads(row["used_memories"])) & set(memory_ids):
                    self.db.execute("UPDATE turns SET text=?,reply=NULL,planned_reply=NULL,used_memories='[]',context_sources=NULL,status='redacted',context_valid=0,updated=? "
                                    "WHERE owner=? AND pet=? AND id=?", ("[该轮关联内容已清除]", time.time(), owner, pet, row["id"]))
                    # Keep the generation needed to stop an unconsumed delivery.
                    self.db.execute("""UPDATE journal SET
                        type=CASE WHEN type IN ('turn.interrupted','presentation.cancelled') THEN type ELSE 'turn.redacted' END,
                        payload=CASE WHEN type IN ('turn.interrupted','presentation.cancelled')
                            THEN json_object('generation',json_extract(payload,'$.generation'),'reason','memory_erased')
                            ELSE '{}' END
                        WHERE owner=? AND pet=? AND turn_id=?""", (owner, pet, row["id"]))
                    changed.append(row["id"])
            if deletion_id:
                self.db.execute("INSERT INTO applied_deletions VALUES(?,?,?)", (owner, pet, deletion_id))
            return changed

    def invalidate_context(self, owner, pet, turn_ids, memory_ids):
        with self.tx():
            changed = []
            for row in self.db.execute("SELECT id,used_memories FROM turns WHERE owner=? AND pet=?", (owner, pet)).fetchall():
                if row["id"] in turn_ids or set(json.loads(row["used_memories"])) & set(memory_ids):
                    self.db.execute("UPDATE turns SET context_valid=0 WHERE owner=? AND pet=? AND id=?", (owner, pet, row["id"]))
                    changed.append(row["id"])
            return changed

    def history(self, owner, pet, *, session=None, limit=30):
        require(isinstance(limit, int) and 1 <= limit <= 200, "invalid_input", "历史条数无效")
        with self.lock:
            query, args = "SELECT * FROM turns WHERE owner=? AND pet=?", [owner, pet]
            if session is not None:
                query += " AND session=?"
                args.append(session)
            rows = self.db.execute(query + " ORDER BY created DESC,id DESC LIMIT ?", [*args, limit]).fetchall()
            return [dict(r) for r in reversed(rows)]

    def recover(self, owner, pet):
        with self.tx():
            self.db.execute("UPDATE turns SET status='interrupted',error='process_restart',updated=? "
                            "WHERE owner=? AND pet=? AND status IN ('accepted','generating','ready','presenting')", (time.time(), owner, pet))

    def event(self, owner, pet, kind, tid, payload):
        with self.tx():
            seq = self.db.execute("INSERT INTO journal(owner,pet,type,turn_id,payload,created) VALUES(?,?,?,?,?,?)",
                                  (owner, pet, kind, tid, dumps(payload), time.time())).lastrowid
            # Keep a bounded event replay window, while retaining conversation history.
            self.db.execute("DELETE FROM journal WHERE owner=? AND pet=? AND seq < COALESCE((SELECT seq FROM journal "
                            "WHERE owner=? AND pet=? ORDER BY seq DESC LIMIT 1 OFFSET 1999),0)", (owner, pet, owner, pet))
            return seq

    def poll(self, owner, pet, after=0, limit=100):
        require(isinstance(after, int) and after >= 0 and isinstance(limit, int) and 1 <= limit <= 500,
                "invalid_cursor", "事件游标或条数无效")
        with self.lock:
            first = self.db.execute("SELECT min(seq) FROM journal WHERE owner=? AND pet=?", (owner, pet)).fetchone()[0]
            rows = self.db.execute("SELECT * FROM journal WHERE owner=? AND pet=? AND seq>? ORDER BY seq LIMIT ?",
                                   (owner, pet, after, limit)).fetchall()
            return {"events": [{"seq": r["seq"], "type": r["type"], "turn_id": r["turn_id"],
                                "payload": json.loads(r["payload"])} for r in rows],
                    "next_cursor": rows[-1]["seq"] if rows else after,
                    "gap": bool(after and first and after < first - 1)}

    def cursor(self, owner, pet):
        with self.lock:
            return self.db.execute("SELECT COALESCE(max(seq),0) FROM journal WHERE owner=? AND pet=?", (owner, pet)).fetchone()[0]

    def close(self):
        with self.lock:
            self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.db.close()
