"""Local activity and reminder decisions backed by the existing companion store."""
import math
import re
import time
import uuid
from datetime import datetime


ACTIVITY = r"做题|学习|复习|写作|工作|开会"
NUMBER = r"[1-9]\d{0,2}|[一二两三四五六七八九十]{1,3}"
DURATION = rf"半(?:个)?小时|一刻钟|(?:{NUMBER})\s*(?:秒钟?|分钟|个?小时)"
START = re.compile(
    rf"^(?:我)?(?:先|准备|要)?(?P<activity>{ACTIVITY})(?:了)?[，,。\s]+"
    rf"(?:请)?(?P<duration>{DURATION})(?:之后|后)[，,\s]*(?:请)?(?:提醒我|叫我)"
    r"(?:休息(?:一下|一会儿|一会|会儿)?|起来活动一下)[。！!]*"
    r"(?:[，,。\s]+(?:这)?期间[，,\s]*(?:请)?"
    r"(?P<quiet>(?:先)?(?:别|不要)(?:主动找我|主动搭话|主动打扰我|打扰我|打断我)"
    r"|可以(?:主动找我|主动搭话)))?$"
)
CANCEL = re.compile(r"^(?:请)?(?:帮我)?取消(?:这次|刚才的|这个)?(?:专注提醒|休息提醒|专注陪伴)$")
REPEAT = re.compile(rf"^(?:以后|今后)[，,\s]*(?P<activity>{ACTIVITY})(?:的时候|时)?(?:也|都)?(?:按|就)?这样(?:做|陪我)?$")
DIGITS = dict(zip("一二两三四五六七八九", (1, 2, 2, 3, 4, 5, 6, 7, 8, 9)))
GRACE_SECONDS = 20 * 60
LEGACY_GRACE_SECONDS = 6 * 3600
RECEIPT_WAIT_SECONDS = 90
PROACTIVE_LINES = (
    ("我在这里。想聊一会儿的话，直接叫我就好。", "ここにいるよ。少し話したくなったら、そのまま声をかけてね。"),
    ("要不要停一下，喝口水？等你准备好了，我们再继续。", "少し手を止めて、お水でも飲まない？"),
    ("今天有什么想和我分享的事吗？我有空听。", "今日は、私に話したいことが何かあった？"),
)
OUTING = re.compile(r"^我(?:马上|一会儿|等会儿|待会儿|准备|打算|正要)(?:就|要)?(?:出门|出发|出去散步)(?:[，,。！!\s]|$)")


def duration_seconds(value):
    value = value.replace(" ", "")
    if value.startswith("半"):
        return 1800
    if value == "一刻钟":
        return 900
    match = re.fullmatch(rf"({NUMBER})(秒钟?|分钟|个?小时)", value)
    if not match:
        return None
    amount, unit = match.groups()
    if amount.isascii():
        count = int(amount)
    elif "十" in amount:
        tens, ones = amount.split("十", 1)
        if (tens and tens not in DIGITS) or (ones and ones not in DIGITS):
            return None
        count = DIGITS.get(tens, 1) * 10 + DIGITS.get(ones, 0)
    else:
        count = DIGITS.get(amount, 0)
    seconds = count * (1 if unit.startswith("秒") else 60 if unit == "分钟" else 3600)
    return seconds if 1 <= seconds <= 12 * 3600 else None


def focus_request(text):
    text = text.strip().rstrip("。！! ")
    match = START.fullmatch(text)
    if match:
        seconds = duration_seconds(match["duration"])
        if not seconds:
            return None
        preference = match["quiet"]
        return {"kind": "start", "activity": match["activity"], "seconds": seconds,
                "duration": match["duration"], "quiet": None if not preference else not preference.startswith("可以")}
    if CANCEL.fullmatch(text):
        return {"kind": "cancel"}
    match = REPEAT.fullmatch(text)
    return {"kind": "remember", "activity": match["activity"]} if match else None


class CompanionScheduler:
    def __init__(self, store, owner, pet, *, clock=time.time):
        self.store, self.owner, self.pet, self.clock = store, owner, pet, clock
        with store.tx():
            tables = {row[0] for row in store.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "companion_focus" in tables and "companion_actions" not in tables:
                store.db.execute("ALTER TABLE companion_focus RENAME TO companion_actions")
            if "companion_focus_receipts" in tables and "companion_action_receipts" not in tables:
                store.db.execute("ALTER TABLE companion_focus_receipts RENAME TO companion_action_receipts")
            store.db.execute("""CREATE TABLE IF NOT EXISTS companion_actions (
                owner TEXT NOT NULL, pet TEXT NOT NULL, id TEXT NOT NULL,
                activity TEXT NOT NULL, started REAL NOT NULL, due REAL NOT NULL, expires REAL NOT NULL,
                quiet INTEGER NOT NULL, status TEXT NOT NULL, dispatched REAL, displayed REAL,
                display_state TEXT NOT NULL DEFAULT 'pending', audio_state TEXT NOT NULL DEFAULT 'pending',
                kind TEXT NOT NULL DEFAULT 'focus', title TEXT NOT NULL DEFAULT '', source_ref TEXT,
                PRIMARY KEY(owner,pet,id))""")
            columns = {row[1] for row in store.db.execute("PRAGMA table_info(companion_actions)")}
            if "kind" not in columns:
                store.db.execute("ALTER TABLE companion_actions ADD COLUMN kind TEXT NOT NULL DEFAULT 'focus'")
            if "title" not in columns:
                store.db.execute("ALTER TABLE companion_actions ADD COLUMN title TEXT NOT NULL DEFAULT ''")
            if "source_ref" not in columns:
                store.db.execute("ALTER TABLE companion_actions ADD COLUMN source_ref TEXT")
            if "repeat" not in columns:
                store.db.execute("ALTER TABLE companion_actions ADD COLUMN repeat TEXT NOT NULL DEFAULT 'none'")
            store.db.execute("""CREATE TABLE IF NOT EXISTS companion_local_replies (
                owner TEXT NOT NULL, pet TEXT NOT NULL, turn_id TEXT NOT NULL, reply TEXT NOT NULL,
                focus_task_id TEXT,
                PRIMARY KEY(owner,pet,turn_id))""")
            store.db.execute("""CREATE INDEX IF NOT EXISTS companion_actions_due
                ON companion_actions(owner,pet,status,due)""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS companion_action_receipts (
                owner TEXT NOT NULL, pet TEXT NOT NULL, id TEXT NOT NULL,
                channel TEXT NOT NULL, state TEXT NOT NULL, at REAL NOT NULL,
                PRIMARY KEY(owner,pet,id,channel,state))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS companion_proactive (
                owner TEXT NOT NULL, pet TEXT NOT NULL, enabled INTEGER NOT NULL,
                PRIMARY KEY(owner,pet))""")
            # An earlier process may have delivered an external notification just
            # before it exited. Preserve uncertainty and avoid a second delivery.
            recovered_at = self.clock()
            self._mark_display_unconfirmed(recovered_at)
            store.db.execute("""INSERT OR IGNORE INTO companion_action_receipts
                SELECT owner,pet,id,'audio','interrupted',? FROM companion_actions
                WHERE owner=? AND pet=? AND dispatched IS NOT NULL
                  AND audio_state IN ('requested','generated','playing')""", (recovered_at, owner, pet))
            store.db.execute("""UPDATE companion_actions SET audio_state=CASE
                  WHEN audio_state='pending' THEN 'unconfirmed' ELSE 'interrupted' END
                WHERE owner=? AND pet=? AND dispatched IS NOT NULL
                  AND audio_state IN ('pending','requested','generated','playing')""", (owner, pet))
            config = store.db.execute("SELECT enabled FROM companion_proactive WHERE owner=? AND pet=?",
                                      (owner, pet)).fetchone()
            last = store.db.execute("""SELECT max(started) FROM companion_actions
                WHERE owner=? AND pet=? AND kind IN ('proactive','weather')""", (owner, pet)).fetchone()[0]
        self.proactive_enabled = not config or bool(config["enabled"])
        self.last_proactive = last or 0
        self.unresponded_proactive = 0
        self.proactive_activity_at = 0
        self.proactive_after = max(self.clock() + 480, self.last_proactive + 1500)

    def _row(self, task_id):
        return self.store.db.execute("SELECT * FROM companion_actions WHERE owner=? AND pet=? AND id=?",
                                     (self.owner, self.pet, task_id)).fetchone()

    def local_reply(self, turn_id):
        with self.store.lock:
            row = self.store.db.execute("""SELECT reply FROM companion_local_replies
                WHERE owner=? AND pet=? AND turn_id=?""", (self.owner, self.pet, turn_id)).fetchone()
        return row["reply"] if row else None

    def _save_reply(self, turn_id, text, task_id=None):
        self.store.db.execute("INSERT OR IGNORE INTO companion_local_replies VALUES(?,?,?,?,?)",
                              (self.owner, self.pet, turn_id, text, task_id))
        return text

    def save_reply(self, turn_id, text, *, task_id=None):
        with self.store.tx():
            return self._save_reply(turn_id, text, task_id)

    def start(self, turn_id, request, *, focus_preference=None):
        with self.store.tx():
            prior = self.local_reply(turn_id)
            if prior is not None:
                return prior
            now = self.clock()
            due = now + request["seconds"]
            quiet = focus_preference == "quiet" if request["quiet"] is None else request["quiet"]
            self.store.db.execute("""UPDATE companion_actions SET status='cancelled'
                WHERE owner=? AND pet=? AND kind='focus' AND status='pending'""", (self.owner, self.pet))
            self.store.db.execute("""INSERT INTO companion_actions(
                owner,pet,id,activity,started,due,expires,quiet,status) VALUES(?,?,?,?,?,?,?,?,'pending')""",
                (self.owner, self.pet, "focus:" + turn_id, request["activity"], now, due,
                 due + GRACE_SECONDS, int(quiet)))
            text = "好，" + request["duration"] + "后提醒你休息。"
            if quiet:
                text += "这段时间我会安静陪你。"
            return self._save_reply(turn_id, text, "focus:" + turn_id)

    def cancel(self, turn_id):
        with self.store.tx():
            prior = self.local_reply(turn_id)
            if prior is not None:
                return prior
            changed = self.store.db.execute("""UPDATE companion_actions SET status='cancelled'
                WHERE owner=? AND pet=? AND kind='focus' AND status='pending'""", (self.owner, self.pet)).rowcount
            return self._save_reply(turn_id, "好，已取消这次专注提醒。" if changed else "现在没有等待触发的专注提醒。")

    def recent_focus(self, activity):
        now = self.clock()
        with self.store.lock:
            return self.store.db.execute("""SELECT * FROM companion_actions
                WHERE owner=? AND pet=? AND kind='focus' AND activity=? AND status NOT IN ('cancelled','overdue','removed')
                  AND due>=? ORDER BY started DESC LIMIT 1""", (self.owner, self.pet, activity, now - 300)).fetchone()

    def migrate_reminders(self, rows):
        if not rows:
            return
        with self.store.tx():
            for row in rows:
                historical = row["status"] == "notified"
                self.store.db.execute("""INSERT OR IGNORE INTO companion_actions(
                    owner,pet,id,activity,started,due,expires,quiet,status,kind,title,display_state,audio_state)
                    VALUES(?,?,?,'',0,?,?,0,?,'reminder',?,?,?)""",
                    (self.owner, self.pet, row["id"], row["at"], row["at"] + LEGACY_GRACE_SECONDS,
                     "uncertain" if historical else row["status"], row["title"],
                     "legacy_dispatched" if historical else "pending", "skipped" if historical else "pending"))

    def add_reminder(self, request):
        title, at, now = request.get("title"), request.get("at"), self.clock()
        repeat = str(request.get("repeat") or "none").strip().lower()
        if repeat not in ("none", "daily", "weekly", "monthly", "yearly"):
            repeat = "none"
        if (not isinstance(title, str) or not 1 <= len(title.strip()) <= 120 or
                type(at) not in (int, float) or not math.isfinite(at) or not now - 60 <= at <= now + 366 * 86400):
            raise ValueError("请填写一年内的提醒时间和120字以内的内容")
        with self.store.tx():
            count = self.store.db.execute("""SELECT count(*) FROM companion_actions
                WHERE owner=? AND pet=? AND kind='reminder' AND status<>'removed'""",
                (self.owner, self.pet)).fetchone()[0]
            if count >= 80:
                raise ValueError("最多保留80项提醒")
            self.store.db.execute("""INSERT INTO companion_actions(
                owner,pet,id,activity,started,due,expires,quiet,status,kind,title)
                VALUES(?,?,?,'',?,?,?,0,'pending','reminder',?)""",
                (self.owner, self.pet, uuid.uuid4().hex, now, at, at + LEGACY_GRACE_SECONDS, title.strip()))
            if repeat != "none":
                self.store.db.execute("UPDATE companion_actions SET repeat=? WHERE owner=? AND pet=? AND rowid=last_insert_rowid()", (repeat, self.owner, self.pet))

    def finish(self, task_id, action):
        if action not in ("done", "remove"):
            raise ValueError("未知的提醒操作")
        with self.store.tx():
            row = self._row(task_id)
            if not row or row["kind"] not in ("focus", "reminder") or row["status"] == "removed":
                raise ValueError("提醒已变化，请刷新")
            status = "removed" if action == "remove" else "done"
            rep = row["repeat"] if "repeat" in row.keys() else "none"
            if action == "done" and rep in ("daily", "weekly", "monthly", "yearly"):
                step = {"daily": 86400, "weekly": 7 * 86400, "monthly": 30 * 86400, "yearly": 365 * 86400}[rep]
                nxt = max(self.clock() + 60, float(row["due"]) + step)
                self.store.db.execute("UPDATE companion_actions SET status='pending',due=?,expires=?,dispatched=NULL,display_state='pending',audio_state='pending' WHERE owner=? AND pet=? AND id=?",
                                      (nxt, nxt + LEGACY_GRACE_SECONDS, self.owner, self.pet, task_id))
                return
            self.store.db.execute("UPDATE companion_actions SET status=? WHERE owner=? AND pet=? AND id=?",
                                  (status, self.owner, self.pet, task_id))

    def status(self):
        now = self.clock()
        with self.store.lock:
            focuses = self.store.db.execute("""SELECT * FROM companion_actions WHERE owner=? AND pet=?
                AND kind='focus' AND status<>'removed' ORDER BY started DESC LIMIT 25""",
                (self.owner, self.pet)).fetchall()
            regular = self.store.db.execute("""SELECT * FROM companion_actions WHERE owner=? AND pet=?
                AND kind='reminder' AND status<>'removed' ORDER BY due""", (self.owner, self.pet)).fetchall()
        current = next((row for row in focuses if row["status"] == "pending" and row["due"] > now), None)
        focus = {"activity": current["activity"], "started_at": current["started"],
                 "ends_at": current["due"], "quiet": bool(current["quiet"]),
                 "source_turn": current["id"][len("focus:"):]} if current else None
        reminders = [{"id": row["id"], "title": row["title"] or row["activity"] + "后休息", "at": row["due"], "status": row["status"],
                      "display_state": row["display_state"], "audio_state": row["audio_state"], "repeat": row["repeat"] if "repeat" in row.keys() else "none"} for row in [*focuses, *regular]]
        return {"focus": focus, "reminders": reminders}

    def allows_background(self):
        with self.store.lock:
            return self.store.db.execute("""SELECT 1 FROM companion_actions
                WHERE owner=? AND pet=? AND kind='focus' AND status='pending' AND due>? AND quiet=1 LIMIT 1""",
                (self.owner, self.pet, self.clock())).fetchone() is None

    def activity(self):
        with self.store.lock:
            now = self.clock()
            self.unresponded_proactive = 0
            self.proactive_activity_at = now
            self.proactive_after = max(now + 480, self.last_proactive + 1500)

    def configure_proactive(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("主动搭话设置无效")
        with self.store.tx():
            self.store.db.execute("INSERT OR REPLACE INTO companion_proactive VALUES(?,?,?)",
                                  (self.owner, self.pet, int(enabled)))
            self.proactive_enabled = enabled
            self.activity()

    def take_proactive(self, context):
        now = self.clock()
        local = datetime.fromtimestamp(now)
        idle = context.get("idle_seconds")
        available = context.get("text_allowed") is True or (
            context.get("listening") is True and context.get("speech_allowed") is True)
        if (not self.proactive_enabled or now < self.proactive_after or not 7 <= local.hour < 23 or not self.allows_background() or
                not available or context.get("busy") is not False or
                type(idle) not in (int, float) or not 0 <= idle < 60):
            return None
        day_start = local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        with self.store.tx():
            if not self.proactive_enabled or now < self.proactive_after or not self.allows_background():
                return None
            if self.store.db.execute("""SELECT 1 FROM companion_actions WHERE owner=? AND pet=?
                AND kind IN ('focus','reminder') AND status='pending' AND due<=? AND expires>? LIMIT 1""",
                (self.owner, self.pet, now, now)).fetchone():
                return None
            claimed = self.store.db.execute("""SELECT kind FROM companion_actions WHERE owner=? AND pet=?
                AND kind IN ('proactive','weather') AND started>=?""", (self.owner, self.pet, day_start)).fetchall()
            if len(claimed) >= len(PROACTIVE_LINES):
                return None
            kind, source, reason = "proactive", None, "陪伴问候"
            text, japanese = PROACTIVE_LINES[len(claimed)]
            open_topic = str(context.get("open_loop") or "").strip()
            if open_topic and len(claimed) == 0:
                reason = "未完话题"
                text = "对了，之前你提到的「" + open_topic[:28] + "」，后来进展顺利吗？"
                japanese = "そういえば、前に話していたこと、その後どうなった？"
            forecast = context.get("weather")
            if forecast in ("下雨", "雷雨", "下雪") and not any(row["kind"] == "weather" for row in claimed):
                history = self.store.history(self.owner, self.pet, limit=12)
                source = next((row["id"] for row in reversed(history)
                               if now - 3600 <= row["created"] <= now and row["context_valid"]
                               and row["status"] != "redacted" and OUTING.match(row["text"].strip())), None)
                if source:
                    kind, reason = "weather", "近期出门和当前天气"
                    text = "要出门的话，当地天气显示" + forecast + "，记得先看看外面。"
                    japanese = "外は雪みたい。出かける前に確認してね。" if forecast == "下雪" else "外は雨みたい。出かける前に確認してね。"
            identifier = "auto:" + uuid.uuid4().hex
            expires = now + 30
            self.store.db.execute("""INSERT INTO companion_actions(
                owner,pet,id,activity,started,due,expires,quiet,status,dispatched,kind,title,source_ref)
                VALUES(?,?,?,'',?,?,?,0,'dispatching',?,?,?,?)""",
                (self.owner, self.pet, identifier, now, now, expires, now, kind, text, source))
            self.last_proactive = now
            self.unresponded_proactive = getattr(self, "unresponded_proactive", 0) + 1
            self.proactive_after = now + int(1500 * (1.6 ** min(self.unresponded_proactive - 1, 4)))
            return {"id": identifier, "kind": kind, "title": text, "japanese": japanese, "expires_at": expires, "reason": reason}

    def commit_proactive_message(self, task_id, session, text):
        with self.store.tx():
            row = self._row(task_id)
            now = self.clock()
            if (not row or row["kind"] not in ("proactive", "weather") or row["status"] != "dispatching"
                    or row["display_state"] != "pending" or row["expires"] <= now
                    or self.proactive_activity_at > row["started"] or not self.proactive_enabled
                    or not self.allows_background()):
                return False
            stamp = time.time()
            self.store.db.execute(
                "INSERT INTO turns(owner,pet,id,session,text,reply,status,created,updated,mode) "
                "VALUES(?,?,?,?,'',?,'completed',?,?,'proactive')",
                (self.owner, self.pet, task_id, session, text, stamp, stamp))
            self.store.db.execute("UPDATE companion_actions SET title=?,display_state='requested' "
                "WHERE owner=? AND pet=? AND id=?", (text, self.owner, self.pet, task_id))
            self._log_receipt(task_id, "display", "requested")
            return True

    def take_due(self, special=None):
        now = self.clock()
        with self.store.lock:
            needed = self.store.db.execute("""SELECT 1 FROM companion_actions WHERE owner=? AND pet=?
                AND ((status='pending' AND due<=?) OR (status='dispatching' AND dispatched<=?)) LIMIT 1""",
                (self.owner, self.pet, now, now - RECEIPT_WAIT_SECONDS)).fetchone()
        if not needed and special is None:
            return None, False
        with self.store.tx():
            changed = self.store.db.execute("""UPDATE companion_actions SET status='overdue'
                WHERE owner=? AND pet=? AND status='pending' AND expires<=?""", (self.owner, self.pet, now)).rowcount
            changed += self._mark_display_unconfirmed(now, now - RECEIPT_WAIT_SECONDS)
            row = self.store.db.execute("""SELECT * FROM companion_actions
                WHERE owner=? AND pet=? AND status='pending' AND due<=?
                ORDER BY due LIMIT 1""", (self.owner, self.pet, now)).fetchone()
            if row is None:
                notice = self._claim_special(special, now) if special else None
                return notice, bool(changed or notice)
            self.store.db.execute("""UPDATE companion_actions SET status='dispatching',dispatched=?
                WHERE owner=? AND pet=? AND id=?""", (now, self.owner, self.pet, row["id"]))
            if row["kind"] == "reminder":
                return {"id": row["id"], "kind": "reminder", "title": row["title"]}, True
            return {"id": row["id"], "kind": "focus", "title": "时间到了，休息一下吧。",
                    "japanese": "時間だよ。少し休もう。", "source_turn": row["id"][len("focus:"):]}, True

    def _mark_display_unconfirmed(self, now, cutoff=None):
        criteria = "owner=? AND pet=? AND status='dispatching' AND (? IS NULL OR dispatched<=?)"
        params = (self.owner, self.pet, cutoff, cutoff)
        self.store.db.execute(f"""INSERT OR IGNORE INTO companion_action_receipts
            SELECT owner,pet,id,'display','unconfirmed',? FROM companion_actions
            WHERE {criteria} AND kind IN ('reminder','focus','special')""",
            (now, *params))
        return self.store.db.execute(f"""UPDATE companion_actions SET status='uncertain',display_state='unconfirmed'
            WHERE {criteria}""", params).rowcount

    def _claim_special(self, offer, now):
        if not offer["due"] <= now < offer["expires"] or not self.allows_background() or not 7 <= datetime.fromtimestamp(now).hour < 23:
            return None
        if self.store.db.execute("""SELECT 1 FROM companion_actions
            WHERE owner=? AND pet=? AND kind='special' AND dispatched>? LIMIT 1""",
            (self.owner, self.pet, now - 30)).fetchone():
            return None
        identifier = offer["id"]
        changed = self.store.db.execute("""INSERT OR IGNORE INTO companion_actions(
            owner,pet,id,activity,started,due,expires,quiet,status,dispatched,kind,title,source_ref)
            VALUES(?,?,?,'',?,?,?,0,'dispatching',?,'special',?,?)""",
            (self.owner, self.pet, identifier, now, offer["due"], offer["expires"], now,
             offer["title"], offer["item"])).rowcount
        return {"id": identifier, "kind": "special", "title": offer["title"]} if changed else None

    def receipt(self, task_id, channel, state):
        with self.store.tx():
            row = self._row(task_id)
            if not row or row["dispatched"] is None:
                return False
            if self.store.db.execute("""SELECT 1 FROM companion_action_receipts WHERE owner=? AND pet=?
                   AND id=? AND channel=? AND state=?""",
                   (self.owner, self.pet, task_id, channel, state)).fetchone():
                return False
            if channel == "card" and state == "opened" and row["kind"] == "special":
                return self._log_receipt(task_id, channel, state)
            if channel == "subtitle" and state == "shown":
                if row["audio_state"] not in ("requested", "generated", "playing"):
                    return False
                if row["kind"] in ("proactive", "weather"):
                    self.store.db.execute("""UPDATE companion_actions SET status='notified',display_state='shown',displayed=?
                        WHERE owner=? AND pet=? AND id=?""", (self.clock(), self.owner, self.pet, task_id))
                return self._log_receipt(task_id, channel, state)
            if channel == "display":
                if row["status"] in ("done", "cancelled", "removed", "overdue"):
                    return False
                if state == "shown" and row["display_state"] in ("pending", "requested", "unconfirmed"):
                    status = "notified" if row["status"] in ("dispatching", "uncertain") else row["status"]
                    self.store.db.execute("""UPDATE companion_actions SET status=?,display_state='shown',displayed=?
                        WHERE owner=? AND pet=? AND id=?""", (status, self.clock(), self.owner, self.pet, task_id))
                    return self._log_receipt(task_id, channel, state)
                allowed = {"requested": ("pending",), "unavailable": ("pending", "requested", "unconfirmed")}
                if row["display_state"] not in allowed.get(state, ()):
                    return False
                status = "uncertain" if state == "unavailable" and row["status"] == "dispatching" else row["status"]
                self.store.db.execute("""UPDATE companion_actions SET status=?,display_state=?
                    WHERE owner=? AND pet=? AND id=?""", (status, state, self.owner, self.pet, task_id))
                return self._log_receipt(task_id, channel, state)
            transitions = {
                "pending": ("requested", "skipped", "failed"),
                "requested": ("generated", "playing", "failed", "interrupted"),
                "generated": ("playing", "failed", "interrupted"),
                "playing": ("finished", "failed", "interrupted"),
            }
            if channel == "audio" and state == "generated" and row["audio_state"] == "playing":
                return self._log_receipt(task_id, channel, state)
            if channel != "audio" or state not in transitions.get(row["audio_state"], ()):
                return False
            status = row["status"]
            if row["kind"] in ("proactive", "weather"):
                if state == "finished":
                    status = "done"
                elif state in ("skipped", "failed", "interrupted") and row["display_state"] not in ("requested", "shown"):
                    status = "cancelled"
            self.store.db.execute("UPDATE companion_actions SET audio_state=?,status=? WHERE owner=? AND pet=? AND id=?",
                                  (state, status, self.owner, self.pet, task_id))
            return self._log_receipt(task_id, channel, state)

    def _log_receipt(self, task_id, channel, state):
        self.store.db.execute("INSERT INTO companion_action_receipts VALUES(?,?,?,?,?,?)",
                              (self.owner, self.pet, task_id, channel, state, self.clock()))
        return True

    def receipts(self, task_id):
        with self.store.lock:
            return [dict(row) for row in self.store.db.execute("""SELECT channel,state,at
                FROM companion_action_receipts WHERE owner=? AND pet=? AND id=? ORDER BY at,rowid""",
                (self.owner, self.pet, task_id))]
