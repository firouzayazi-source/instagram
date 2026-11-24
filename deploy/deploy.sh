#!/usr/bin/env bash
# انتشار روی سرور: کد تازه، وابستگی‌ها، ساخت پنل، تست، راه‌اندازی مجدد، وارسی سلامت.
# فقط به /opt/igbot و سرویس igbot دست می‌زند.
# کل اسکریپت داخل تابع است تا bash پیش از اجرا همه‌اش را بخواند؛ وگرنه git pull وسط اجرا خود همین فایل را عوض می‌کند.
set -Eeuo pipefail

G="git -c safe.directory=/opt/igbot"
PREV=""; BKFILE=""

# برگشت به نسخه‌ی قبلی: کد، وابستگی‌ها، پنل، مالکیت و سرویس‌ها؛ پایگاه داده دست نمی‌خورد (تغییرهای پایگاه داده افزایشی‌اند)
# ولی راه بازگرداندن بکاپ پیش از انتشار چاپ می‌شود
rollback() {
  trap - ERR
  [ -n "$PREV" ] || exit 1
  echo "↩️ برگشت به نسخه‌ی قبلی ($PREV)"
  cd /opt/igbot
  $G reset -q --hard "$PREV"
  .venv/bin/pip install -q -r requirements.txt || true
  (cd web && npm ci --no-audit --no-fund --silent && npm run build --silent) || true
  chown -R igbot:igbot /opt/igbot
  if [ "${RESTARTED:-0}" = 1 ]; then
    systemctl restart igbot || true
    systemctl is-enabled --quiet igbot-telegram 2>/dev/null && systemctl restart igbot-telegram || true
    systemctl is-enabled --quiet igbot-bale 2>/dev/null && systemctl restart igbot-bale || true
  fi
  [ -n "$BKFILE" ] && echo "اگر پایگاه داده هم باید برگردد: systemctl stop igbot && sudo -u igbot cp $BKFILE /opt/igbot/data/bot.db && rm -f /opt/igbot/data/bot.db-wal /opt/igbot/data/bot.db-shm && systemctl start igbot"
  exit 1
}

main() {
  umask 077     # بکاپ‌ها رمز و شماره‌ی مشتری دارند: فقط root
  cd /opt/igbot
  # بکاپ پیش از انتشار: اگر نسخه‌ی تازه ستون یا جدولی به پایگاه داده اضافه کند و مشکلی پیش بیاید، راه برگشت هست
  BK=/var/backups/igbot; mkdir -p "$BK"; STAMP=$(date +%Y%m%d-%H%M%S)
  if [ -f data/bot.db ]; then
    sqlite3 data/bot.db ".backup '$BK/pre-deploy-$STAMP.db'"      # اگر نشد، set -e انتشار را متوقف می‌کند
    chmod 600 "$BK/pre-deploy-$STAMP.db"; BKFILE="$BK/pre-deploy-$STAMP.db"
    # ربات تلگرام هم با همین انتشار به‌روز و ری‌استارت می‌شود
    if [ -f data/telegram/users.db ]; then
      sqlite3 data/telegram/users.db ".backup '$BK/pre-deploy-tg-$STAMP.db'" && chmod 600 "$BK/pre-deploy-tg-$STAMP.db"
      ls -1t "$BK"/pre-deploy-tg-*.db 2>/dev/null | tail -n +6 | xargs -r rm -f
    fi
    echo "بکاپ پیش از انتشار: $BK/pre-deploy-$STAMP.db (commit قبلی: $(git -c safe.directory=/opt/igbot rev-parse --short HEAD))"
    ls -1t "$BK"/pre-deploy-2*.db 2>/dev/null | tail -n +6 | xargs -r rm -f      # فقط ۵ تای آخر
  fi
  # مخزن مال کاربر igbot است و اسکریپت با root اجرا می‌شود
  PREV=$($G rev-parse HEAD)
  $G pull --ff-only
  trap rollback ERR     # از اینجا هر خطا (نصب، ساخت، تست، سلامت) به نسخه‌ی قبلی برمی‌گردد
  umask 022
  .venv/bin/pip install -q -U "pip<27"
  # eager: وابستگی‌های فرعی (pydantic، click، …) هم در محدوده‌ی سقف‌های requirements.txt به‌روز شوند؛ تست‌ها بعدش
  .venv/bin/pip install -q -U --upgrade-strategy eager -r requirements.txt
  (cd web && npm ci --no-audit --no-fund --silent && npm run build --silent)
  # تست‌ها هرگز روی داده‌ی زنده: مسیرها به پوشه‌ی موقت (لایه‌ی دوم ایمنی کنار tests/conftest.py)
  T=$(mktemp -d)
  # متغیرهای ربات در پوسته‌ی سرور (توکن، آیدی مدیر) به تست‌ها نرسند: تست با مقدار ساختگی خودش (۳ آذر ۱۴۰۵، یک تست با ADMIN_ID واقعی رد شد)
  if ! env -u BOT_TOKEN -u ADMIN_ID -u BOT_PLATFORM -u BALE_BOT_TOKEN -u BALE_ADMIN_ID -u KNOWLEDGE_DIR \
       DB_PATH=$T/bot.db TG_DATA_DIR=$T/telegram .venv/bin/python -m pytest -q -p no:cacheprovider; then
    rm -rf "$T"
    # کد تست‌نشده روی دیسک نماند (با ری‌استارت یا کرش بالا می‌آمد)
    echo "❌ تست‌ها رد شد"
    rollback
  fi
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

  # ربات بله: فقط اگر با deploy/enable-bale.sh راه افتاده باشد
  if [ -f /etc/systemd/system/igbot-bale.service ] && ! cmp -s deploy/igbot-bale.service /etc/systemd/system/igbot-bale.service; then
    cp deploy/igbot-bale.service /etc/systemd/system/igbot-bale.service
    systemctl daemon-reload
    echo "فایل سرویس بله به‌روز شد"
  fi

  chown -R igbot:igbot /opt/igbot
  [ -f /opt/igbot/.env ] && chmod 600 /opt/igbot/.env   # رازها فقط برای کاربر igbot
  RESTARTED=1
  systemctl restart igbot
  if systemctl is-enabled --quiet igbot-telegram 2>/dev/null; then
    systemctl restart igbot-telegram
    sleep 3
    if systemctl is-active --quiet igbot-telegram; then echo "ربات تلگرام فعال است"
    else echo "❌ ربات تلگرام بالا نیامد"; journalctl -u igbot-telegram -n 20 --no-pager; rollback; fi
  fi
  if systemctl is-enabled --quiet igbot-bale 2>/dev/null; then
    systemctl restart igbot-bale
    sleep 3
    if systemctl is-active --quiet igbot-bale; then echo "ربات بله فعال است"
    else echo "⚠️ ربات بله بالا نیامد (بقیه سالم است)"; journalctl -u igbot-bale -n 20 --no-pager; fi
  fi
  sleep 2
  if ! curl -fsS https://ig.stland.ir/health; then echo; echo "❌ پنل سالم بالا نیامد"; journalctl -u igbot -n 20 --no-pager; rollback; fi
  echo
  trap - ERR
}

main "$@"
