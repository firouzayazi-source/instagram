"""یکسان‌سازی متن فارسی تا «تقویم»، «تقويم» و «تقویم.» یکی دیده شوند."""
import re

_CHAR_MAP = str.maketrans({
    "ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "ؤ": "و", "إ": "ا", "أ": "ا", "آ": "ا",
    **{d: str(i) for i, d in enumerate("٠١٢٣٤٥٦٧٨٩")},
    **{d: str(i) for i, d in enumerate("۰۱۲۳۴۵۶۷۸۹")},
})
_ZERO_WIDTH = re.compile(r"[​-‏‪-‮﻿]")
_EDGE_PUNCT = re.compile(r"^[\s\.\،,!؟\?:;\-_\"'«»()\[\]]+|[\s\.\،,!؟\?:;\-_\"'«»()\[\]]+$")
_SPACES = re.compile(r"\s+")
_MARKS = re.compile(r"[\u0640\u064B-\u065F\u0670]")      # کشیده (لیـست) و اعراب (لیستُ)


def _strip_symbols(t: str) -> str:
    """شکلک و نماد ابتدا و انتهای متن («لیست 😍»، «لیست❤️» ← «لیست»)."""
    import unicodedata
    edge = lambda ch: unicodedata.category(ch) in ("So", "Sk", "Sm", "Cn", "Mn", "Cf") or ch in "\ufe0f\u200d"  # noqa: E731
    i, j = 0, len(t)
    while i < j and (edge(t[i]) or t[i].isspace()):
        i += 1
    while j > i and (edge(t[j - 1]) or t[j - 1].isspace()):
        j -= 1
    return t[i:j]


def normalize(text: str | None) -> str:
    if not text:
        return ""
    t = _ZERO_WIDTH.sub("", text).translate(_CHAR_MAP).lower()
    t = _MARKS.sub("", t)
    for _ in range(2):                 # نماد و نقطه‌گذاری لبه‌ها ممکن است درهم باشند («لیست!! 😍»)
        t = _strip_symbols(_EDGE_PUNCT.sub("", t))
    return _SPACES.sub(" ", t).strip()
