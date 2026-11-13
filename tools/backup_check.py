"""آزمون بازگردانی بکاپ شبانه: آخرین بکاپ‌ها واقعاً باز می‌شوند و داده دارند؟

بعد از هر بکاپ از deploy/backup.sh اجرا می‌شود. آخرین bot-*.db و tg-users-*.db را در پوشه‌ی موقت کپی
می‌کند (خود بکاپ دست نمی‌خورد)، integrity_check می‌گیرد، همان راه‌اندازی برنامه (ساخت جدول‌ها و ارتقا) را
رویش اجرا می‌کند و تعداد ردیف‌های جدول‌های اصلی را با پایگاه داده‌ی زنده مقایسه می‌کند. نتیجه در
پایگاه داده‌ی زنده (kv: backup_check) نوشته می‌شود و اگر خراب بود، نظارت پنل به تلگرام مدیر هشدار می‌دهد.

    sudo -u igbot /opt/igbot/.venv/bin/python /opt/igbot/tools/backup_check.py /var/backups/igbot
"""
import json
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TABLES = ("rules", "customers", "comments", "messages")


def latest(d: Path, pattern: str) -> Path | None:
    xs = sorted(d.glob(pattern))
    return xs[-1] if xs else None


def check_db(path: Path, live: Path | None = None, app_schema: bool = False) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t) / path.name
        shutil.copy2(path, tmp)
        try:
            with sqlite3.connect(tmp) as c:
                ok = c.execute("PRAGMA integrity_check").fetchone()[0]
                if ok != "ok":
                    return False, f"{path.name}: integrity_check ← {ok[:100]}"
            if app_schema:
                from app import db
                db.init(str(tmp))                     # همان راه‌اندازی برنامه، روی کپی
                with sqlite3.connect(tmp) as c, (sqlite3.connect(f"file:{live}?mode=ro", uri=True) if live and live.exists() else _Null()) as lv:
                    for tb in TABLES:
                        n = c.execute(f"SELECT COUNT(*) FROM {tb}").fetchone()[0]
                        if lv is not None:
                            m = lv.execute(f"SELECT COUNT(*) FROM {tb}").fetchone()[0]
                            if m >= 20 and n < m * 0.5:          # بکاپ دیشب نباید نصف داده‌ی امروز باشد
                                return False, f"{path.name}: جدول {tb} فقط {n} ردیف (زنده: {m})"
        except sqlite3.Error as e:
            return False, f"{path.name}: باز نشد ({e})"
    return True, f"{path.name}: سالم"


class _Null:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


def run(backup_dir: Path, live_db: Path, max_age_h: float = 30) -> dict:
    notes, ok = [], True
    b = latest(backup_dir, "bot-*.db")
    if not b:
        ok = False
        notes.append("بکاپ پایگاه داده‌ی پنل پیدا نشد")
    else:
        if time.time() - b.stat().st_mtime > max_age_h * 3600:
            ok = False
            notes.append(f"آخرین بکاپ ({b.name}) قدیمی است")
        r, msg = check_db(b, live_db, app_schema=True)
        ok &= r
        notes.append(msg)
    t = latest(backup_dir, "tg-users-*.db")
    if t:
        r, msg = check_db(t)
        ok &= r
        notes.append(msg)
    return {"at": time.time(), "ok": ok, "error": "" if ok else "؛ ".join(n for n in notes if "سالم" not in n), "notes": notes}


def main() -> int:
    from app import config, db
    backup_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "/var/backups/igbot")
    res = run(backup_dir, Path(config.DB_PATH))
    try:
        with db.connect() as c:
            db.kv_set(c, "backup_check", json.dumps(res, ensure_ascii=False))
    except sqlite3.Error as e:
        print("ثبت نتیجه نشد:", e)
    print(("✅ " if res["ok"] else "❌ ") + " | ".join(res["notes"]))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
