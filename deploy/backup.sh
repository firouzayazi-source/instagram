#!/usr/bin/env bash
# بکاپ شبانه‌ی SQLite؛ ۱۴ روز نگه می‌دارد. در cron: 0 4 * * * /opt/igbot/deploy/backup.sh
set -euo pipefail
SRC=/opt/igbot/data/bot.db
DST=/var/backups/igbot
mkdir -p "$DST"
sqlite3 "$SRC" ".backup '$DST/bot-$(date +%F).db'"
find "$DST" -name 'bot-*.db' -mtime +14 -delete
