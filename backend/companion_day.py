"""Daily plan and recorded character activities in the companion store."""
from datetime import datetime, timedelta
import re
import time
import uuid

from pet_memory.types import MemoryError


PERIODS = (
    (0, 390, "夜里休息", ("把夜晚留给安静。",)),
    (390, 540, "晨间准备", ("慢慢醒来，整理一下手边的东西。", "留一点时间看看今天想做什么。")),
    (540, 720, "上午的个人时间", ("读一会儿书，把有意思的地方记下来。", "把读到一半的内容接着看完。")),
    (720, 810, "午间休息", ("先歇一会儿，把上午的事放一放。",)),
    (810, 1050, "下午的个人时间", ("整理笔记，留下几个以后还想琢磨的问题。", "翻看旧笔记，把想接着做的事挑出来。")),
    (1050, 1260, "傍晚的空档", ("给自己留一点自由时间，有话可以慢慢聊。", "把没做完的事先放好，等有空再接着做。")),
    (1260, 1440, "夜间收尾", ("把今天值得留下的几件事理一理，准备休息。",)),
)


def day_plan(timestamp):
    local = datetime.fromtimestamp(timestamp)
    minute = local.hour * 60 + local.minute
    seed = local.date().toordinal()
    slots = [
        {"start": start, "end": end, "title": title,
         "detail": options[(seed + index) % len(options)],
         "status": "elapsed" if minute >= end else "current" if minute >= start else "upcoming"}
        for index, (start, end, title, options) in enumerate(PERIODS)
    ]
    return {"day": local.date().isoformat(), "source": "role_plan", "slots": slots}


REST_SECONDS = {0: 20 * 60, 720: 5 * 60}
CHAT_PHASES = {"thinking", "waiting_for_provider", "ready", "presenting"}
HEADING = re.compile(r"^#{1,6}[ \t]+\S", re.MULTILINE)


class RoleActivities:
    def __init__(self, store, owner, pet, *, clock=time.time, steady=time.monotonic):
        self.store, self.key = store, (owner, pet)
        self.clock, self.steady = clock, steady
        self.last_step = steady()
        self.rest_id, self.rest_credit = None, 0.
        with self.store.tx():
            store.db.execute("""CREATE TABLE IF NOT EXISTS companion_role_activities(
                owner TEXT NOT NULL, pet TEXT NOT NULL, id TEXT NOT NULL, kind TEXT NOT NULL,
                state TEXT NOT NULL, reason TEXT NOT NULL, source_id TEXT, revision INTEGER,
                created REAL NOT NULL, ended REAL, deadline REAL, progress REAL NOT NULL,
                total INTEGER NOT NULL, parts INTEGER NOT NULL DEFAULT 0, headings INTEGER NOT NULL DEFAULT 0,
                note_state TEXT,
                PRIMARY KEY(owner,pet,id))""")
            if "note_state" not in {row[1] for row in store.db.execute("PRAGMA table_info(companion_role_activities)")}:
                store.db.execute("ALTER TABLE companion_role_activities ADD COLUMN note_state TEXT")
            store.db.execute("""CREATE INDEX IF NOT EXISTS companion_role_state
                ON companion_role_activities(owner,pet,state,ended)""")
            store.db.execute("""CREATE INDEX IF NOT EXISTS companion_reading_queue
                ON companion_role_activities(owner,pet,ended)
                WHERE kind='read' AND state='completed' AND note_state='queued'""")
            store.db.execute("""CREATE INDEX IF NOT EXISTS companion_turns_day
                ON turns(owner,pet,status,updated)""")
            store.db.execute("""UPDATE companion_role_activities SET state='paused'
                WHERE owner=? AND pet=? AND state='running'""", self.key)
            store.db.execute("""UPDATE companion_role_activities SET note_state='queued'
                WHERE owner=? AND pet=? AND note_state='running'""", self.key)

    def _pending(self, kind):
        return self.store.db.execute("""SELECT * FROM companion_role_activities WHERE owner=? AND pet=?
            AND kind=? AND state IN ('queued','running','paused') ORDER BY created LIMIT 1""",
            (*self.key, kind)).fetchone()

    def optional_speech_allowed(self):
        with self.store.lock:
            return self.store.db.execute("""SELECT 1 FROM companion_role_activities WHERE owner=? AND pet=?
                AND (state='running' OR (kind='read' AND state IN ('queued','paused'))
                    OR (state='completed' AND note_state IN ('queued','running'))) LIMIT 1""",
                self.key).fetchone() is None

    def request_read(self, source_id, revision, length):
        with self.store.tx():
            existing = self._pending("read")
            if existing:
                if (existing["source_id"], existing["revision"]) == (source_id, revision):
                    return
                raise ValueError("已有一份资料在等待或阅读中，请先在「今日」取消它")
            self.store.db.execute("""INSERT INTO companion_role_activities
                (owner,pet,id,kind,state,reason,source_id,revision,created,progress,total,note_state)
                VALUES(?,?,?,'read','queued','requested',?,?,?,0,?,'queued')""",
                (*self.key, "read:" + uuid.uuid4().hex, source_id, revision, self.clock(), length))

    def cancel_read(self, activity_id):
        with self.store.tx():
            return bool(self.store.db.execute("""UPDATE companion_role_activities SET state='cancelled',ended=?
                WHERE owner=? AND pet=? AND id=? AND kind='read' AND state IN ('queued','running','paused')""",
                (self.clock(), *self.key, activity_id)).rowcount)

    def claim_reading_note(self):
        with self.store.lock:
            row = self.store.db.execute("""SELECT id,source_id,revision FROM companion_role_activities
                WHERE owner=? AND pet=? AND kind='read' AND state='completed' AND note_state='queued'
                ORDER BY ended LIMIT 1""", self.key).fetchone()
        if row is None:
            return None
        with self.store.tx():
            changed = self.store.db.execute("""UPDATE companion_role_activities SET note_state='running'
                WHERE owner=? AND pet=? AND id=? AND note_state='queued'""", (*self.key,row["id"])).rowcount
            return dict(row) if changed else None

    def finish_reading_note(self, activity_id, state):
        with self.store.tx():
            self.store.db.execute("""UPDATE companion_role_activities SET note_state=?
                WHERE owner=? AND pet=? AND id=? AND note_state='running'""", (state,*self.key,activity_id))

    def _read(self, row, load, allowed):
        state = row["state"]
        if not allowed:
            if state != "running":
                return False
            return self._commit_read(row, state="paused")
        offset = int(row["progress"])
        try:
            part = load(row["source_id"], offset)
        except MemoryError:
            return self._commit_read(row, state="unavailable", ended=self.clock())
        if part["revision"] != row["revision"] or part["total_chars"] != row["total"]:
            return self._commit_read(row, state="unavailable", ended=self.clock())
        end = part["next_offset"]
        if not offset < end <= row["total"] or len(part["text"]) != end - offset:
            return self._commit_read(row, state="unavailable", ended=self.clock())
        finished = end == row["total"]
        # Count complete Markdown heading lines once, including a heading crossing a page boundary.
        headings = len(HEADING.findall(part["heading_text"]))
        return self._commit_read(row, state="completed" if finished else "running",
                                 progress=end, parts=1, headings=headings, ended=self.clock() if finished else None)

    def _commit_read(self, row, *, state, progress=None, parts=0, headings=0, ended=None):
        with self.store.tx():
            return bool(self.store.db.execute("""UPDATE companion_role_activities
                SET state=?,progress=?,parts=parts+?,headings=headings+?,ended=?
                WHERE owner=? AND pet=? AND id=? AND state=? AND progress=?""",
                (state, row["progress"] if progress is None else progress, parts, headings, ended,
                 *self.key, row["id"], row["state"], row["progress"])).rowcount)

    def _rest(self, now, elapsed, allowed):
        local = datetime.fromtimestamp(now)
        minute = local.hour * 60 + local.minute
        with self.store.lock:
            row = self._pending("rest")
            if row and now >= row["deadline"]:
                return self._save_rest(row, "expired", row["progress"] + self.rest_credit, now)
            if row is None:
                if not allowed:
                    return False
                slot = next((slot for slot in PERIODS if slot[0] <= minute < slot[1]), None)
                if slot is None or slot[0] not in REST_SECONDS:
                    return False
                start, end = slot[:2]
                day = local.replace(hour=0, minute=0, second=0, microsecond=0)
                deadline = (day + timedelta(minutes=end)).timestamp()
                total = REST_SECONDS[start]
                if deadline - now < total:
                    return False
                identifier = f"rest:{local.date()}:{start}"
                with self.store.tx():
                    changed = self.store.db.execute("""INSERT OR IGNORE INTO companion_role_activities
                        (owner,pet,id,kind,state,reason,created,deadline,progress,total)
                        VALUES(?,?,?,'rest','running','rest_window',?,?,0,?)""",
                        (*self.key, identifier, now, deadline, total)).rowcount
                if changed:
                    self.rest_id, self.rest_credit = identifier, 0.
                return bool(changed)
            if self.rest_id != row["id"]:
                self.rest_id, self.rest_credit = row["id"], 0.
            if not allowed:
                return row["state"] == "running" and self._save_rest(row, "paused", row["progress"] + self.rest_credit)
            if row["state"] == "paused":
                return self._save_rest(row, "running", row["progress"])
            self.rest_credit += elapsed
            progress = min(row["total"], row["progress"] + self.rest_credit)
            if progress >= row["total"]:
                return self._save_rest(row, "completed", progress, now)
            if self.rest_credit >= 5:
                return self._save_rest(row, "running", progress)
            return False

    def _save_rest(self, row, state, progress, ended=None):
        with self.store.tx():
            self.store.db.execute("""UPDATE companion_role_activities SET state=?,progress=?,ended=?
                WHERE owner=? AND pet=? AND id=?""", (state, progress, ended, *self.key, row["id"]))
        self.rest_credit = 0.
        return True

    def tick(self, *, allowed, load):
        current = self.steady()
        elapsed = current - self.last_step
        self.last_step = current
        # Process rest advances only on observed ticks. Suspend and restart gaps earn no time.
        elapsed = elapsed if 0 < elapsed <= 3 else 0.
        with self.store.lock:
            reading = self._pending("read")
        changed = self._rest(self.clock(), elapsed, allowed and reading is None)
        return (self._read(reading, load, allowed) if reading else False) or changed

    @staticmethod
    def _public(row):
        kind, state = row["kind"], row["state"]
        result = {"id": row["id"], "kind": kind, "state": state, "reason": row["reason"],
                  "created": row["created"], "ended": row["ended"], "deadline": row["deadline"],
                  "progress": int(row["progress"]),
                  "total": row["total"], "interruptible": state in ("queued", "running", "paused")}
        if kind == "read" and state == "completed":
            result["sections"] = row["parts"]
            result["headings"] = row["headings"]
            if row["note_state"]:
                result["notes"] = row["note_state"]
        return result

    def snapshot(self, dialogue, program):
        now = self.clock()
        day = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0)
        with self.store.lock:
            read, rest = self._pending("read"), self._pending("rest")
            recent = self.store.db.execute("""SELECT * FROM companion_role_activities
                WHERE owner=? AND pet=? AND ended>=? ORDER BY ended DESC,rowid DESC LIMIT 8""",
                (*self.key, day.timestamp())).fetchall()
            counts = {row[0]:row[1] for row in self.store.db.execute("""SELECT status,count(*) FROM turns WHERE owner=? AND pet=?
                AND status IN ('completed','failed','interrupted') AND updated>=? GROUP BY status""",
                (*self.key, day.timestamp()))}
        pending = [self._public(row) for row in (read, rest) if row is not None]
        running = next((item for item in pending if item["state"] == "running"), None)
        chatting = dialogue in CHAT_PHASES or program in ("recognizing", "speaking", "synthesizing", "playing")
        current = {"kind": "chat", "state": "running", "reason": "dialogue", "interruptible": True} if chatting else (
            running if running and dialogue == "idle" and program in ("idle", "listening") else
            {"kind": "idle", "state": "running", "reason": "available", "interruptible": True})
        return {"current": current, "pending": pending, "recent": [self._public(row) for row in recent],
                "delivered": counts.get("completed", 0),
                "interrupted": counts.get("interrupted", 0), "failed": counts.get("failed", 0),
                "program": dialogue if program in ("idle", "listening") and dialogue != "idle" else program}
