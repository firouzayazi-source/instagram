"""نظارت خودکار کامنت‌ها: کامنت توهین‌آمیز، تبلیغ و لینک، یا کلمه‌ی ممنوع مخفی می‌شود.

مخفی کردن در اینستاگرام برگشت‌پذیر است (کامنت فقط برای نویسنده و دوستانش دیده می‌شود) و از
صفحه‌ی کامنت‌ها با یک لمس برمی‌گردد. فیلتر فحش همان فیلتر ربات تلگرام است (tgbot/profanity.py).
"""
import re

from . import brain_engine  # noqa: F401  (مسیر tgbot را به sys.path اضافه می‌کند)
from .normalize import normalize

import profanity  # noqa: E402  (tgbot/profanity.py)

# لینک و دامنه؛ منشن دوستان (@name) زیر پست رایج و بی‌خطر است و شامل نمی‌شود
LINK = re.compile(r"https?://|www\.|t\.me/|wa\.me/|\b[\w-]{2,}\.(?:com|ir|net|org|shop|store|me|info|xyz|online)\b",
                  re.IGNORECASE)


def check(text: str, s: dict) -> str:
    """دلیل مخفی کردن، یا رشته‌ی خالی اگر کامنت مشکلی ندارد."""
    if not text:
        return ""
    if s.get("mod_profanity") and profanity.is_abusive(text):
        return "توهین"
    if s.get("mod_links") and LINK.search(text):
        return "لینک یا تبلیغ"
    t = normalize(text)
    for w in s.get("mod_words") or []:
        w = normalize(w)
        if w and w in t:
            return "کلمه‌ی ممنوع"
    return ""
