"""دانش مشترک اینستاگرام و تلگرام: نیت‌ها (faq.json) و متن بخش‌ها (data.json) ربات تلگرام.

یک بار در پنل وارد می‌شود و هر دو پلتفرم با همان جواب می‌دهند. خواندن مستقیم از فایل‌های
ربات تلگرام است؛ نوشتن از راه پوشه‌ی inbox که خود ربات تلگرام اعمال می‌کند (تنها نویسنده).
"""
import json
import os
import re
import secrets
import time
from pathlib import Path

from . import brain_engine, config

# بخش‌هایی که متنشان از پنل ویرایش می‌شود (کلیدها همان ربات تلگرام)
SECTIONS = {"5": "آدرس فروشگاه", "3": "شرایط اقساط", "4": "پشتیبانی و تماس", "2": "سایت", "1": "شبکه‌های اجتماعی",
            "welcome": "خوش‌آمدگویی تلگرام"}
ACTIONS = {"": "فقط همین متن", "prices": "جستجو در فهرست کالای سایت", "hours": "ساعت کاری",
           "human": "سپردن به همکار", "notify": "خبر دادن وقتی کالا رسید", "specs": "مشخصات فنی آیفون",
           "compare": "مقایسه‌ی آیفون‌ها", **{f"section:{k}": f"نمایش «{v}»" for k, v in SECTIONS.items() if k != "welcome"}}
_ID = re.compile(r"^[A-Za-z0-9_]{1,40}$")
STALE_SECONDS = 30


def inbox() -> Path:
    return Path(config.TG_DATA_DIR) / "inbox"


def ready() -> bool:
    """دانش مشترک فقط وقتی هست که ربات تلگرام روی همین سرور داده‌اش را دارد."""
    return (Path(config.TG_DATA_DIR) / "faq.json").exists()


def intents() -> list[dict]:
    out = []
    for x in brain_engine._load_json("faq.json", []):
        if not isinstance(x, dict) or not x.get("id"):
            continue
        out.append({"id": x["id"], "keys": x.get("keys") or [], "examples": x.get("examples") or [],
                    "answer": x.get("answer") or "", "action": x.get("action") or "",
                    "enabled": x.get("enabled", True), "hits": x.get("hits", 0), "builtin": not x["id"].startswith("p_")})
    return out


def sections() -> list[dict]:
    """به ترتیب SECTIONS (فهرست، چون کلیدهای عددی در جاوااسکریپت جابه‌جا مرتب می‌شوند)."""
    d = brain_engine._load_json("data.json", {})
    d = d if isinstance(d, dict) else {}
    return [{"key": k, "title": v, "text": d.get(k, "")} for k, v in SECTIONS.items()]


def pending() -> dict:
    """تغییرهایی که ربات تلگرام هنوز برنداشته. کهنه یعنی ربات تلگرام خاموش است."""
    try:
        files = [f for f in inbox().iterdir() if f.suffix == ".json"]
    except FileNotFoundError:
        return {"count": 0, "stale": False}
    oldest = min((f.stat().st_mtime for f in files), default=time.time())
    return {"count": len(files), "stale": bool(files) and time.time() - oldest > STALE_SECONDS}


def _queue(op: dict) -> None:
    if not ready():
        raise ValueError("دانش مشترک در دسترس نیست: ربات تلگرام هنوز روی این سرور منتقل نشده")
    d = inbox()
    d.mkdir(parents=True, exist_ok=True)
    name = f"{time.time_ns()}-{secrets.token_hex(3)}.json"
    tmp = d / (name + ".tmp")
    tmp.write_text(json.dumps(op, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, d / name)   # ربات تلگرام فقط فایل کامل‌شده‌ی .json را می‌بیند


def _lines(v) -> list[str]:
    if isinstance(v, str):
        v = re.split(r"[\n,،]+", v)
    return [str(x).strip()[:300] for x in (v or []) if str(x).strip()][:80]


def save_intent(item: dict) -> None:
    iid = str(item.get("id") or "")
    if iid and not _ID.match(iid):
        raise ValueError("شناسه‌ی نامعتبر")
    action = str(item.get("action") or "")
    if action not in ACTIONS:
        raise ValueError("کار نامعتبر")
    keys, examples = _lines(item.get("keys")), _lines(item.get("examples"))
    answer = str(item.get("answer") or "").strip()[:4000]
    if not keys and not examples:
        raise ValueError("دست‌کم یک کلیدواژه یا جمله‌ی نمونه لازم است")
    if not answer and not action:
        raise ValueError("متن جواب یا یک کار لازم است")
    _queue({"op": "intent_upsert", "item": {"id": iid, "keys": keys, "examples": examples, "answer": answer,
                                            "action": action, "enabled": bool(item.get("enabled", True))}})


def delete_intent(iid: str) -> None:
    if not _ID.match(iid or ""):
        raise ValueError("شناسه‌ی نامعتبر")
    _queue({"op": "intent_delete", "id": iid})


def save_section(key: str, text: str) -> None:
    if key not in SECTIONS:
        raise ValueError("بخش ناشناخته")
    _queue({"op": "section_set", "key": key, "text": str(text or "")[:4000]})


def prompt_text(limit: int = 60) -> str:
    """دانش مشترک برای پرامپت هوش مصنوعی: بخش‌ها و جواب نیت‌ها (نسخه‌ی اول هر جواب)."""
    parts = []
    for v in sections():
        if v["key"] != "welcome" and v["text"].strip():
            parts.append(f"[{v['title']}]\n{brain_engine._plain(v['text'])}")
    for it in intents()[:limit]:
        if not it["enabled"] or not it["answer"].strip():
            continue
        first = brain_engine._plain(it["answer"].split("\n---\n")[0]).replace("{product}", "").replace("{name}", "")
        topic = "، ".join((it["keys"] or it["examples"])[:4])
        parts.append(f"[{topic}]\n{first.strip()}")
    return "\n\n".join(parts)
