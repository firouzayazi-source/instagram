#!/usr/bin/env bash
# راه‌اندازی یک‌باره‌ی ربات «بله» (همان کد ربات تلگرام). فقط به /opt/igbot و سرویس igbot-bale دست می‌زند.
# پیش‌نیاز: در /opt/igbot/.env دو خط BALE_BOT_TOKEN=… و BALE_ADMIN_ID=… (آیدی عددی بله‌ی مدیرها) را خودتان بنویسید.
set -Eeuo pipefail
cd /opt/igbot
grep -q '^BALE_BOT_TOKEN=.\+' .env || { echo "❌ BALE_BOT_TOKEN در /opt/igbot/.env نیست"; exit 1; }
grep -q '^BALE_ADMIN_ID=[0-9]' .env || { echo "❌ BALE_ADMIN_ID در /opt/igbot/.env نیست"; exit 1; }
install -d -o igbot -g igbot -m 700 data/bale
cp deploy/igbot-bale.service /etc/systemd/system/igbot-bale.service
systemctl daemon-reload
systemctl enable --now igbot-bale
sleep 4
if systemctl is-active --quiet igbot-bale; then echo "✅ ربات بله فعال است"
else echo "❌ ربات بله بالا نیامد"; journalctl -u igbot-bale -n 30 --no-pager; exit 1; fi
