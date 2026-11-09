"""Conservative offline extraction. Complex understanding is an optional provider."""
from __future__ import annotations

import re


class RuleExtractor:
    def extract(self, event: dict) -> list[dict]:
        text = event["text"].strip()
        if not text or event["role"] == "assistant":
            return []
        if event["role"] == "document":
            # A host explicitly submitting a document chooses its world/layer.
            return [{"quote": text[:16000], "kind": "episode", "subject": "companion"}]
        if event["role"] == "host":
            return [{"quote": text[:16000], "kind": "episode", "subject": "companion"}]
        # Never interpret a quoted example as a control request or personal profile.
        if text.startswith(("“", "\"", "「", "例如", "比如", "假如", "假设", "如果", "你觉得")):
            return []
        explicit = re.match(r"^(?:请)?(?:帮我)?记住[：:，,\s]*(.+)$", text, re.S)
        if explicit:
            quote = explicit.group(1).strip()
            return [{"quote": quote, "kind": "note", "subject": "user"}]
        name = re.fullmatch(r"(?:请|以后|今后)?(?:叫我|称呼我)([^。！？\n]{1,40})[。！]?", text)
        if name:
            return [{"quote": text, "kind": "preference", "subject": "user",
                     "predicate": "preferred_name", "value": name.group(1).strip(" ，,！!。") }]
        if re.fullmatch(r"我(?:今天|现在|有点|这会儿)(?:很|有点|觉得)?(?:累|疲惫|难过|不舒服|想安静(?:一会儿)?)[。！]?", text):
            return [{"quote": text, "kind": "temporary", "subject": "user"}]
        if re.fullmatch(r"我(?:现在|平时|一直|更)?(?:喜欢|不喜欢|偏好)([^。！？\n]{1,200})[。！]?", text):
            return [{"quote": text, "kind": "preference", "subject": "user"}]
        if re.match(r"^(?:今天|昨天|前天|上周|刚才)?(?:我|我们)(?:一起)?(?:完成了|做完了|讨论了|聊了|去了|看了)", text):
            return [{"quote": text[:4000], "kind": "episode", "subject": "user"}]
        return []
