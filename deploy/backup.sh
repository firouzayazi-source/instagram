#!/usr/bin/env bash
# بکاپ شبانه؛ ۱۴ روز نگه می‌دارد. در cron: 0 4 * * * /opt/igbot/deploy/backup.sh
set -euo pipefail
umask 077                      # بکاپ‌ها رمز، نشست و شماره‌ی مشتری دارند: فقط root
DST=/var/backups/igbot
mkdir -p "$DST"; chmod 700 "$DST"
D=$(date +%F)

# اینستاگرام و پنل
sqlite3 /opt/igbot/data/bot.db ".backup '$DST/bot-$D.db'"

# ربات تلگرام (بعد از انتقال): دیتابیس با .backup، فایل‌های JSON در یک tar
TG=/opt/igbot/data/telegram
if [ -d "$TG" ]; then
  [ -f "$TG/users.db" ] && sqlite3 "$TG/users.db" ".backup '$DST/tg-users-$D.db'"
  # (--wildcards هنگام ساختن بایگانی الگو را باز نمی‌کند و بایگانی خالی می‌ساخت؛ حالا پوسته فهرست را می‌سازد)
  ( cd "$TG" && shopt -s nullglob && files=(*.json) && [ ${#files[@]} -gt 0 ] && tar -czf "$DST/tg-json-$D.tar.gz" "${files[@]}" ) \
    || echo "❌ بکاپ فایل‌های JSON ربات تلگرام ساخته نشد"
fi

# ربات بله (اگر راه افتاده باشد): همان شکل
BL=/opt/igbot/data/bale
if [ -f "$BL/users.db" ]; then
  sqlite3 "$BL/users.db" ".backup '$DST/bale-users-$D.db'"
  ( cd "$BL" && shopt -s nullglob && files=(*.json) && [ ${#files[@]} -gt 0 ] && tar -czf "$DST/bale-json-$D.tar.gz" "${files[@]}" ) || true
fi

# رازها و کلیدها (.env، کلید داخلی، کانال‌ها): بی این‌ها بعد از از دست رفتن سرور همه‌ی اتصال‌ها از صفر ساخته می‌شوند.
# فقط root می‌خواند (۶۰۰).
# فقط فایل‌هایی که هستند (نبودن یکی، بقیه را از بایگانی بیرون نیندازد)
( umask 077; cd /opt/igbot && files=(); for f in .env data/internal.key data/channels.json; do [ -f "$f" ] && files+=("$f"); done
  tar -czf "$DST/secrets-$D.tar.gz" "${files[@]}" )
chmod 600 "$DST/secrets-$D.tar.gz"

find "$DST" \( -name 'bot-*.db' -o -name 'tg-users-*.db' -o -name 'tg-json-*.tar.gz' -o -name 'bale-users-*.db' -o -name 'bale-json-*.tar.gz' -o -name 'secrets-*.tar.gz' \) -mtime +14 -delete

# آزمون بازگردانی: آخرین بکاپ‌ها باز می‌شوند و داده دارند؟ نتیجه در پنل و هشدار تلگرام (tools/backup_check.py)
if [ -x /opt/igbot/.venv/bin/python ]; then
  # با root (پوشه‌ی /var/backups فقط برای root باز است)؛ خود اسکریپت نتیجه را با کاربر igbot ثبت می‌کند
  (cd /opt/igbot && /opt/igbot/.venv/bin/python tools/backup_check.py "$DST") || echo "❌ آزمون بکاپ ناموفق؛ پنل و تلگرام را ببینید"
fi

# نسخه‌ی بیرون از سرور (اختیاری): اگر BACKUP_COPY_DIR در .env باشد (مثلاً دیسک یا فضای ذخیره‌ی جدا که روی سرور
# mount شده)، بکاپ امشب آنجا هم کپی می‌شود. مقصد را صاحب سرور تعیین می‌کند؛ این اسکریپت کلید یا اتصال تازه نمی‌سازد.
COPY_DIR=$(grep -E '^BACKUP_COPY_DIR=' /opt/igbot/.env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "\"'" || true)
if [ -n "${COPY_DIR:-}" ] && [ ! -d "$COPY_DIR" ]; then
  echo "❌ مقصد کپی بیرونی ($COPY_DIR) پیدا نشد (mount نیست؟)؛ کپی بیرونی امشب انجام نشد"
fi
if [ -n "${COPY_DIR:-}" ] && [ -d "$COPY_DIR" ]; then
  for f in bot-"$D".db tg-users-"$D".db tg-json-"$D".tar.gz; do
    [ -f "$DST/$f" ] && { cp -p "$DST/$f" "$COPY_DIR"/ || echo "❌ کپی بیرونی $f ناموفق"; }
  done
  # رازها فقط اگر صاحب سرور صریح خواسته باشد (BACKUP_COPY_SECRETS=1)؛ مقصد بیرونی باید امن باشد
  if grep -qE '^BACKUP_COPY_SECRETS=1' /opt/igbot/.env 2>/dev/null; then
    cp -p "$DST"/secrets-"$D".tar.gz "$COPY_DIR"/ || echo "❌ کپی بیرونی رازها ناموفق"
  fi
  find "$COPY_DIR" \( -name 'bot-*.db' -o -name 'tg-users-*.db' -o -name 'tg-json-*.tar.gz' -o -name 'secrets-*.tar.gz' \) -mtime +30 -delete 2>/dev/null || true
fi
