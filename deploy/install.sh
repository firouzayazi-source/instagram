#!/usr/bin/env bash
# One-time setup on a server that already runs nginx + certbot.
#   bash /opt/instagram-bot/deploy/install.sh ig.stland.ir
# Safe to run again: it only adds this bot's own nginx site and never touches other sites.
set -euo pipefail

DOMAIN="${1:-ig.stland.ir}"
DIR=/opt/instagram-bot
SITE=/etc/nginx/sites-available/instagram-bot
cd "$DIR"

echo "== 1) DNS"
MYIP=$(curl -4 -s -m 8 https://api.ipify.org || true)
DNSIP=$(getent ahostsv4 "$DOMAIN" | awk '{print $1; exit}' || true)
if [ -z "$DNSIP" ]; then echo "✘ $DOMAIN هنوز به هیچ IP اشاره نمی‌کند. چند دقیقه بعد دوباره اجرا کنید."; exit 1; fi
if [ "$DNSIP" != "$MYIP" ]; then
  echo "✘ $DOMAIN به $DNSIP اشاره می‌کند ولی IP این سرور $MYIP است."
  echo "  اگر رکورد در Cloudflare است: ابر نارنجی (Proxied) را خاکستری کنید (DNS only)، مثل بقیه‌ی رکوردهای stland.ir."
  exit 1
fi
echo "✔ $DOMAIN -> $DNSIP"

echo "== 2) .env"
if [ ! -f .env ]; then
  cp .env.example .env
  sed -i "s|^PUBLIC_URL=.*|PUBLIC_URL=https://$DOMAIN|; s|^DOMAIN=.*|DOMAIN=$DOMAIN|" .env
  sed -i "s|^IG_VERIFY_TOKEN=.*|IG_VERIFY_TOKEN=$(openssl rand -hex 16)|" .env
  sed -i "s|^TELEGRAM_WEBHOOK_SECRET=.*|TELEGRAM_WEBHOOK_SECRET=$(openssl rand -hex 24)|" .env
  echo "✔ .env ساخته شد (PUBLIC_URL، IG_VERIFY_TOKEN و TELEGRAM_WEBHOOK_SECRET خودکار پر شد)"
else
  echo "✔ .env از قبل هست؛ دست نخورد"
fi
chmod 600 .env
mkdir -p data

echo "== 3) nginx"
if [ ! -f "$SITE" ]; then
  sed "s/ig.example.com/$DOMAIN/" deploy/nginx-instagram-bot.conf > "$SITE"
  ln -sf "$SITE" /etc/nginx/sites-enabled/instagram-bot
fi
nginx -t
systemctl reload nginx
echo "✔ سایت nginx فعال شد"

echo "== 4) SSL"
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --redirect --keep-until-expiring \
  --register-unsafely-without-email
echo "✔ گواهی SSL گرفته شد"

echo
echo "✅ آماده است. قدم بعد: کلیدها را در .env بنویسید:"
echo "   nano $DIR/.env"
