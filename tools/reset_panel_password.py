"""بازیابی رمز پنل (ig.stland.ir) روی خود سرور؛ رمز هرگز در چت، ریپو یا لاگ نمی‌آید.

یک رمز تازه‌ی قوی و خوانا می‌سازد (یا با --ask خودتان دو بار تایپ می‌کنید)، فقط خط PANEL_PASSWORD را در
/opt/igbot/.env عوض می‌کند (بقیه‌ی خط‌ها و دسترسی ۶۰۰ و مالک فایل دست نمی‌خورد)، از .env قبلی بکاپ
می‌گیرد، همه‌ی ورودهای قبلی پنل را باطل می‌کند و سرویس igbot را ری‌استارت می‌کند. رمز تازه فقط یک بار
روی همین ترمینال نشان داده می‌شود.

    sudo python3 /opt/igbot/tools/reset_panel_password.py            # فقط توضیح
    sudo python3 /opt/igbot/tools/reset_panel_password.py --apply    # رمز تازه
"""
import argparse
import getpass
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORDS = "abcdefghjkmnpqrstuvwxyz23456789"          # بدون نویسه‌های شبیه هم (l/1، o/0، i)


def new_password() -> str:
    """چهار گروه پنج‌نویسه‌ای، مثل k7m2q-x9p4t-… (حدود ۹۷ بیت؛ خوانا برای تایپ روی گوشی)."""
    return "-".join("".join(secrets.choice(WORDS) for _ in range(5)) for _ in range(4))


def write_env(path: Path, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    out, done = [], False
    for ln in lines:
        if re.match(r"^\s*PANEL_PASSWORD\s*=", ln):
            if not done:
                out.append(f"PANEL_PASSWORD={value}")
            done = True
            continue
        out.append(ln)
    if not done:
        out.append(f"PANEL_PASSWORD={value}")
    st = path.stat() if path.exists() else None
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.ftruncate(fd, 0)
        os.write(fd, ("\n".join(out) + "\n").encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, 0o600)
    if st is not None:
        try:
            os.chown(path, st.st_uid, st.st_gid)
        except OSError:
            pass


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ask", action="store_true", help="رمز را خودتان (دو بار، بی‌نمایش) تایپ کنید")
    ap.add_argument("--env", default=os.environ.get("IGBOT_ENV_FILE") or str(ROOT / ".env"))
    ap.add_argument("--db", default=str(ROOT / "data" / "bot.db"))
    ap.add_argument("--backup-dir", default="/var/backups/igbot")
    ap.add_argument("--no-service", action="store_true", help="برای تست: سرویس را ری‌استارت نکن")
    a = ap.parse_args(argv)
    env = Path(a.env)
    print(f"فایل رمز: {env}\nکار: رمز تازه برای پنل، بکاپ از .env، خروج همه‌ی ورودهای قبلی، ری‌استارت igbot.")
    if not a.apply:
        print("فقط توضیح بود؛ برای ساختن رمز تازه: --apply")
        return 0
    if a.ask:
        pw = getpass.getpass("رمز تازه (حداقل ۴ نویسه): ")
        if len(pw) < 4 or pw != getpass.getpass("تکرار رمز: ") or re.search(r"\s", pw):
            sys.exit("رمز کوتاه است، فاصله دارد یا دو بار یکی نبود؛ چیزی عوض نشد.")
    else:
        pw = new_password()
    if env.exists():
        bdir = Path(a.backup_dir)
        bdir.mkdir(parents=True, exist_ok=True)
        b = bdir / f"env-before-password-reset-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(env, b)
        os.chmod(b, 0o600)
        print(f"بکاپ: {b}")
    write_env(env, pw)
    if Path(a.db).exists():
        with sqlite3.connect(a.db) as c:
            c.execute("DELETE FROM sessions")       # ورودهای قبلی (شاید روی دستگاه گم‌شده) باطل شوند
    if not a.no_service:
        subprocess.run(["systemctl", "restart", "igbot"], check=False)
    print("\n✅ رمز پنل عوض شد. همین الان جایی امن یادداشت کنید (این رمز دیگر نمایش داده نمی‌شود):\n")
    print(f"    {pw}" if not a.ask else "    (همان رمزی که تایپ کردید)")
    print("\nورود: https://ig.stland.ir")
    return 0


if __name__ == "__main__":
    sys.exit(main())
