"""خروجی متن پیام‌های واقعی مشتری‌ها برای رشد دانش ربات (۶ آذر ۱۴۰۵).

فقط متن پیام مشتری بیرون می‌آید: بی‌نام، بی‌آیدی، بی‌زمان. شماره‌ی تلفن و کارت (هر عدد ۷ رقم به بالا)،
لینک، ایمیل و @آیدی پوشانده می‌شوند. پیام‌های یکسان یکی می‌شوند و تعدادشان کنارشان می‌آید.
خروجی همان قالبی است که tgbot/tools/answer_check.py scan می‌خواند: [[متن, تعداد], …]

منبع‌ها (فقط خواندن؛ چیزی نوشته یا پاک نمی‌شود):
- دایرکت‌ها و کامنت‌های اینستاگرام و لاگ مغز مرکزی (data/bot.db)
- سؤال‌های نفهمیده‌ی فهرست مشترک و جستجوهای کالای ربات تلگرام (data/telegram)

با پایتون سیستم هم اجرا می‌شود (فقط کتابخانه‌ی استاندارد):

    python3 tools/export_questions.py                      # → /tmp/stockland_questions.json
    python3 tools/export_questions.py --out FILE --days 365 --limit 3000

فایل خروجی اطلاعات مشتری است: در ریپو گذاشته نمی‌شود.
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_LEN = 300

_URL = re.compile(r"(?:https?://|www\.)\S+|\b[\w.-]+\.(?:ir|com|net|org|me)\b\S*", re.I)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
_HANDLE = re.compile(r"@[\w.]+")
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_LONG_NUM = re.compile(r"(?:\d[\s\-]?){7,}")        # تلفن، کارت، شبا، کد ملی
_SPACE = re.compile(r"\s+")


def mask(text: str) -> str:
    t = str(text or "").translate(_FA_DIGITS)
    t = _EMAIL.sub("<ایمیل>", t)
    t = _URL.sub("<لینک>", t)
    t = _HANDLE.sub("<آیدی>", t)
    t = _LONG_NUM.sub("<شماره> ", t)
    return _SPACE.sub(" ", t).strip()


def _key(t: str) -> str:
    return _SPACE.sub(" ", re.sub(r"[؟?!.،,]+", " ", t.lower())).strip()


def _rows(db: Path, sql: str, args=()) -> list:
    if not db.exists():
        return []
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
        try:
            return [r[0] for r in c.execute(sql, args)]
        finally:
            c.close()
    except sqlite3.Error as e:
        print(f"  ⚠️ {db.name}: {e}", file=sys.stderr)
        return []


def _json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def collect(bot_db: Path, tg_dir: Path, since: float) -> dict[str, list]:
    """متن خام هر منبع (پیش از پوشاندن)."""
    out: dict[str, list] = {}
    out["دایرکت اینستاگرام"] = _rows(bot_db, "SELECT text FROM messages WHERE direction='in' AND created_at>?", (since,))
    out["کامنت اینستاگرام"] = _rows(bot_db, "SELECT text FROM comments WHERE created_at>?", (since,))
    out["مغز مرکزی (همه‌ی پلتفرم‌ها)"] = _rows(
        bot_db, "SELECT input FROM ai_log WHERE is_test=0 AND created_at>? AND channel NOT IN ('review')", (since,))
    unm = _json(tg_dir / "unmatched.json", [])
    texts = []
    for u in unm if isinstance(unm, list) else []:
        if isinstance(u, dict) and u.get("text"):
            texts += [u["text"]] * max(1, min(int(u.get("count", 1) or 1), 50))
    out["نفهمیده‌های فهرست مشترک"] = texts
    since_iso = time.strftime("%Y-%m-%d", time.localtime(since))
    out["جستجوی کالای تلگرام"] = _rows(tg_dir / "users.db", "SELECT q FROM searches WHERE ts>=?", (since_iso,))
    return out


def build(sources: dict[str, list], limit: int) -> tuple[list, dict]:
    cnt: Counter = Counter()
    first: dict[str, str] = {}
    stats = {}
    for name, texts in sources.items():
        n = 0
        for raw in texts:
            t = mask(raw)
            if len(t) < 2 or len(t) > MAX_LEN or not re.search(r"[آ-یa-zA-Z]", t):
                continue
            k = _key(t)
            first.setdefault(k, t)
            cnt[k] += 1
            n += 1
        stats[name] = n
    items = [[first[k], n] for k, n in cnt.most_common(limit)]
    return items, stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/stockland_questions.json")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--limit", type=int, default=4000, help="حداکثر تعداد پیام یکتا (پرتکرارها اول)")
    ap.add_argument("--db", default=os.environ.get("DB_PATH", str(ROOT / "data" / "bot.db")))
    ap.add_argument("--tg-dir", default=os.environ.get("TG_DATA_DIR", str(ROOT / "data" / "telegram")))
    a = ap.parse_args(argv)
    sources = collect(Path(a.db), Path(a.tg_dir), time.time() - a.days * 86400)
    items, stats = build(sources, a.limit)
    out = Path(a.out)
    out.write_text(json.dumps(items, ensure_ascii=False, indent=0), encoding="utf-8")
    try:
        os.chmod(out, 0o600)
    except OSError:
        pass
    for name, n in stats.items():
        print(f"{name}: {n}")
    print(f"پیام یکتا: {len(items)} (از {sum(stats.values())} پیام) ← {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
