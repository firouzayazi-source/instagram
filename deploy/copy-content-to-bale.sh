#!/usr/bin/env bash
# محتوای ربات تلگرام (متن بخش‌ها، منو، ساعت کاری، دکمه‌ها، مکان‌ها، سؤال‌های آماده، بخش‌های سفارشی، یادگرفته‌ها)
# را به ربات بله کپی می‌کند. فقط /opt/igbot/data/bale عوض می‌شود؛ اول از فایل‌های فعلی بله بکاپ گرفته می‌شود.
# کپی نمی‌شود: مشتری‌ها (users.db)، مدیرها، تنظیمات، آمار، تاپیک‌ها، بنرها و عکس‌ها
# (شناسه‌ی عکس تلگرام در بله کار نمی‌کند؛ عکس‌ها را از پنل خود ربات بله دوباره بگذارید).
set -Eeuo pipefail
TG=/opt/igbot/data/telegram; BL=/opt/igbot/data/bale
[ -d "$TG" ] && [ -d "$BL" ] || { echo "❌ پوشه‌ی داده‌ی تلگرام یا بله نیست (اول enable-bale.sh)"; exit 1; }
FILES="data.json workhours.json buttons.json menu.json places.json faq.json pages.json learn.json"
BK=/var/backups/igbot/bale-before-copy-$(date +%Y%m%d-%H%M%S); mkdir -p "$BK"; chmod 700 "$BK"
systemctl stop igbot-bale
for f in $FILES; do
  [ -f "$BL/$f" ] && cp -p "$BL/$f" "$BK/"
  [ -f "$TG/$f" ] && cp "$TG/$f" "$BL/$f"
done
# عکس‌های سؤال‌های آماده (شناسه‌ی تلگرام) برداشته می‌شوند تا ارسال در بله خطا ندهد
/opt/igbot/.venv/bin/python - "$BL/faq.json" <<'PY'
import json, sys
p = sys.argv[1]
try:
    d = json.load(open(p, encoding="utf-8"))
except (OSError, ValueError):
    sys.exit(0)
n = 0
for it in d if isinstance(d, list) else []:
    if isinstance(it, dict) and it.pop("photo", None):
        n += 1
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"عکس برداشته‌شده از سؤال‌های آماده: {n}")
PY
chown -R igbot:igbot "$BL"; chmod 600 "$BL"/*.json
systemctl start igbot-bale; sleep 3
if systemctl is-active --quiet igbot-bale; then echo "✅ محتوا کپی شد و ربات بله فعال است (بکاپ فایل‌های قبلی بله: $BK)"
else echo "❌ ربات بله بالا نیامد"; journalctl -u igbot-bale -n 20 --no-pager; exit 1; fi
