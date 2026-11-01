#!/usr/bin/env bash
# انتشار روی سرور: کد تازه، وابستگی‌ها، ساخت پنل، تست، راه‌اندازی مجدد، وارسی سلامت
set -euo pipefail
cd /opt/igbot
git pull --ff-only
.venv/bin/pip install -q -r requirements.txt
(cd web && npm ci --no-audit --no-fund --silent && npm run build --silent)
.venv/bin/python -m pytest -q
sudo systemctl restart igbot
sleep 2
curl -fsS https://ig.stland.ir/health && echo
