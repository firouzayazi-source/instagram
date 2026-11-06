"""عوض کردن نشانی ربات اصلی استوک‌لند (همان ربات اپل‌آیدی) در همه‌ی دانش و تنظیمات پروژه.

نشانی در کد نیست؛ از دکمه‌ی «اپل آیدی» منوی ربات تلگرام خوانده می‌شود (tgbot/appleid.py). این ابزار نام
کاربری قدیم را (پیش‌فرض: همان که الان در دکمه‌ی اپل‌آیدی است، یا با --old) در همه‌ی لینک‌های t.me و
telegram.me و نام‌های @ در متن بخش‌ها، جواب نیت‌ها، دکمه‌ها، صفحه‌ها و تنظیمات ربات تلگرام و اطلاعات
کسب‌وکار هوش مصنوعی با نام تازه جایگزین می‌کند. به داده‌ی مشتری‌ها (پرونده، سفارش، پیام) دست نمی‌زند.

پیش‌فرض فقط نمایش است. با --apply: بکاپ در /var/backups/igbot، توقف کوتاه ربات تلگرام، نوشتن، روشن کردن.

    sudo python3 /opt/igbot/tools/set_bot_link.py Stlandd_bot
    sudo python3 /opt/igbot/tools/set_bot_link.py Stlandd_bot --apply
"""
import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tgbot"))
sys.path.insert(0, str(ROOT / "tools"))
import appleid  # noqa: E402
import set_contact_phone as phone  # noqa: E402  (فایل‌ها، بکاپ و نوشتن مشترک)

USER_RX = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")


def username(s: str) -> str:
    s = s.strip().rstrip("/")
    s = re.sub(r"^(?:https?://)?(?:t|telegram)\.me/", "", s, flags=re.I).lstrip("@")
    return s.split("?")[0]


def rx(old: str):
    o = re.escape(old)
    return re.compile(rf"((?:https?://)?(?:t|telegram)\.me/|(?<![\w.]){'@'}){o}(?![A-Za-z0-9_])", re.I)


def walk(obj, pat, new, path, changes):
    if isinstance(obj, str):
        s = pat.sub(lambda m: m.group(1) + new, obj)
        if s != obj:
            changes.append((path, obj, s))
        return s
    if isinstance(obj, list):
        return [walk(x, pat, new, f"{path}[{i}]", changes) for i, x in enumerate(obj)]
    if isinstance(obj, dict):
        return {k: (v if k in ("id", "hits", "_seed", "file_id", "uid", "thumb_id") else walk(v, pat, new, f"{path}.{k}", changes))
                for k, v in obj.items()}
    return obj


def load(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def current_old(tg_dir: Path):
    found = appleid.find(load(tg_dir / "menu.json", []), load(tg_dir / "buttons.json", {}), load(tg_dir / "data.json", {}))
    if found and re.search(r"//(?:t|telegram)\.me/", found[1], re.I):
        return username(found[1])
    return None


def plan(old: str, new: str, tg_dir: Path, db_path: Path):
    pat, out = rx(old), []
    for name in phone.TG_FILES:
        p = tg_dir / name
        if p.exists():
            ch = []
            nd = walk(load(p, None), pat, new, name, ch)
            out.append((p, nd, ch))
    if db_path.exists():
        with sqlite3.connect(db_path) as c:
            r = c.execute("SELECT value FROM kv WHERE key='ai_settings'").fetchone()
        if r:
            ch = []
            nd = walk(json.loads(r[0]), pat, new, "ai_settings", ch)
            out.append((("kv", "ai_settings"), nd, ch))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("new", help="نام کاربری تازه‌ی ربات، مثل Stlandd_bot")
    ap.add_argument("--old", help="نام کاربری قدیم؛ پیش‌فرض همان که در دکمه‌ی اپل‌آیدی است")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--tg-dir", default=str(ROOT / "data" / "telegram"))
    ap.add_argument("--db", default=str(ROOT / "data" / "bot.db"))
    ap.add_argument("--backup-dir", default="/var/backups/igbot")
    ap.add_argument("--no-service", action="store_true", help="برای تست: سرویس تلگرام را خاموش/روشن نکن")
    a = ap.parse_args(argv)
    new = username(a.new)
    if not USER_RX.fullmatch(new):
        sys.exit("نام کاربری تازه نامعتبر است")
    tg_dir, db_path = Path(a.tg_dir), Path(a.db)
    old = username(a.old) if a.old else current_old(tg_dir)
    if not old:
        sys.exit("لینک t.me در دکمه‌ی «اپل آیدی» منوی ربات پیدا نشد؛ نام قدیم را با --old بدهید.")
    print(f"نام قدیم: {old}  ←  نام تازه: {new}")
    if old == new:
        print("نشانی همین الان درست است؛ چیزی برای تغییر نیست.")
        return 0
    items = plan(old, new, tg_dir, db_path)
    total = sum(len(ch) for _, _, ch in items)
    pat = rx(old)
    for _, _, ch in items:
        for path, before, after in ch:
            print(f"── {path}")
            for m in pat.finditer(before):
                print(f"  قبل: …{before[max(0, m.start() - 40):m.end() + 20]!r}…")
    print(f"\n{total} جای تغییر.")
    if not a.apply or not total:
        print("فقط نمایش بود؛ برای اعمال: --apply" if total else "چیزی برای تغییر نیست.")
        return 0
    phone.write_all(items, tg_dir, db_path, Path(a.backup_dir), "bot-link", a.no_service)
    print("✅ اعمال شد")
    return 0


if __name__ == "__main__":
    sys.exit(main())
