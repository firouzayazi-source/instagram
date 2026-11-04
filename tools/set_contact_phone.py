"""یکی کردن شماره‌ی تماس فروشگاه (یکپارچه، بی‌فاصله، تا در متن فارسی به‌هم نریزد) در همه‌ی دانش و تنظیمات پروژه.

هر شماره‌ی تلفن (موبایل یا ثابت، با رقم فارسی یا لاتین، با فاصله یا خط تیره، و لینک‌های tel: و wa.me)
در متن بخش‌ها، جواب نیت‌ها، دکمه‌ها، صفحه‌ها و تنظیمات ربات تلگرام و در اطلاعات کسب‌وکار هوش مصنوعی
با شماره‌ی تازه جایگزین می‌شود؛ خط‌هایی که بعد از جایگزینی تکراری شوند یکی می‌شوند.
به داده‌ی مشتری‌ها (پرونده، سفارش، پیام) دست نمی‌زند.

پیش‌فرض فقط نمایش است (چه چیزی عوض می‌شود). با --apply: بکاپ در /var/backups/igbot، توقف کوتاه ربات
تلگرام (تنها نویسنده‌ی فایل‌هایش)، نوشتن، و روشن کردن دوباره.

    python3 tools/set_contact_phone.py 09127488434
    python3 tools/set_contact_phone.py 09127488434 --apply
"""
import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TG_FILES = ("data.json", "faq.json", "buttons.json", "places.json", "pages.json", "menu.json", "settings.json", "banner.json")
FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_D = r"[0-9۰-۹٠-٩]"
_SEP = r"[\s\-‌.]?"
# موبایل ۰۹… / +۹۸۹… / ۹۸۹…، و تلفن ثابت ۰۲۵… (۱۱ رقم با صفر)
PHONE_RX = re.compile(
    rf"(?<![0-9۰-۹٠-٩])(?:(?:\+|00)?(?:98|۹۸){_SEP}|[0۰٠])(?:[9۹٩]{_D}{{2}}|[1-8۱-۸١-٨]{_D}{{1,2}}){_SEP}{_D}{{3,4}}{_SEP}{_D}{{3,4}}(?![0-9۰-۹٠-٩])")


def canon(num: str) -> str:
    """هر شکل شماره → ۰۹۱۲۷۴۸۸۴۳۴ (لاتین، با صفر)."""
    d = re.sub(r"\D", "", num.translate(EN))
    if d.startswith("0098"):
        d = d[4:]
    if d.startswith("98") and len(d) == 12:
        d = d[2:]
    return d if d.startswith("0") else "0" + d


def fmt(new: str, sample: str, ctx: str) -> str:
    """شماره‌ی تازه به همان شکل جای قبلی: لینک → ‎+98…‎، رقم فارسی → فارسی، وگرنه لاتین با فاصله."""
    c = canon(new)
    if re.search(r"(?:tel:|wa\.me/|whatsapp)\s*$", ctx, re.I):
        return ("+98" if sample.strip().startswith("+") else "98") + c[1:] if "wa.me" in ctx.lower() else "+98" + c[1:]
    # یکپارچه و بی‌فاصله: «۰۹۱۲ ۷۴۸ ۸۴۳۴» در متن راست‌به‌چپ جابه‌جا نمایش داده می‌شود
    return c.translate(FA) if re.search(r"[۰-۹٠-٩]", sample) else c


def replace_in(text: str, new: str) -> tuple[str, list[str]]:
    found = []

    def sub(m):
        if canon(m.group(0)) == canon(new) and len(canon(m.group(0))) == 11:
            found.append(m.group(0))
            return fmt(new, m.group(0), text[max(0, m.start() - 20):m.start()])
        found.append(m.group(0))
        return fmt(new, m.group(0), text[max(0, m.start() - 20):m.start()])
    out = PHONE_RX.sub(sub, text)
    if not found:
        return text, []
    # «X - X»، «X و X»، «X، X» → X ؛ خط‌های تکراری پشت‌سرهم → یکی
    for disp in {fmt(new, f, "") for f in found} | {fmt(new, "۰", "")}:
        e = re.escape(disp)
        out = re.sub(rf"{e}(?:\s*(?:-|–|و|،|,|/|\||یا)\s*{e})+", disp, out)
    lines, keep = out.split("\n"), []
    for ln in lines:
        if keep and ln.strip() and ln.strip() == keep[-1].strip():
            continue
        if keep and canon(new) in canon(ln) and ln.strip() in [k.strip() for k in keep]:
            continue
        keep.append(ln)
    return "\n".join(keep), found


def walk(obj, new, path, changes):
    """همه‌ی رشته‌های JSON؛ کلیدهای آماری و شناسه‌ها دست نمی‌خورند."""
    if isinstance(obj, str):
        new_s, found = replace_in(obj, new)
        if found and new_s != obj:
            changes.append((path, obj, new_s))
        return new_s
    if isinstance(obj, list):
        return [walk(x, new, f"{path}[{i}]", changes) for i, x in enumerate(obj)]
    if isinstance(obj, dict):
        return {k: (v if k in ("id", "hits", "_seed", "file_id", "uid", "thumb_id") else walk(v, new, f"{path}.{k}", changes))
                for k, v in obj.items()}
    return obj


SUPPORT_KEY = "4"     # بخش «پشتیبانی و تماس» ربات تلگرام (کلید همان در shared_kb.SECTIONS)


def plan(new: str, tg_dir: Path, db_path: Path, ensure_support: bool = True):
    """[(برچسب، داده‌ی تازه یا None، تغییرها)]"""
    out = []
    for name in TG_FILES:
        p = tg_dir / name
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        ch = []
        nd = walk(data, new, name, ch)
        if name == "data.json" and ensure_support and isinstance(nd, dict):
            cur = nd.get(SUPPORT_KEY) or ""
            if not PHONE_RX.search(cur):     # بخش پشتیبانی شماره ندارد: یک خط تماس اضافه می‌شود
                line = f"📞 شماره‌ی تماس: {new.translate(FA)}"
                nd[SUPPORT_KEY] = (cur.rstrip() + "\n\n" + line) if cur.strip() else line
                ch.append((f"{name}.{SUPPORT_KEY} (افزودن به «پشتیبانی و تماس»)", cur, nd[SUPPORT_KEY]))
        out.append((p, nd, ch))
    if db_path.exists():
        with sqlite3.connect(db_path) as c:
            r = c.execute("SELECT value FROM kv WHERE key='ai_settings'").fetchone()
        if r:
            data = json.loads(r[0])
            ch = []
            nd = walk(data, new, "ai_settings", ch)
            out.append((("kv", "ai_settings"), nd, ch))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("phone")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--tg-dir", default=str(ROOT / "data" / "telegram"))
    ap.add_argument("--db", default=str(ROOT / "data" / "bot.db"))
    ap.add_argument("--backup-dir", default="/var/backups/igbot")
    ap.add_argument("--no-service", action="store_true", help="برای تست: سرویس تلگرام را خاموش/روشن نکن")
    ap.add_argument("--no-support", action="store_true", help="شماره به بخش «پشتیبانی و تماس» اضافه نشود")
    a = ap.parse_args(argv)
    new = canon(a.phone)
    if not re.fullmatch(r"0\d{10}", new):
        sys.exit("شماره نامعتبر است")
    tg_dir, db_path = Path(a.tg_dir), Path(a.db)
    items = plan(new, tg_dir, db_path, ensure_support=not a.no_support)
    total = sum(len(ch) for _, _, ch in items)
    for target, _, ch in items:
        for path, old, nw in ch:
            print(f"── {path}")
            olds = [m.group(0) for m in PHONE_RX.finditer(old)]
            if olds:     # دور خود شماره، نه ابتدای متن
                for m in PHONE_RX.finditer(old):
                    print(f"  قبل: …{old[max(0, m.start() - 70):m.end() + 30]!r}…")
                for m in re.finditer(re.escape(new) + "|" + re.escape(new.translate(FA)), nw):
                    print(f"  بعد: …{nw[max(0, m.start() - 70):m.end() + 30]!r}…")
            else:
                print(f"  قبل: {old[-200:]!r}\n  بعد: {nw[-200:]!r}")
    print(f"\n{total} جای تغییر. شماره‌ی تازه: {new}")
    if not a.apply or not total:
        print("فقط نمایش بود؛ برای اعمال: --apply" if total else "چیزی برای تغییر نیست.")
        return 0
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bdir = Path(a.backup_dir) / f"contact-phone-{stamp}"
    bdir.mkdir(parents=True, exist_ok=True)
    for name in TG_FILES:
        if (tg_dir / name).exists():
            shutil.copy2(tg_dir / name, bdir / name)
    if db_path.exists():
        shutil.copy2(db_path, bdir / "bot.db")
    print(f"بکاپ: {bdir}")
    if not a.no_service:
        subprocess.run(["systemctl", "stop", "igbot-telegram"], check=False)
    try:
        for target, nd, ch in items:
            if not ch:
                continue
            if isinstance(target, Path):
                tmp = target.with_suffix(target.suffix + ".tmp")
                tmp.write_text(json.dumps(nd, ensure_ascii=False, indent=1), encoding="utf-8")
                st = target.stat()
                os.replace(tmp, target)
                try:
                    os.chown(target, st.st_uid, st.st_gid)
                except OSError:
                    pass
            else:
                with sqlite3.connect(db_path) as c:
                    c.execute("UPDATE kv SET value=? WHERE key='ai_settings'", (json.dumps(nd, ensure_ascii=False),))
    finally:
        if not a.no_service:
            subprocess.run(["systemctl", "start", "igbot-telegram"], check=False)
    print("✅ اعمال شد")
    return 0


if __name__ == "__main__":
    sys.exit(main())
