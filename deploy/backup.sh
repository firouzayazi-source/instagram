#!/usr/bin/env bash
# بکاپ شبانه؛ ۱۴ روز نگه می‌دارد. در cron: 0 4 * * * /opt/igbot/deploy/backup.sh
set -euo pipefail
DST=/var/backups/igbot
mkdir -p "$DST"
D=$(date +%F)

# اینستاگرام و پنل
sqlite3 /opt/igbot/data/bot.db ".backup '$DST/bot-$D.db'"

# ربات تلگرام (بعد از انتقال): دیتابیس با .backup، فایل‌های JSON در یک tar
TG=/opt/igbot/data/telegram
if [ -d "$TG" ]; then
  [ -f "$TG/users.db" ] && sqlite3 "$TG/users.db" ".backup '$DST/tg-users-$D.db'"
  tar -czf "$DST/tg-json-$D.tar.gz" -C "$TG" --wildcards '*.json' 2>/dev/null || true
fi

find "$DST" \( -name 'bot-*.db' -o -name 'tg-users-*.db' -o -name 'tg-json-*.tar.gz' \) -mtime +14 -delete

# آزمون بازگردانی: آخرین بکاپ‌ها باز می‌شوند و داده دارند؟ نتیجه در پنل و هشدار تلگرام (tools/backup_check.py)
if [ -x /opt/igbot/.venv/bin/python ]; then
  # با root (پوشه‌ی /var/backups فقط برای root باز است)؛ خود اسکریپت نتیجه را با کاربر igbot ثبت می‌کند
  (cd /opt/igbot && /opt/igbot/.venv/bin/python tools/backup_check.py "$DST") || echo "❌ آزمون بکاپ ناموفق؛ پنل و تلگرام را ببینید"
fi

# نسخه‌ی بیرون از سرور (اختیاری): اگر BACKUP_COPY_DIR در .env باشد (مثلاً دیسک یا فضای ذخیره‌ی جدا که روی سرور
# mount شده)، بکاپ امشب آنجا هم کپی می‌شود. مقصد را صاحب سرور تعیین می‌کند؛ این اسکریپت کلید یا اتصال تازه نمی‌سازد.
COPY_DIR=$(grep -E '^BACKUP_COPY_DIR=' /opt/igbot/.env 2>/dev/null | tail -1 | cut -d= -f2- || true)
if [ -n "${COPY_DIR:-}" ] && [ -d "$COPY_DIR" ]; then
  cp -p "$DST"/bot-"$D".db "$DST"/tg-users-"$D".db "$DST"/tg-json-"$D".tar.gz "$COPY_DIR"/ 2>/dev/null || echo "❌ کپی بیرونی بکاپ ناموفق"
  find "$COPY_DIR" \( -name 'bot-*.db' -o -name 'tg-users-*.db' -o -name 'tg-json-*.tar.gz' \) -mtime +30 -delete 2>/dev/null || true
fi
