from __future__ import annotations

import math
import re
import time

from .models import require


class CharacterState:
    """Short-lived affect, separated from persistent character traits."""
    def __init__(self, store, owner, pet, clock=time.time):
        self.store, self.owner, self.pet, self.clock = store, owner, pet, clock

    def snapshot(self):
        raw = self.store.state(self.owner, self.pet) or {
            "valence": 0.0, "arousal": 0.25, "energy": 0.65,
            "completed_turns": 0, "updated_at": self.clock(), "last_signal": "neutral"}
        elapsed = max(0.0, self.clock() - raw["updated_at"])
        affect_decay = math.exp(-math.log(2) * elapsed / 1800)
        energy_decay = math.exp(-math.log(2) * elapsed / 3600)
        result = dict(raw)
        result["valence"] *= affect_decay
        result["arousal"] = 0.25 + (result["arousal"] - 0.25) * affect_decay
        result["energy"] = 0.65 + (result["energy"] - 0.65) * energy_decay
        result["updated_at"] = self.clock()
        if result["energy"] < 0.28:
            mood = "tired"
        elif result["valence"] < -0.12:
            mood = "concerned"
        elif result["valence"] > 0.15:
            mood = "joyful"
        elif result["arousal"] > 0.55:
            mood = "focused"
        else:
            mood = "calm"
        result["mood"] = mood
        result["familiarity"] = "初识" if result["completed_turns"] < 10 else "逐渐熟悉" if result["completed_turns"] < 50 else "熟悉"
        return result

    @staticmethod
    def classify(text):
        if text.startswith(("“", '"', "例如", "假如", "如果", "比如")):
            return "neutral"
        if re.search(r"^(?:谢谢|辛苦你了|太好了|终于完成了)", text):
            return "celebrate"
        if re.search(r"^我(?:今天|现在|这会儿)?(?:很|有点|觉得)?(?:难过|伤心|累|不舒服|担心)", text):
            return "comfort"
        if text in {"先安静一会儿", "我想专心做事", "我要专心工作"}:
            return "focus"
        return "neutral"

    def apply(self, signal, event_id, *, completed=False):
        require(signal in {"neutral", "celebrate", "comfort", "focus", "rest"}, "invalid_signal", "状态信号无效")
        with self.store.lock:
            current = self.snapshot()
            if signal == "celebrate":
                current["valence"] += 0.20
                current["arousal"] += 0.08
            elif signal == "comfort":
                current["valence"] -= 0.18
                current["arousal"] += 0.06
            elif signal == "focus":
                current["arousal"] += 0.35
            elif signal == "rest":
                current["energy"] += 0.15
                current["arousal"] -= 0.10
            if completed:
                current["completed_turns"] += 1
                current["energy"] -= 0.008
            current["valence"] = min(0.8, max(-0.8, current["valence"]))
            current["arousal"] = min(0.9, max(0.1, current["arousal"]))
            current["energy"] = min(1.0, max(0.1, current["energy"]))
            current["last_signal"] = signal
            current.pop("mood", None)
            current.pop("familiarity", None)
            self.store.save_state(self.owner, self.pet, current, event_id)
            return self.snapshot()
