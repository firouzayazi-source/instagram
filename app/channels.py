"""کانال‌ها (شبکه‌های اجتماعی) پروژه: وضعیت اتصال و روشن/خاموش هر کدام.

هسته‌ی مرکزی (موتور فهم، دانش، هوش مصنوعی) برای همه مشترک است؛ هر کانال تنظیمات و قابلیت‌های
خودش را دارد و جدا روشن و خاموش می‌شود. وضعیت روشن/خاموش در data/channels.json است تا
پروسه‌ی ربات تلگرام هم بخواندش. مقدار هیچ کلیدی برگردانده نمی‌شود، فقط این‌که تنظیم شده یا نه.
"""
import json
import os
import time
from pathlib import Path

from . import config, db

# ready=False یعنی در فهرست هست ولی هنوز ساخته نشده («به‌زودی»)
CHANNELS = {
    "instagram": {"label": "اینستاگرام", "ready": True,
                  "fields": [("IG_ACCESS_TOKEN", "توکن دسترسی"), ("IG_USER_ID", "شناسه‌ی پیج"),
                             ("IG_APP_SECRET", "کلید مخفی اپ (Instagram App Secret)"),
                             ("IG_VERIFY_TOKEN", "رمز تأیید وبهوک")]},
    "telegram": {"label": "تلگرام", "ready": True,
                 "fields": [("BOT_TOKEN", "توکن ربات از BotFather"), ("ADMIN_ID", "آیدی عددی مدیرها")]},
    "bale": {"label": "بله", "ready": False, "fields": []},
    "eitaa": {"label": "ایتا", "ready": False, "fields": []},
    "rubika": {"label": "روبیکا", "ready": False, "fields": []},
    "whatsapp": {"label": "واتساپ", "ready": False, "fields": []},
    "webchat": {"label": "چت سایت", "ready": False, "fields": []},
}
TG_ONLINE_SECONDS = 180


def state_file() -> Path:
    return Path(config.DB_PATH).parent / "channels.json"


def _state() -> dict:
    try:
        d = json.loads(state_file().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def enabled(ch: str) -> bool:
    """کانال ساخته‌شده به‌طور پیش‌فرض روشن است تا کاربر خاموشش کند."""
    if not CHANNELS.get(ch, {}).get("ready"):
        return False
    return bool(_state().get(ch, {}).get("enabled", True))


def set_enabled(ch: str, value: bool) -> None:
    if not CHANNELS.get(ch, {}).get("ready"):
        raise ValueError("این کانال هنوز در دسترس نیست")
    d = _state()
    d.setdefault(ch, {})["enabled"] = bool(value)
    f = state_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, f)


def _fields(ch: str) -> list[dict]:
    return [{"key": k, "label": l, "set": bool((os.environ.get(k) or getattr(config, k, "") or "").strip())}
            for k, l in CHANNELS[ch]["fields"]]


def _instagram(c) -> dict:
    fields = _fields("instagram")
    exp = float(db.kv_get(c, "token_expires_at") or 0)
    last = c.execute("SELECT MAX(created_at) FROM events").fetchone()[0]
    day = time.time() - 86400
    connected = all(f["set"] for f in fields)
    return {"connected": connected, "last_event": last or 0,
            "token_days_left": int((exp - time.time()) / 86400) if exp else None,
            "events_24h": c.execute("SELECT COUNT(*) FROM events WHERE created_at>?", (day,)).fetchone()[0],
            "webhook_url": "https://ig.stland.ir/webhook",
            "note": "" if connected else "مقدارهای اپ متا هنوز در ‎/opt/igbot/.env نیست"}


def _telegram() -> dict:
    fields = _fields("telegram")
    st = {}
    try:
        st = json.loads((Path(config.TG_DATA_DIR) / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    online = bool(st) and time.time() - float(st.get("ts") or 0) < TG_ONLINE_SECONDS
    return {"connected": all(f["set"] for f in fields) and online, "online": online,
            "username": st.get("username") or "", "users": st.get("users"), "last_seen": st.get("ts") or 0,
            "note": "" if online else "ربات تلگرام گزارش وضعیت نمی‌دهد؛ سرویس igbot-telegram روشن است؟"}


def describe(c) -> list[dict]:
    out = []
    for ch, meta in CHANNELS.items():
        item = {"id": ch, "label": meta["label"], "ready": meta["ready"], "enabled": enabled(ch),
                "fields": _fields(ch) if meta["ready"] else []}
        if ch == "instagram":
            item.update(_instagram(c))
        elif ch == "telegram":
            item.update(_telegram())
        else:
            item.update(connected=False, note="به‌زودی")
        out.append(item)
    return out
