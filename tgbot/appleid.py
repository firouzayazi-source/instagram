"""لینک «ربات اپل آیدی» استوک‌لند: همان دکمه‌ای که مدیر در منوی ربات تلگرام ساخته.

نشانی در کد نیست؛ از تنظیمات خود ربات پیدا می‌شود (menu.json → کلید آن دکمه → لینک‌های دستی آن بخش در
buttons.json یا لینک داخل متنش در data.json). پس اگر مدیر ربات یا نشانی را از پنل عوض کند، همه‌جا
(تلگرام و اینستاگرام) خودکار همان می‌شود. اولویت با لینک تلگرام (t.me) است.
"""
import re

LABEL_RX = re.compile(r"اپل\s*‌?\s*آ?یدی|اپل\s*‌?\s*ایدی|apple\s*id", re.I)
_URL_RX = re.compile(r"(?:https?://)?(?:t\.me|telegram\.me)/[A-Za-z0-9_]{4,}[^\s<>\"']*|https?://[^\s<>\"']+", re.I)


def _norm(u):
    u = u.strip().rstrip(".،,؛;")
    return u if u.lower().startswith("http") else "https://" + u


def find(menu, buttons, data):
    """(عنوان دکمه، نشانی) یا None. menu فهرست آیتم‌های منو، buttons و data همان فایل‌های ربات."""
    for m in sorted(menu or [], key=lambda x: x.get("order", 99)):
        label = m.get("label", "")
        if not LABEL_RX.search(label) or not m.get("enabled", True):
            continue
        key = m.get("key")
        urls = [(it.get("url") or "").strip() for it in ((buttons or {}).get(key) or {}).get("items", [])]
        urls += _URL_RX.findall(((data or {}).get(key) or "") if isinstance(data, dict) else "")
        urls = [_norm(u) for u in urls if u]
        if urls:
            tg = [u for u in urls if re.search(r"//(?:t|telegram)\.me/", u, re.I)]
            return label, (tg or urls)[0]
    return None
