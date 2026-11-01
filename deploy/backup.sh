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
