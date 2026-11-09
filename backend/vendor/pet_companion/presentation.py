from __future__ import annotations

import heapq
import threading
import time

from .models import EXPRESSIONS, MOTIONS, ReplyPlan, finite_number, require


class PresentationScheduler:
    """A cancellable, single-character timeline. Does not load or replace art."""
    def __init__(self, *, expressions=EXPRESSIONS, motions=MOTIONS, clock=time.monotonic):
        require(bool(expressions) and "neutral" in expressions and set(expressions) <= set(EXPRESSIONS),
                "invalid_catalog", "表情目录须含 neutral 且全部为已知项")
        require(bool(motions) and "idle" in motions and set(motions) <= set(MOTIONS),
                "invalid_catalog", "动作目录须含 idle 且全部为已知项")
        self.expressions, self.motions, self.clock = set(expressions), set(motions), clock
        self.lock = threading.RLock()
        self.queue = []
        self.counter = 0
        self.active = None
        self.audio = False
        self.segment = -1

    def _cue(self, at, kind, payload):
        self.counter += 1
        heapq.heappush(self.queue, (at, self.counter, kind, payload))

    def start(self, turn_id, plan, generation):
        plan = ReplyPlan.parse(plan)
        with self.lock:
            cancelled = self.cancel("replacement")
            expression = plan.expression if plan.expression in self.expressions else "neutral"
            motion = plan.motion if plan.motion in self.motions else "idle"
            self.active = {"turn_id": turn_id, "generation": generation}
            self.audio = False
            self.segment = -1
            started = self.clock()
            duration = max(0.8, min(12.0, len(plan.text) / 18))
            self._cue(started, "presentation.started", {"text_only": True, "duration_estimate": duration})
            self._cue(started, "gaze.set", {"target": "user"})
            self._cue(started, "expression.set", {"name": expression})
            self._cue(started, "mouth.level", {"level": 0.0, "source": "no_audio"})
            if motion != "idle":
                self._cue(started + 0.12, "motion.play", {"name": motion})
                self._cue(started + min(1.2, duration * 0.7), "motion.stop", {"name": motion})
            self._cue(started + duration, "presentation.completed", {})
            return cancelled

    def tick(self):
        with self.lock:
            events = []
            while self.queue and self.queue[0][0] <= self.clock() and self.active:
                _, _, kind, payload = heapq.heappop(self.queue)
                base = dict(self.active)
                if kind == "presentation.completed":
                    events.extend([{**base, "type": "mouth.level", "payload": {"level": 0.0, "source": "ended"}},
                                   {**base, "type": "motion.stop", "payload": {"name": "all"}},
                                   {**base, "type": "expression.set", "payload": {"name": "neutral"}}])
                    self.active = None
                    self.audio = False
                    self.queue.clear()
                events.append({**base, "type": kind, "payload": payload})
            return events

    def cancel(self, reason="interrupted"):
        with self.lock:
            self.queue.clear()
            if not self.active:
                return []
            base = dict(self.active)
            events = [{**base, "type": "presentation.cancelled", "payload": {"reason": reason}},
                      {**base, "type": "motion.stop", "payload": {"name": "all"}},
                      {**base, "type": "mouth.level", "payload": {"level": 0.0, "source": "cancelled"}},
                      {**base, "type": "expression.set", "payload": {"name": "neutral"}}]
            if self.audio:
                events.append({**base, "type": "audio.stop", "payload": {}})
            self.active = None
            self.audio = False
            return events

    def audio_started(self, turn_id, generation, duration, segment=0):
        duration = finite_number(duration, "duration", 0.05, 120)
        require(isinstance(segment, int) and not isinstance(segment, bool) and segment >= 0, "invalid_segment", "音频分段序号无效")
        with self.lock:
            if not self.active or self.active != {"turn_id": turn_id, "generation": generation}:
                return []
            if segment <= self.segment:
                return []
            self.segment = segment
            self.audio = True
            self.queue = [e for e in self.queue if e[2] != "presentation.completed"]
            heapq.heapify(self.queue)
            self._cue(self.clock() + duration, "presentation.completed", {})
            return [{**self.active, "type": "audio.clock", "payload": {"duration": duration, "segment": segment, "source": "host_playback_ack"}}]

    def mouth(self, turn_id, generation, level, segment=0):
        level = finite_number(level, "mouth_level", 0, 1)
        with self.lock:
            if not self.active or not self.audio or segment != self.segment or self.active != {"turn_id": turn_id, "generation": generation}:
                return []
            return [{**self.active, "type": "mouth.level", "payload": {"level": level, "segment": segment, "source": "host_audio"}}]

    def status(self):
        with self.lock:
            return {"active": dict(self.active) if self.active else None, "audio": self.audio, "pending_cues": len(self.queue)}
