"""فرستادن خبر به گروه پشتیبانی تلگرام (تاپیک «اینستاگرام») از راه خود ربات تلگرام.

پیام در data/telegram/notify گذاشته می‌شود و ربات تلگرام هر چند ثانیه می‌فرستدش؛ اگر گروه تنظیم نشده
باشد برای مدیرها می‌رود. اگر ربات تلگرام روی این سرور نیست، کاری نمی‌کند.
"""
import json
import os
import secrets
import time
from pathlib import Path

from . import config


def send(text: str, photo: str = "", topic: str = "") -> bool:
    """photo: آدرس https عکس (مثلاً رسید پرداخت) که ربات تلگرام همراه متن می‌فرستد.
    topic: «orders» یعنی تاپیک «🛒 سفارش‌ها» گروه؛ خالی یعنی تاپیک «📸 اینستاگرام»."""
    base = Path(config.TG_DATA_DIR)
    if not (base / "faq.json").exists():
        return False
    d = base / "notify"
    try:
        d.mkdir(parents=True, exist_ok=True)
        name = f"{time.time_ns()}-{secrets.token_hex(3)}.json"
        tmp = d / (name + ".tmp")
        tmp.write_text(json.dumps({"text": text[:3500], **({"photo": photo} if photo.startswith("https://") else {}),
                                   **({"topic": topic} if topic else {})},
                                  ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, d / name)
        return True
    except OSError as e:
        print("tg notify failed:", e)
        return False
