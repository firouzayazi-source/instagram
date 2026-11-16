"""ترمز اضطراری و قواعد ایمنی پیج (بعد از قفل پیج در ۲۵ آبان ۱۴۰۵).

هر خطایی از اینستاگرام که نشانه‌ی محدودیت، مسدودی، اسپم یا باطل شدن دسترسی است، ترمز را می‌کشد: از آن لحظه هیچ
پیام، جواب یا انتشاری از برنامه نمی‌رود (خواندن کامنت و دایرکت برای صندوق ادامه دارد) و به تلگرام مدیر خبر می‌رود.
فقط صاحب پیج از پنل (بیشتر ← حساب، رمز و توقف اضطراری) ترمز را برمی‌دارد. صاحب پیج خودش هم می‌تواند ترمز را دستی بکشد.
"""
import json
import re
import time

from . import db

KEY = "ig_brake"

# کدهای Graph API: 4/17/32/613/80002 سقف نرخ؛ 190 دسترسی باطل (مثلاً بعد از عوض شدن رمز یا قفل)؛
# 368 «موقتاً به خاطر نقض قواعد مسدود». کد 10 عمداً نیست: «بیرون از پنجره‌ی ۲۴ ساعته» هم همین کد است.
CODES = {4, 17, 32, 190, 368, 613, 80002}
SUBCODES = {2207051, 2534040, 2207042, 458, 459, 460, 463, 464, 467}   # اسپم/محدودیت انتشار، سقف جواب خصوصی، نشست باطل
WORDS = ("action blocked", "temporarily blocked", "checkpoint", "spam", "restricted", "suspicious",
         "we limit how often", "session has been invalidated", "account is locked", "has been locked")
URL_RX = re.compile(r"(https?://|www\.)\S+|\b[a-z0-9-]+\.(ir|com|net|org|io|me|ly|gl|co|to|link|app)(/\S*)?\b", re.I)
# نشانی کوتاه یا تغییر مسیر: اینستاگرام لینک پنهان در پیام خودکار را نشانه‌ی پیج هک‌شده می‌داند
SHORTENERS = ("bit.ly", "tinyurl", "goo.gl", "t.co/", "ow.ly", "is.gd", "buff.ly", "cutt.ly", "rebrand.ly", "shorturl",
              "tiny.cc", "rb.gy", "s.id/", "linktr.ee/s/", "/l/")


def _code(err: str, name: str) -> int | None:
    m = re.search(rf"['\"]{name}['\"]:\s*(\d+)", err)
    return int(m.group(1)) if m else None


def dangerous(err: str) -> bool:
    """خطایی که یعنی اینستاگرام پیج یا برنامه را محدود کرده (نه خطای عادی مثل «کامنت پاک شده»)."""
    e = str(err)
    low = e.lower()
    if any(k in low for k in ("length of the message", "does not exist", "outside of allowed window", "brake:")):
        return False
    return _code(e, "code") in CODES or _code(e, "error_subcode") in SUBCODES or any(w in low for w in WORDS)


def state(c) -> dict:
    try:
        return json.loads(db.kv_get(c, KEY) or "{}")
    except ValueError:
        return {}


def active(c=None) -> bool:
    import sqlite3
    try:
        if c is None:
            with db.connect() as c2:
                return bool(state(c2).get("on"))
        return bool(state(c).get("on"))
    except sqlite3.Error:       # پایگاه داده هنوز ساخته نشده (ابزارها، تست‌ها)
        return False


def trip(reason: str, manual: bool = False) -> bool:
    """ترمز را می‌کشد (اگر از قبل کشیده نبود) و به تلگرام خبر می‌دهد. خروجی: آیا همین الان کشیده شد."""
    with db.connect() as c:
        if active(c):
            return False
        db.kv_set(c, KEY, json.dumps({"on": True, "at": time.time(), "reason": str(reason)[:300], "manual": manual},
                                     ensure_ascii=False))
    try:
        from . import tg_notify
        tg_notify.send(("⛔ توقف اضطراری دستی" if manual else "⛔ توقف اضطراری خودکار") +
                       ": از این لحظه هیچ پیام، جواب یا انتشاری از برنامه روی پیج نمی‌رود.\n"
                       f"علت: {str(reason)[:200]}\nبرداشتن: پنل ← بیشتر ← حساب، رمز و توقف اضطراری (بعد از اطمینان از سلامت پیج).")
    except Exception as e:  # noqa: BLE001
        print("brake alert failed:", e)
    return True


def release() -> None:
    with db.connect() as c:
        st = state(c)
        db.kv_set(c, KEY, json.dumps({"on": False, "released_at": time.time(), "last_reason": st.get("reason", "")},
                                     ensure_ascii=False))


def check_error(err) -> None:
    if dangerous(str(err)):
        trip(str(err))


def link_problems(text: str) -> list[str]:
    """مشکل‌های لینک در یک متن پیام خودکار."""
    out = []
    low = (text or "").lower()
    if any(s in low for s in SHORTENERS):
        out.append("لینک کوتاه‌شده یا تغییر مسیر (مثل bit.ly) ممنوع است؛ لینک اصلی را بگذارید")
    return out


def has_link(text: str) -> bool:
    return bool(URL_RX.search(text or ""))
