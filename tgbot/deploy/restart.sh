#!/usr/bin/env bash
# ری‌استارت امن ربات — روی وی‌پی‌اس:  bash deploy/restart.sh
# فقط پروسه‌های همین پروژه را لمس می‌کند؛ به سرویس‌های دیگر سرور کاری ندارد.
set -u
DIR="$(cd "$(dirname "$0")/.." && pwd)"
SVC=telegram-bot

echo "▶ توقف سرویس..."
systemctl stop "$SVC" 2>/dev/null

# اگر پروسه‌ای از همین پروژه جا مانده، فقط همان را ببند
LEFT=$(pgrep -f "$DIR/venv/bin/python" || true)
if [ -n "$LEFT" ]; then
  echo "▶ پروسه‌ی جامانده پیدا شد ($LEFT) — بسته می‌شود"
  pkill -f "$DIR/venv/bin/python" 2>/dev/null
  sleep 2
  pkill -9 -f "$DIR/venv/bin/python" 2>/dev/null
fi

systemctl reset-failed "$SVC" 2>/dev/null
echo "▶ شروع سرویس..."
systemctl start "$SVC"
sleep 3

STATE=$(systemctl is-active "$SVC" 2>/dev/null)
echo
if [ "$STATE" = "active" ]; then
  echo "✅ سرویس فعال است"
else
  echo "❌ سرویس فعال نشد (وضعیت: ${STATE:-نامشخص})"
fi
echo
echo "──────── ۱۵ خط آخر لاگ ────────"
journalctl -u "$SVC" -n 15 --no-pager
