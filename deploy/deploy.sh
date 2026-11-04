#!/usr/bin/env bash
# انتشار روی سرور: کد تازه، وابستگی‌ها، ساخت پنل، تست، راه‌اندازی مجدد، وارسی سلامت.
# فقط به /opt/igbot و سرویس igbot دست می‌زند.
# کل اسکریپت داخل تابع است تا bash پیش از اجرا همه‌اش را بخواند؛ وگرنه git pull وسط اجرا خود همین فایل را عوض می‌کند.
set -euo pipefail

main() {
  cd /opt/igbot
  # مخزن مال کاربر igbot است و اسکریپت با root اجرا می‌شود
  git -c safe.directory=/opt/igbot pull --ff-only
  .venv/bin/pip install -q -r requirements.txt
  (cd web && npm ci --no-audit --no-fund --silent && npm run build --silent)
  # تست‌ها هرگز روی داده‌ی زنده: مسیرها به پوشه‌ی موقت (لایه‌ی دوم ایمنی کنار tests/conftest.py)
  T=$(mktemp -d)
  DB_PATH=$T/bot.db TG_DATA_DIR=$T/telegram .venv/bin/python -m pytest -q -p no:cacheprovider
  rm -rf "$T"

  # فایل سرویس اگر در ریپو عوض شده باشد، با بکاپ از نسخه‌ی قبلی
  if ! cmp -s deploy/igbot.service /etc/systemd/system/igbot.service; then
    mkdir -p /var/backups/igbot
    cp /etc/systemd/system/igbot.service "/var/backups/igbot/igbot.service.$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
    cp deploy/igbot.service /etc/systemd/system/igbot.service
    systemctl daemon-reload
    echo "فایل سرویس به‌روز شد"
  fi

  # ربات تلگرام: فقط اگر منتقل شده باشد (deploy/migrate-telegram.sh) به‌روز و ری‌استارت می‌شود
  if [ -f /etc/systemd/system/igbot-telegram.service ] && ! cmp -s deploy/igbot-telegram.service /etc/systemd/system/igbot-telegram.service; then
    mkdir -p /var/backups/igbot
    cp /etc/systemd/system/igbot-telegram.service "/var/backups/igbot/igbot-telegram.service.$(date +%Y%m%d-%H%M%S)"
    cp deploy/igbot-telegram.service /etc/systemd/system/igbot-telegram.service
    systemctl daemon-reload
    echo "فایل سرویس تلگرام به‌روز شد"
  fi

  chown -R igbot:igbot /opt/igbot
  [ -f /opt/igbot/.env ] && chmod 600 /opt/igbot/.env   # رازها فقط برای کاربر igbot
  systemctl restart igbot
  if systemctl is-enabled --quiet igbot-telegram 2>/dev/null; then
    systemctl restart igbot-telegram
    sleep 3
    systemctl is-active --quiet igbot-telegram && echo "ربات تلگرام فعال است" || { echo "❌ ربات تلگرام بالا نیامد"; journalctl -u igbot-telegram -n 20 --no-pager; }
  fi
  sleep 2
  curl -fsS https://ig.stland.ir/health && echo
}

main "$@"
