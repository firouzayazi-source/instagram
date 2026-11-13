#!/usr/bin/env bash
# بازنشستگی ربات تلگرام قدیمی (پوشه‌ی /opt/telegram-bot و سرویس telegram-bot) که از ۱۱ آبان فقط برای برگشت
# نگه داشته شده بود. صاحب پروژه ۲۲ آبان ۱۴۰۵ تأیید کرد.
#   بدون --apply: فقط وارسی و گزارش؛ هیچ چیز تغییر نمی‌کند.
#   با --apply: اول بایگانی کامل پوشه (با دسترسی ۶۰۰ در /var/backups/igbot)، بعد برداشتن سرویس و پوشه.
# فقط به همین پوشه و همین سرویس دست می‌زند؛ کلیدها و تنظیمات SSH، سرویس‌های دیگر و داده‌ی
# /opt/igbot/data/telegram دست نمی‌خورند. هیچ رازی چاپ نمی‌شود.
set -euo pipefail

main() {
  OLD=/opt/telegram-bot
  UNIT=/etc/systemd/system/telegram-bot.service
  BK=/var/backups/igbot
  APPLY=${1:-}

  echo "▶ وارسی"
  systemctl is-active --quiet igbot-telegram || { echo "❌ سرویس igbot-telegram فعال نیست؛ ربات قدیمی برداشته نمی‌شود"; exit 1; }
  [ -s /opt/igbot/data/telegram/users.db ] || { echo "❌ داده‌ی ربات در /opt/igbot/data/telegram نیست؛ چیزی تغییر نکرد"; exit 1; }
  echo "✅ ربات تازه (igbot-telegram) فعال است و داده‌اش سر جاست"
  if systemctl is-active --quiet telegram-bot 2>/dev/null; then
    echo "❌ سرویس قدیمی telegram-bot هنوز روشن است (دو ربات با یک توکن)؛ اول بررسی شود. چیزی تغییر نکرد"; exit 1
  fi
  [ -d "$OLD" ] && echo "پوشه‌ی قدیمی: $OLD ($(du -sh "$OLD" | cut -f1))" || echo "پوشه‌ی قدیمی از قبل نیست"
  [ -f "$UNIT" ] && echo "فایل سرویس قدیمی: $UNIT" || echo "فایل سرویس قدیمی از قبل نیست"

  if [ ! -d "$OLD" ] && [ ! -f "$UNIT" ]; then
    echo; echo "✅ چیزی برای بازنشستگی نمانده؛ ربات قدیمی از قبل برداشته شده است."; return
  fi
  if [ "$APPLY" != "--apply" ]; then
    echo; echo "فقط وارسی بود. برای اجرا: sudo bash $0 --apply"; return
  fi

  mkdir -p "$BK"
  STAMP=$(date +%Y%m%d-%H%M%S)
  if [ -d "$OLD" ]; then
    echo "▶ بایگانی پوشه‌ی قدیمی"
    ARC="$BK/telegram-bot-retired-$STAMP.tar.gz"
    tar -czf "$ARC" -C /opt telegram-bot
    chmod 600 "$ARC"
    tar -tzf "$ARC" > /dev/null && echo "✅ بایگانی سالم: $ARC" || { echo "❌ بایگانی خراب؛ چیزی پاک نشد"; exit 1; }
  fi
  if [ -f "$UNIT" ]; then
    echo "▶ برداشتن سرویس قدیمی"
    systemctl disable telegram-bot 2>/dev/null || true
    cp "$UNIT" "$BK/telegram-bot.service.retired-$STAMP"
    rm -f "$UNIT"
    systemctl daemon-reload
  fi
  if [ -d "$OLD" ]; then
    echo "▶ پاک کردن پوشه‌ی قدیمی"
    rm -rf "$OLD"
  fi
  echo "✅ ربات قدیمی بازنشسته شد. برگشت (در صورت نیاز): از بایگانی بالا در /opt باز شود."
  systemctl is-active --quiet igbot-telegram && echo "✅ ربات تلگرام فعلی همچنان فعال است"
}

main "$@"
