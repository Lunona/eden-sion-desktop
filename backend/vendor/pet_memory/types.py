from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import unicodedata


class MemoryError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def require(condition: bool, code: str, message: str):
    if not condition:
        raise MemoryError(code, message)


def string(value, name: str, maximum: int = 16000, allow_empty: bool = False) -> str:
    require(isinstance(value, str), "invalid_input", f"{name} 必须是文本")
    value = value.strip()
    require((bool(value) or allow_empty) and len(value) <= maximum,
            "invalid_input", f"{name} 为空或过长")
    require(not any(ord(c) < 32 and c not in "\n\r\t" for c in value),
            "invalid_input", f"{name} 含无效控制字符")
    return value


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def timestamp(value: str | None = None) -> str:
    if value is None:
        return now()
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(date.tzinfo is not None, "invalid_time", "时间必须包含时区")
        return date.astimezone(timezone.utc).isoformat(timespec="microseconds")
    except (ValueError, TypeError, AttributeError):
        raise MemoryError("invalid_time", "时间须为包含时区的 ISO 8601 格式") from None


def normalized(text: str) -> str:
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", text).casefold())


def fingerprint(text: str) -> str:
    # Punctuation carries factual meaning: -5, 5, 5.0 and 50 must not collapse.
    return hashlib.sha256(canonical_text(text).encode("utf-8")).hexdigest()


def canonical_text(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).strip().casefold())


def terms(text: str) -> list[str]:
    """Identical ingestion/query tokenization; preserves short CJK names."""
    text = unicodedata.normalize("NFKC", text).casefold()
    result = re.findall(r"[a-z0-9_]+", text)
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        result.extend(run[i:i + 2] for i in range(len(run) - 1))
        # Single-character matching is deliberately limited to a single-character query.
        if len(run) == 1:
            result.append(run)
    return list(dict.fromkeys(result))[:256]


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return -1.0
    a = math.sqrt(sum(v * v for v in left))
    b = math.sqrt(sum(v * v for v in right))
    return sum(x * y for x, y in zip(left, right)) / (a * b) if a and b else -1.0


def vector(value) -> list[float]:
    require(isinstance(value, list) and 1 <= len(value) <= 16384,
            "invalid_vector", "向量维度无效")
    require(all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                for v in value), "invalid_vector", "向量包含无效数值")
    require(any(v != 0 for v in value), "invalid_vector", "向量不能全部为零")
    return [float(v) for v in value]


@dataclass(frozen=True)
class Scope:
    owner_id: str
    companion_id: str
    visible_world_ids: tuple[str, ...] = ("real",)
    session_id: str = "default"

    def __post_init__(self):
        for name in ("owner_id", "companion_id", "session_id"):
            object.__setattr__(self, name, string(getattr(self, name), name, 128))
        require(isinstance(self.visible_world_ids, (list, tuple)) and
                1 <= len(self.visible_world_ids) <= 32, "invalid_scope", "须指定可读世界集合")
        worlds = tuple(dict.fromkeys(string(w, "world_id", 128) for w in self.visible_world_ids))
        object.__setattr__(self, "visible_world_ids", worlds)

    @classmethod
    def parse(cls, value):
        if isinstance(value, cls):
            return value
        require(isinstance(value, dict), "invalid_scope", "缺少宿主提供的访问范围")
        try:
            return cls(**value)
        except TypeError:
            raise MemoryError("invalid_scope", "范围字段不正确") from None

    def as_dict(self):
        return {"owner_id": self.owner_id, "companion_id": self.companion_id,
                "visible_world_ids": list(self.visible_world_ids), "session_id": self.session_id}
