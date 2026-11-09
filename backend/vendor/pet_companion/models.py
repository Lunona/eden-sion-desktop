from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math

from pet_memory.types import MemoryError, Scope, dumps, string


class CoreError(MemoryError):
    pass


def require(condition, code, message):
    if not condition:
        raise CoreError(code, message)


EXPRESSIONS = ("neutral", "smile", "thoughtful", "concerned", "sleepy")
MOTIONS = ("idle", "nod", "head_tilt", "wave")
TONES = ("calm", "warm", "gentle", "thoughtful")


def text_list(value, name):
    require(isinstance(value, list), "invalid_profile", f"{name} 必须是文本列表")
    result = [string(v, name, 200) for v in value]
    require(sum(map(len, result)) <= 4000, "invalid_profile", f"{name} 总字数请控制在 4000 以内")
    return result


@dataclass(frozen=True)
class CharacterProfile:
    name: str = "示例角色"
    origin: str = "虚构示例作品"
    self_description: str = "我知道自己来自故事，也知道现在正通过桌宠与你交流。"
    speaking_style: tuple[str, ...] = ("自然简洁", "保留角色自己的语气")
    traits: tuple[str, ...] = ("温和", "认真")
    world_ids: tuple[str, ...] = ("real", "canon:example", "branch:example")
    story_progress: dict = field(default_factory=lambda: {"canon:example": 2})
    knows_origin: bool = True
    canon_entity_id: str = "example-character"
    canon_profile: str = ""

    def __post_init__(self):
        for key in ("speaking_style", "traits", "world_ids"):
            require(isinstance(getattr(self, key), (tuple, list)), "invalid_profile", f"{key} 必须为列表")
        for key, limit in (("name", 128), ("origin", 256), ("self_description", 1500), ("canon_entity_id", 128)):
            object.__setattr__(self, key, string(getattr(self, key), key, limit))
        require(isinstance(self.canon_profile, str) and len(self.canon_profile) <= 4000,
                "invalid_profile", "原作角色卡请控制在 4000 字以内")
        object.__setattr__(self, "canon_profile", self.canon_profile.strip())
        object.__setattr__(self, "speaking_style", tuple(text_list(list(self.speaking_style), "speaking_style")))
        object.__setattr__(self, "traits", tuple(text_list(list(self.traits), "traits")))
        scope = Scope("validation", "validation", self.world_ids)
        object.__setattr__(self, "world_ids", scope.visible_world_ids)
        require(isinstance(self.knows_origin, bool), "invalid_profile", "knows_origin 必须为布尔值")
        require(isinstance(self.story_progress, dict) and all(
            k in self.world_ids and isinstance(v, int) and not isinstance(v, bool) and v >= 0
            for k, v in self.story_progress.items()), "invalid_profile", "剧情进度无效")
        object.__setattr__(self, "story_progress", dict(self.story_progress))

    @classmethod
    def parse(cls, value):
        if isinstance(value, cls):
            return cls(**value.as_dict())
        require(isinstance(value, dict), "invalid_profile", "角色设定须为对象")
        require(not (set(value) - set(cls.__dataclass_fields__)), "invalid_profile", "角色设定包含未知字段")
        for key in ("traits", "speaking_style", "world_ids"):
            if key in value:
                require(isinstance(value[key], (list, tuple)), "invalid_profile", f"{key} 必须为列表")
        try:
            return cls(**value)
        except TypeError:
            raise CoreError("invalid_profile", "角色设定字段格式有误") from None

    def as_dict(self):
        result = asdict(self)
        for key in ("speaking_style", "traits", "world_ids"):
            result[key] = list(result[key])
        return result

    def memory_identity(self):
        return {"name": self.name, "origin": self.origin, "self_description": self.self_description,
                "canon_entity_id": self.canon_entity_id, "knows_origin": self.knows_origin,
                "visible_world_ids": list(self.world_ids), "story_progress": dict(self.story_progress)}


@dataclass(frozen=True)
class ReplyPlan:
    text: str
    expression: str = "neutral"
    motion: str = "idle"
    tone: str = "calm"

    def __post_init__(self):
        object.__setattr__(self, "text", string(self.text, "reply", 8000))
        require(self.expression in EXPRESSIONS, "invalid_plan", "表情不在允许的目录内")
        require(self.motion in MOTIONS, "invalid_plan", "动作不在允许的目录内")
        require(self.tone in TONES, "invalid_plan", "语气标记无效")

    @classmethod
    def parse(cls, value):
        if isinstance(value, cls):
            return value
        require(isinstance(value, dict) and set(value) <= {"text", "expression", "motion", "tone"},
                "invalid_plan", "回复计划包含未授权字段")
        try:
            return cls(**value)
        except TypeError:
            raise CoreError("invalid_plan", "回复计划缺少必要字段") from None

    def as_dict(self):
        return asdict(self)


def finite_number(value, name, low, high):
    require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            and low <= value <= high, "invalid_number", f"{name} 超出范围")
    return float(value)
