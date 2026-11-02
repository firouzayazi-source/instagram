"""موتور قانون‌ها: کدام قانون به این رویداد می‌خورد و چه پاسخی می‌دهد."""
import re
import time
from dataclasses import dataclass

from .normalize import normalize

MATCHES = ("any", "exact", "contains", "starts_with", "regex")


@dataclass
class Incoming:
    channel: str          # comment | dm
    user_id: str
    text: str
    media_id: str | None = None   # فقط برای کامنت
    is_follower: bool | None = None
    source: str = ""      # دایرکت: story_reply (جواب به استوری) | mention (منشن در استوری) | icebreaker | ""


def trigger_matches(trigger: dict, text_norm: str) -> bool:
    m = trigger.get("match", "any")
    v = normalize(trigger.get("value", ""))
    if m == "any":
        return True
    if not v:
        return False
    if m == "exact":
        return text_norm == v
    if m == "contains":
        return v in text_norm
    if m == "starts_with":
        return text_norm.startswith(v)
    if m == "regex":
        try:
            return re.search(trigger.get("value", ""), text_norm) is not None
        except re.error:
            return False
    return False


def rule_matches(rule: dict, inc: Incoming, last_hit_at: float | None, now: float | None = None) -> bool:
    now = now or time.time()
    chs = rule["channels"]
    if inc.source == "mention":                 # منشن متن ندارد؛ فقط دستورهای مخصوص منشن
        if "mention" not in chs:
            return False
    elif inc.source == "story_reply":           # جواب به استوری هم دایرکت است
        if "story_reply" not in chs and "dm" not in chs:
            return False
    elif inc.channel not in chs:
        return False
    scope = rule["post_scope"]
    if inc.channel == "comment" and scope != "all" and inc.media_id not in scope:
        return False
    adv = rule.get("advanced", {})
    if adv.get("once_per_user") and last_hit_at is not None:
        return False
    cooldown = adv.get("cooldown_seconds")
    if cooldown and last_hit_at is not None and now - last_hit_at < cooldown:
        return False
    hours = adv.get("active_hours")  # [start, end] به وقت محلی سرور، مثل [9, 23]
    if hours:
        h = time.localtime(now).tm_hour
        start, end = hours
        inside = start <= h < end if start <= end else (h >= start or h < end)
        if not inside:
            return False
    text_norm = normalize(inc.text)
    return any(trigger_matches(t, text_norm) for t in rule["triggers"])


def pick(replies: list[str], use_count: int) -> str | None:
    """چرخش بین متن‌ها تا پاسخ‌ها تکراری نباشند."""
    if not replies:
        return None
    return replies[use_count % len(replies)]


def find_rule(rules: list[dict], inc: Incoming, last_hit_lookup) -> dict | None:
    """اولین قانون منطبق به ترتیب اولویت. last_hit_lookup(rule_id, user_id) -> float|None"""
    for rule in rules:
        if rule_matches(rule, inc, last_hit_lookup(rule["id"], inc.user_id)):
            return rule
    return None
