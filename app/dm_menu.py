"""منوی ثابت دایرکت: دکمه‌هایی که همیشه کنار نوار نوشتن دایرکت پیج دیده می‌شوند.

هر دکمه یا لینک باز می‌کند (مثل ربات تلگرام یا سایت) یا یک متن آماده می‌فرستد. لمس دکمه‌ی متنی در وبهوک
postback با MENU:<شماره> می‌آید و در خوانش Composio معمولاً به‌صورت پیامی با همان عنوان؛ هر دو جواب
همان متن را می‌گیرند، حتی وقتی جواب خودکار دایرکت خاموش است (چون صاحب پیج خودش این متن را تعیین کرده).
"""
import json

from . import db
from .normalize import normalize

KEY = "dm_menu"
MAX_ITEMS = 5
TITLE_MAX = 30


def load(c) -> list[dict]:
    try:
        return json.loads(db.kv_get(c, KEY) or "[]")
    except ValueError:
        return []


def clean(items) -> list[dict]:
    out = []
    for x in (items or [])[:MAX_ITEMS]:
        title = str((x or {}).get("title", "")).strip()[:TITLE_MAX]
        kind = "url" if x.get("type") == "url" else "text"
        value = str(x.get("value", "")).strip()[:1000]
        if not title and not value:
            continue
        if not title or not value:
            raise ValueError("هر دکمه هم عنوان لازم دارد هم " + ("لینک" if kind == "url" else "متن جواب"))
        if kind == "url" and not value.startswith("https://"):
            raise ValueError(f"لینک دکمه‌ی «{title}» باید با https:// شروع شود")
        out.append({"title": title, "type": kind, "value": value})
    return out


def save(c, items) -> list[dict]:
    items = clean(items)
    db.kv_set(c, KEY, json.dumps(items, ensure_ascii=False))
    return items


def reply_for(c, payload: str, text: str) -> str | None:
    """متن جواب لمس یکی از دکمه‌های متنی؛ None اگر این پیام از منو نیامده."""
    items = load(c)
    if payload.startswith("MENU:"):
        try:
            x = items[int(payload[5:])]
            return x["value"] if x["type"] == "text" else None
        except (ValueError, IndexError):
            return None
    t = normalize((text or "").strip())
    for x in items:
        if x["type"] == "text" and t and normalize(x["title"]) == t:
            return x["value"]
    return None
