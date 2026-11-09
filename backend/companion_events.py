"""Bounded, metadata-only observations of the host and renderer."""
import sqlite3
import threading
import time
from pathlib import Path


EVENTS = frozenset({
    "input.accepted", "touch.pressed", "screen.captured", "reminder.due",
    "special.revealed", "notice.submitted", "notice.shown",
    "reply.generated", "reply.displayed", "reply.failed", "turn.cancelled", "presentation.cancelled",
    "audio.requested", "audio.generated", "caption.displayed", "audio.started",
    "audio.finished", "audio.failed", "audio.interrupted", "card.opened", "proactive.due", "weather.due",
    "tool.approved", "tool.confirmed", "tool.submitted",
    "tool.unconfirmed", "tool.cancelled", "tool.failed",
})
SOURCES = frozenset({"text", "voice", "touch", "screen", "timer", "host", "renderer", "tool"})


class EventJournal:
    def __init__(self, path, *, clock=time.time, max_events=None):
        self.clock = clock
        self.lock = threading.Lock()
        self.db = sqlite3.connect(Path(path), check_same_thread=False, timeout=.15)
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.max_events = max_events
        self.since_prune = 0
        with self.db:
            self.db.execute(
                """CREATE TABLE IF NOT EXISTS observations(
                    id TEXT PRIMARY KEY, at REAL NOT NULL, kind TEXT NOT NULL,
                    source TEXT NOT NULL, turn_id TEXT, generation INTEGER,
                    progress INTEGER
                )"""
            )
            self._prune()
        self.duplicates = 0
        self.conflicts = 0

    def record(self, event_id, kind, source, *, turn_id=None, generation=None, progress=None):
        if (kind not in EVENTS or source not in SOURCES or
                not isinstance(event_id, str) or not 1 <= len(event_id) <= 200):
            raise ValueError("无效的陪伴事件")
        if turn_id is not None and (not isinstance(turn_id, str) or not 1 <= len(turn_id) <= 128):
            raise ValueError("无效的轮次")
        for value in (generation, progress):
            if value is not None and (type(value) is not int or not 0 <= value <= 2**31 - 1):
                raise ValueError("无效的事件进度")
        fields = (kind, source, turn_id, generation, progress)
        with self.lock, self.db:
            existing = self.db.execute(
                "SELECT kind,source,turn_id,generation,progress FROM observations WHERE id=?", (event_id,)
            ).fetchone()
            if existing is not None:
                if existing == fields:
                    self.duplicates += 1
                    return "duplicate"
                self.conflicts += 1
                return "conflict"
            self.db.execute(
                "INSERT INTO observations VALUES(?,?,?,?,?,?,?)", (event_id, self.clock(), *fields)
            )
            if self.max_events is not None:
                self.since_prune += 1
                if self.since_prune >= min(self.max_events, 128):
                    self._prune()
            return "recorded"

    def _prune(self):
        if self.max_events is not None:
            self.db.execute("""DELETE FROM observations WHERE rowid <=
                (SELECT rowid FROM observations ORDER BY rowid DESC LIMIT 1 OFFSET ?)""", (self.max_events,))
            self.since_prune = 0

    def summary(self):
        with self.lock:
            counts = dict(self.db.execute("SELECT kind,count(*) FROM observations GROUP BY kind"))
            by_source = dict(self.db.execute(
                "SELECT source,count(*) FROM observations WHERE kind='input.accepted' GROUP BY source"
            ))
            gaps = self.db.execute(
                """SELECT count(*) FROM observations AS output
                   WHERE output.turn_id IS NOT NULL
                     AND output.kind IN ('reply.generated','reply.displayed','screen.captured','audio.started')
                     AND NOT EXISTS (
                        SELECT 1 FROM observations AS input
                        WHERE input.kind='input.accepted' AND input.turn_id=output.turn_id
                     )"""
            ).fetchone()[0]
            open_dialogues = self.db.execute(
                """SELECT count(*) FROM observations AS input
                   WHERE input.kind='input.accepted' AND input.id LIKE 'input:%'
                     AND NOT EXISTS (
                        SELECT 1 FROM observations AS output
                        WHERE output.kind IN ('reply.displayed','reply.failed','turn.cancelled')
                          AND output.turn_id=input.turn_id
                     )"""
            ).fetchone()[0]
            return {"counts": counts, "inputs": by_source, "duplicates": self.duplicates,
                    "conflicts": self.conflicts, "outputsWithoutInput": gaps,
                    "openDialogues": open_dialogues}

    def close(self):
        with self.lock:
            self.db.close()
