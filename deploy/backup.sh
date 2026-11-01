#!/usr/bin/env bash
# بکاپ شبانه‌ی SQLite؛ ۱۴ روز نگه می‌دارد. در cron: 0 4 * * * /opt/instagram-bot/deploy/backup.sh
set -euo pipefail
SRC=/opt/instagram-bot/data/bot.db
DST=/var/backups/instagram-bot
mkdir -p "$DST"
sqlite3 "$SRC" ".backup '$DST/bot-$(date +%F).db'"
find "$DST" -name 'bot-*.db' -mtime +14 -delete
