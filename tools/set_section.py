"""جایگزینی متن یکی از بخش‌های دانش مرکزی (همان «متن بخش‌ها»ی پنل) از روی یک فایل.

از همان مسیر پنل می‌رود: صف inbox که خود ربات تلگرام چند ثانیه بعد اعمال می‌کند (تنها نویسنده‌ی
data.json)؛ ری‌استارت لازم نیست. نسخه‌ی فعلی پیش از اعمال در /var/backups/igbot بکاپ می‌شود.
پیش‌فرض فقط نمایش (قبل و بعد)؛ با --apply اعمال.
به کتابخانه‌های برنامه نیاز دارد، پس با پایتونِ ‎.venv‎ اجرا شود (نه python3 سیستم).

    .venv/bin/python tools/set_section.py 3 deploy/texts/installment.txt
    .venv/bin/python tools/set_section.py 3 deploy/texts/installment.txt --apply
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("key", help="۳ اقساط، ۴ پشتیبانی، ۵ آدرس، ۲ سایت، ۱ شبکه‌ها")
    ap.add_argument("file")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup-dir", default="/var/backups/igbot")
    a = ap.parse_args(argv)
    from app import config, shared_kb
    if a.key not in shared_kb.SECTIONS:
        sys.exit(f"بخش ناشناخته؛ یکی از: {', '.join(f'{k}={v}' for k, v in shared_kb.SECTIONS.items())}")
    text = Path(a.file).read_text(encoding="utf-8").strip()
    data = Path(config.TG_DATA_DIR) / "data.json"
    cur = (json.loads(data.read_text(encoding="utf-8")).get(a.key) or "") if data.exists() else ""
    print(f"بخش «{shared_kb.SECTIONS[a.key]}»\n\n── الان:\n{cur or '(خالی)'}\n\n── بعد:\n{text}")
    if cur.strip() == text:
        print("\nهمین متن است؛ تغییری لازم نیست.")
        return 0
    if not a.apply:
        print("\nفقط نمایش بود؛ برای اعمال: --apply")
        return 0
    if data.exists():
        b = Path(a.backup_dir) / f"section-{a.key}-{time.strftime('%Y%m%d-%H%M%S')}"
        b.mkdir(parents=True, exist_ok=True)
        shutil.copy2(data, b / "data.json")
        print(f"\nبکاپ: {b}")
    shared_kb.save_section(a.key, text)
    print("✅ در صف ربات تلگرام گذاشته شد؛ چند ثانیه‌ی دیگر در تلگرام و اینستاگرام و پنل اعمال است.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
