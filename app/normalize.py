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


def normalize(text: str | None) -> str:
    if not text:
        return ""
    t = _ZERO_WIDTH.sub("", text).translate(_CHAR_MAP).lower()
    t = _EDGE_PUNCT.sub("", t)
    return _SPACES.sub(" ", t).strip()
