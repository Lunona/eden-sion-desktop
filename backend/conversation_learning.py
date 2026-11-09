"""User-confirmed conversation habits backed by completed turns."""
from datetime import datetime
import re


RULES = {
    "brief": ("length", "日常回答简洁", "普通问题先简短回答，需要时再展开。",
              r"(?:回复|回答|说话)(?:要|尽量|可以)?(?:简短|简洁|短|精简)(?:一点|一些|些)?"),
    "detailed": ("length", "日常回答详细", "默认给出足够细节，复杂问题说明依据。",
                 r"(?:回复|回答|解释)(?:要|尽量|可以)?(?:详细|具体|多写)(?:一点|一些|些)?"),
    "plain": ("emoji", "少用表情符号", "文字回复少用表情符号。",
              r"(?:少用|不要用|别用|不用)(?:表情符号|emoji)"),
    "direct": ("opening", "先回答问题", "先回答当前问题，再补必要的解释。",
               r"(?:先|直接)(?:回答|回复)(?:我的|当前的)?问题"),
}


def evidence(row, key):
    if not row or row["status"] != "completed" or not row["context_valid"]:
        return None
    text = row["text"].strip().rstrip("。！! ")
    pattern = RULES[key][3]
    prefix = r"(?:(?:以后|今后|平时)[，, ]*)?(?:(?:请|我希望你|我喜欢你|我希望|我喜欢)[，, ]*)?"
    if not re.fullmatch(prefix + pattern, text, flags=re.I):
        return None
    return {"id": row["id"], "day": datetime.fromtimestamp(row["created"]).date().isoformat(), "quote": row["text"]}


def observations(rows, key):
    days = {}
    for row in rows:
        sample = evidence(row, key)
        if sample:
            days[sample["day"]] = sample
    return list(days.values())[-8:]


class ConversationLearning:
    def __init__(self, runtime, presence):
        self.runtime = runtime
        self.presence = presence

    def _history(self):
        r = self.runtime
        with r.lock:
            r._reconcile_deleted_context()
            return r.store.history(r.owner, r.pet, limit=200)

    def active(self):
        r = self.runtime
        with r.lock:
            r._reconcile_deleted_context()
            with self.presence.lock:
                approved = dict(self.presence.data["learning"])
            result = {}
            for key, sources in approved.items():
                if key not in RULES or not isinstance(sources, list) or not all(isinstance(x, str) for x in sources):
                    continue
                rows = [r.store.turn(r.owner, r.pet, source) for source in sources[:8]]
                proof = observations(rows, key)
                if len(proof) >= 3:
                    result[key] = proof
            return result

    def status(self):
        rows = self._history()
        active = self.active()
        items = []
        for key, (_, title, _, _) in RULES.items():
            proof = active.get(key) or observations(rows, key)
            if proof:
                items.append({"key": key, "title": title, "evidence": proof,
                              "days": len(proof), "active": key in active})
        return items

    def review(self, key, enabled):
        if key not in RULES or not isinstance(enabled, bool):
            raise ValueError("学习规则无效")
        proof = observations(self._history(), key) if enabled else []
        if enabled and len(proof) < 3:
            raise ValueError("这条习惯需要三天的独立发言作为依据")
        with self.presence.lock:
            approved = self.presence.data["learning"]
            if enabled:
                for old in tuple(approved):
                    if old in RULES and RULES[old][0] == RULES[key][0]:
                        approved.pop(old)
                approved[key] = [sample["id"] for sample in proof]
            else:
                approved.pop(key, None)
            self.presence.save()
        return self.status()

    def guidance(self):
        return [RULES[key][2] for key in self.active()]
