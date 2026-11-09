"""Evidence rules for durable memory and interaction preferences."""
import re
from datetime import datetime, timedelta, timezone

from pet_memory.types import normalized


TEMPORAL = re.compile(r"^(?:我)?(?:今天|今晚|现在|这会儿|这次|刚才|这几天|这段时间|目前|暂时)")
FOCUS = r"(?:做题|学习|复习|写作|工作|开会|专注)"
QUIET = r"(?:别|不要|不用|请勿|不必)(?:再)?(?:主动找我|主动搭话|主动联系我|打扰我|打断我|主动打断我)"
ALLOW = r"(?:可以|允许)(?:再)?(?:主动找我|主动搭话|主动联系我)"
FOCUS_PREFERENCE = re.compile(
    rf"^(?:请)?(?:以后|今后|平时|往后)[，,\s]*(?:我)?(?P<activity>{FOCUS})(?:的时候|期间|时)?[，,\s]*"
    rf"(?:都)?(?:请)?(?P<instruction>{QUIET}|{ALLOW})$"
)
STABLE_QUIET = re.compile(rf"^我(?:不喜欢|不希望)(?P<activity>{FOCUS})(?:的时候|期间|时)?(?:被)?(?:主动)?(?:打断|打扰)$")
AFFINITY = re.compile(r"^我(?:平时|一直|更)?(?P<verb>不喜欢|喜欢|偏好)(?P<object>[^。！？?!\n，,；;]{1,80})$")
IDENTITY = re.compile(r"^我(?:的名字是|叫)([^，,。！!?？\n]{1,32})$")
SHARED = re.compile(r"^(?:今天|昨天|前天|上周|刚才)?(?:我们|你和我)(?:刚才)?(?:一起)?(?:完成了|做完了|讨论了|聊了|去了|看了)")
PLAN = re.compile(r"^(?:我们(?:已经)?约定|我(?:们)?的约定是|约好了)[：:，,\s]*\S")
IMPERATIVE = re.compile(r"提醒我|期间(?:请)?(?:别|不要)|^我先|^先别|^[别不]要|半小时后")


def structured(kind, quote, **fields):
    return {"quote": quote, "kind": kind, "subject": "user", **fields}


def temporary_until(event):
    if not event.get("occurred_at"):
        return {}
    occurred = datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00"))
    local = occurred.astimezone()
    if re.match(r"^(?:我)?(?:今天|今晚)", event["text"].strip()):
        end = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        end = occurred + timedelta(hours=2)
    return {"expires_at": end.astimezone(timezone.utc).isoformat()}


def local_candidates(event, rules, explicit):
    if event["role"] != "user":
        return rules.extract(event) if event["role"] in {"document", "host"} else []
    quote = explicit if explicit is not None else event["text"].strip()
    text = quote.rstrip("。！! ")
    if not text or re.search(r"[?？]", text):
        return []
    stable = FOCUS_PREFERENCE.fullmatch(text)
    quiet_statement = STABLE_QUIET.fullmatch(text)
    if stable or quiet_statement:
        allows = stable and re.fullmatch(ALLOW, stable["instruction"])
        return [structured("preference", quote, predicate="proactive_focus",
                           qualifiers={"activity": (stable or quiet_statement)["activity"]},
                           value="normal" if allows else "quiet")]
    if SHARED.match(text):
        return [structured("episode", quote)]
    if IMPERATIVE.search(text):
        return []
    if TEMPORAL.match(text):
        return [structured("temporary", quote, **temporary_until({**event, "text": text}))]
    match = AFFINITY.fullmatch(text)
    if match:
        target = normalized(match["object"].strip())
        if target:
            return [structured("preference", quote, predicate="affinity",
                               qualifiers={"object": target},
                               value="dislike" if match["verb"] == "不喜欢" else "like")]
    match = IDENTITY.fullmatch(text)
    if match:
        return [structured("preference", quote, predicate="preferred_name", value=match[1].strip())]
    if PLAN.match(text):
        return [structured("plan", quote)]
    fallback = rules.extract({**event, "text": quote})
    if fallback and fallback[0].get("predicate") == "preferred_name":
        return fallback
    return [structured("note", quote)] if explicit is not None else []


def question_quote(text,quote):
    start=text.find(quote)
    if start<0:return False
    if re.search(r'[？?]',quote):return True
    if quote.rstrip().endswith(('。','！','!')) or quote.endswith('\n'):return False
    tail=text[start+len(quote):]
    if re.match(r'^[，,；;]\s*(?:你呢|你觉得|你怎么看|你也|你会|你喜欢)',tail):
        return False
    ending=re.search(r'[。！？!?\n]',tail)
    clause=quote+(tail[:ending.start()] if ending else tail)
    return bool(ending and ending.group() in '？?') or clause.rstrip().endswith(('吗','么'))


def unasserted_quote(source,quote):
    start=source.find(quote)
    if start<0 or question_quote(source,quote):return True
    prefix=source[:start]
    return (any(word in prefix for word in ('假设','假如','如果','例如','比如','他说','她说','你说','助手说'))
            or any(prefix.count(left)>prefix.count(right) for left,right in [('“','”'),('「','」')])
            or prefix.count(chr(34))%2!=0)


def remote_candidate(event, quote, kind, subject, score=0.6):
    # High-confidence model extractions enter active memory directly unless they
    # conflict with an existing single-predicate fact (which core.py gates as candidate).
    if TEMPORAL.match(event["text"].strip()) or TEMPORAL.match(quote.strip()) or IMPERATIVE.search(quote):
        return None
    return {"quote": quote, "kind": kind, "subject": subject, "review_required": float(score) < 0.35}


def memory_category(item):
    layer, kind = item["knowledge_layer"], item["kind"]
    reading = item.get("qualifiers", {}).get("reading_note")
    if reading == "excerpt":
        return "reading_excerpt"
    if reading == "interpretation":
        return "reading_interpretation"
    if layer == "canon":
        return "canon"
    if layer == "story_branch":
        return "virtual_life"
    if kind == "temporary":
        return "temporary"
    if kind == "plan":
        return "pending_task"
    if kind == "episode" and layer == "shared_experience" and (
            item["verification"] == "host_verified" or SHARED.match(item["text"])):
        return "shared_episode"
    return "fact_preference"
