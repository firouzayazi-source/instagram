#!/usr/bin/env bash
# Run the bot without Docker: Python venv + systemd service on 127.0.0.1:8010
# (the same port the nginx site from install.sh proxies to).
#   bash /opt/instagram-bot/deploy/install-native.sh
# Run it again after every `git pull` to update dependencies and restart.
set -euo pipefail

DIR=/opt/instagram-bot
PY="${PYTHON:-/usr/local/bin/python3.12}"
UNIT=/etc/systemd/system/instagram-bot.service
cd "$DIR"

echo "== 1) Python"
[ -x "$PY" ] || PY="$(command -v python3.12 || command -v python3)"
"$PY" -c 'import sys; assert sys.version_info >= (3, 10), sys.version' \
  || { echo "✘ Python 3.10+ لازم است"; exit 1; }
echo "✔ $("$PY" --version)"

echo "== 2) venv + packages"
[ -d venv ] || "$PY" -m venv venv
venv/bin/pip install -q --upgrade pip
venv/bin/pip install -q -r requirements.txt
echo "✔ packages installed"

echo "== 3) user and permissions"
id instagram-bot >/dev/null 2>&1 || useradd --system --home "$DIR" --shell /usr/sbin/nologin instagram-bot
mkdir -p data
chown -R instagram-bot:instagram-bot data
chown instagram-bot:instagram-bot .env && chmod 600 .env
echo "✔ runs as user instagram-bot"

echo "== 4) systemd"
cat > "$UNIT" <<EOF
[Unit]
Description=Instagram reply bot (Telegram approval)
After=network-online.target
Wants=network-online.target

[Service]
User=instagram-bot
WorkingDirectory=$DIR
Environment=DATA_DIR=$DIR/data
Environment=PYTHONUNBUFFERED=1
ExecStart=$DIR/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010
Restart=always
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=$DIR/data
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable -q instagram-bot
systemctl restart instagram-bot

up=""
for i in $(seq 1 30); do
  if curl -s -m 2 http://127.0.0.1:8010/ | grep -q '"ok"'; then up=1; break; fi
  sleep 1
done
if [ -n "$up" ]; then
  echo "✅ ربات روشن است"
else
  echo "✘ ربات بالا نیامد. لاگ:"
  journalctl -u instagram-bot -n 30 --no-pager
  exit 1
fi
sleep 5
journalctl -u instagram-bot -n 20 --no-pager | grep -E "Telegram webhook|WARNING|ERROR|Traceback" || true
