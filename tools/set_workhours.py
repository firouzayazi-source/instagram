"""تنظیم ساعت کاری فروشگاه در ربات (همان workhours.json که تلگرام و اینستاگرام هر دو می‌خوانند).

شیفت‌ها برای روزهای شنبه تا پنجشنبه که الان باز هستند گذاشته می‌شود؛ جمعه و روزهای تعطیل دست نمی‌خورند،
مگر با --days روزها را مشخص کنید (۰=شنبه … ۶=جمعه). پیش‌فرض فقط نمایش؛ با --apply بکاپ، توقف کوتاه
ربات تلگرام (تنها نویسنده‌ی فایل)، نوشتن و روشن کردن دوباره.

    python3 tools/set_workhours.py 11:00-14:00 17:00-22:00
    python3 tools/set_workhours.py 11:00-14:00 17:00-22:00 --apply
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def parse_shift(s):
    a, _, b = s.partition("-")
    a, b = a.strip().zfill(5), b.strip().zfill(5)
    if not (HHMM.match(a) and HHMM.match(b)):
        raise ValueError(f"شیفت نامعتبر: {s} (مثال 11:00-14:00)")
    return {"from": a, "to": b}


def table(wh):
    sch = wh.get("schedule") or {}
    rows = []
    for i, name in enumerate(DAYS):
        d = sch.get(str(i)) or {}
        when = " و ".join(f"{x['from']} تا {x['to']}" for x in d.get("shifts", []))
        rows.append(f"  {name}: {when if d.get('open') and when else 'تعطیل'}")
    return "\n".join(rows)


def build(wh, shifts, days=None):
    sch = dict(wh.get("schedule") or {})
    open_now = [i for i in range(7) if (sch.get(str(i)) or {}).get("open")]
    # جمعه (۶) فقط با --days عوض می‌شود؛ ساعتش معمولاً با بقیه‌ی هفته فرق دارد
    target = days if days is not None else ([i for i in open_now if i != 6] or [0, 1, 2, 3, 4, 5])
    out = {"enabled": True, "schedule": {}}
    for i in range(7):
        d = dict(sch.get(str(i)) or {"open": False, "shifts": []})
        if i in target:
            d["open"], d["shifts"] = True, shifts
        elif days is not None:
            d["open"] = False
        out["schedule"][str(i)] = d
    for k, v in wh.items():
        if k not in ("enabled", "schedule"):
            out[k] = v
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("shifts", nargs="+")
    ap.add_argument("--days", help="مثلاً 0,1,2,3,4,5 (۰=شنبه)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--tg-dir", default=str(ROOT / "data" / "telegram"))
    ap.add_argument("--backup-dir", default="/var/backups/igbot")
    ap.add_argument("--no-service", action="store_true")
    a = ap.parse_args(argv)
    try:
        shifts = [parse_shift(s) for s in a.shifts]
        days = [int(x) for x in a.days.split(",")] if a.days else None
    except ValueError as e:
        sys.exit(str(e))
    p = Path(a.tg_dir) / "workhours.json"
    cur = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    new = build(cur, shifts, days)
    print("الان:\n" + (table(cur) if cur else "  (تنظیم نشده)") + "\n\nبعد:\n" + table(new))
    if not a.apply:
        print("\nفقط نمایش بود؛ برای اعمال: --apply")
        return 0
    bdir = Path(a.backup_dir) / f"workhours-{time.strftime('%Y%m%d-%H%M%S')}"
    bdir.mkdir(parents=True, exist_ok=True)
    if p.exists():
        shutil.copy2(p, bdir / "workhours.json")
    if not a.no_service:
        subprocess.run(["systemctl", "stop", "igbot-telegram"], check=False)
    try:
        st = p.stat() if p.exists() else None
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, p)
        if st:
            try:
                os.chown(p, st.st_uid, st.st_gid)
            except OSError:
                pass
    finally:
        if not a.no_service:
            subprocess.run(["systemctl", "start", "igbot-telegram"], check=False)
    print(f"\n✅ اعمال شد (بکاپ: {bdir})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
