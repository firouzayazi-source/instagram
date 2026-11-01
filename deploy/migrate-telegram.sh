#!/usr/bin/env bash
# یک‌بار: ربات تلگرام از /opt/telegram-bot به igbot منتقل می‌شود.
# پوشه‌ی قدیمی دست نمی‌خورد تا برگشت ممکن باشد. هیچ رازی چاپ نمی‌شود.
set -euo pipefail

main() {
  OLD=/opt/telegram-bot
  NEW=/opt/igbot
  DATA=$NEW/data/telegram

  [ -d "$OLD" ] || { echo "پوشه‌ی $OLD نیست"; exit 1; }
  [ -f "$NEW/tgbot/bot.py" ] || { echo "اول /opt/igbot/deploy/deploy.sh را اجرا کنید"; exit 1; }
  [ -e "$DATA/users.db" ] && { echo "داده قبلاً منتقل شده است ($DATA)"; exit 1; }

  # کلیدهای ربات از .env قدیمی، فقط اگر در .env igbot نیستند
  for k in BOT_TOKEN ADMIN_ID FORCE_IPV4; do
    if ! grep -q "^$k=" "$NEW/.env" && grep -q "^$k=" "$OLD/.env"; then
      grep "^$k=" "$OLD/.env" >> "$NEW/.env"
      echo "✅ $k به ‎/opt/igbot/.env اضافه شد"
    fi
  done
  grep -q "^BOT_TOKEN=." "$NEW/.env" || { echo "BOT_TOKEN پیدا نشد؛ چیزی تغییر نکرد"; exit 1; }

  echo "▶ توقف ربات قدیمی"
  systemctl stop telegram-bot || true
  systemctl disable telegram-bot 2>/dev/null || true

  echo "▶ انتقال داده"
  mkdir -p "$DATA"
  if [ -f "$OLD/users.db" ]; then
    sqlite3 "$OLD/users.db" ".backup '$DATA/users.db'"   # سازگار با WAL
  fi
  cp -p "$OLD"/*.json "$DATA"/ 2>/dev/null || true
  chown -R igbot:igbot "$DATA"
  echo "   $(ls "$DATA" | wc -l) فایل در $DATA"

  echo "▶ راه‌اندازی igbot-telegram"
  cp "$NEW/deploy/igbot-telegram.service" /etc/systemd/system/igbot-telegram.service
  systemctl daemon-reload
  systemctl enable --now igbot-telegram
  sleep 5
  if systemctl is-active --quiet igbot-telegram; then
    echo "✅ ربات تلگرام از igbot اجرا می‌شود"
  else
    echo "❌ igbot-telegram بالا نیامد؛ برای برگشت دستورهای زیر را بزنید"
  fi
  journalctl -u igbot-telegram -n 15 --no-pager || true
  echo
  echo "برگشت به ربات قدیمی در صورت نیاز:"
  echo "  systemctl disable --now igbot-telegram && systemctl enable --now telegram-bot"
}

main "$@"
