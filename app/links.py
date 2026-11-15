"""لینک ردیابی‌شده و شخصی‌سازی پیام دستورها.

- هر لینکی که در پیام یا دکمه‌ی یک دستور است، هنگام ارسال به ‎https://ig.stland.ir/l/<کد>‎ تبدیل می‌شود؛ لمسش
  یک کلیک برای همان دستور ثبت می‌کند و بی‌درنگ به نشانی اصلی می‌رود. کد برای هر (دستور، نشانی) ثابت است.
  از بازدیدکننده فقط هش «IP + روز» نگه داشته می‌شود (برای شمردن نفرهای یکتا)، نه خود IP.
- ‎{username}‎ در متن با نام کاربری مخاطب جایگزین می‌شود (اگر معلوم نباشد، حذف می‌شود).
"""
import hashlib
import re
import secrets
import time

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS links (
  code TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  rule_id INTEGER,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_links_rule ON links(rule_id, url);
CREATE TABLE IF NOT EXISTS link_clicks (
  code TEXT NOT NULL,
  at REAL NOT NULL,
  visitor TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_link_clicks ON link_clicks(code, at);
"""
_URL = re.compile(r"https?://[^\s؀-ۿ«»()<>\"']+")
_CODE = re.compile(r"^[a-z0-9]{6,16}$")
MAX_BUTTONS = 3


def ensure(c) -> None:
    c.executescript(SCHEMA)


def base() -> str:
    return f"{config.PUBLIC_URL.rstrip('/')}/l/"


def short(c, url: str, rule_id) -> str:
    ensure(c)
    r = c.execute("SELECT code FROM links WHERE rule_id IS ? AND url=?", (rule_id, url)).fetchone()
    if r:
        return base() + r[0]
    code = secrets.token_hex(4)
    c.execute("INSERT INTO links(code,url,rule_id,created_at) VALUES (?,?,?,?)", (code, url, rule_id, time.time()))
    return base() + code


def track_text(c, text: str, rule_id) -> str:
    if not text:
        return text
    b = base()

    def rep(m):
        url, tail = m.group(0), ""
        while url and url[-1] in ".,!؟?،:;":        # نقطه‌گذاری آخر جمله جزو لینک نیست
            url, tail = url[:-1], url[-1] + tail
        return (url if url.startswith(b) else short(c, url, rule_id)) + tail
    return _URL.sub(rep, text)


def track_buttons(c, buttons: list[dict], rule_id) -> list[dict]:
    return [{**x, "url": short(c, x["url"], rule_id)} for x in buttons]


def click(c, code: str, ip: str, now: float | None = None) -> str | None:
    """نشانی اصلی یا None. یک کلیک ثبت می‌کند."""
    if not _CODE.match(code or ""):
        return None
    ensure(c)
    r = c.execute("SELECT url FROM links WHERE code=?", (code,)).fetchone()
    if not r:
        return None
    now = now or time.time()
    visitor = hashlib.sha256(f"{ip}|{time.strftime('%Y-%m-%d', time.gmtime(now))}".encode()).hexdigest()[:16]
    c.execute("INSERT INTO link_clicks(code,at,visitor) VALUES (?,?,?)", (code, now, visitor))
    return r[0]


def rule_clicks(c, since: float = 0) -> dict[int, dict]:
    """شناسه‌ی دستور ← {"clicks": کل، "people": نفرهای یکتا در روز}"""
    ensure(c)
    out = {}
    for r in c.execute("SELECT l.rule_id, COUNT(*), COUNT(DISTINCT k.visitor || k.code) FROM link_clicks k "
                       "JOIN links l ON l.code=k.code WHERE k.at>=? AND l.rule_id IS NOT NULL GROUP BY l.rule_id", (since,)):
        out[r[0]] = {"clicks": r[1], "people": r[2]}
    return out


def personalize(text: str, username: str | None) -> str:
    if not text or "{username}" not in text:
        return text
    t = text.replace("{username}", (username or "").lstrip("@"))
    return re.sub(r"[ \t]{2,}", " ", t).replace(" ،", "،").strip()


def clean_buttons(buttons) -> list[dict]:
    out = []
    for x in (buttons or [])[:MAX_BUTTONS]:
        title, url = str((x or {}).get("title", "")).strip()[:20], str(x.get("url", "")).strip()
        if not title and not url:
            continue
        if not title or not url.startswith("https://"):
            raise ValueError("هر دکمه عنوان (تا ۲۰ نویسه) و لینکی که با https:// شروع شود لازم دارد")
        out.append({"title": title, "url": url})
    return out
