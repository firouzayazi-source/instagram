# ربات اینستاگرام استوک لند

ربات مستقل پاسخ خودکار به کامنت و دایرکت پیج `stock_land.ir`، جایگزین نوین‌هاب. طرح کامل در `docs/PLAN.md`، وضعیت در `STATUS.md`.

## اجرا در محیط توسعه

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # مقدارها را پر کنید
python -m pytest -q
uvicorn app.main:app --reload --port 8010
```

## وارد کردن قانون‌ها

```bash
python -m app.importer rules.json
```

فرمت فایل در `app/importer.py` توضیح داده شده است.

## نصب روی سرور

```bash
sudo useradd -r -s /usr/sbin/nologin igbot
sudo git clone https://github.com/firouzayazi-source/instagram /opt/instagram-bot
cd /opt/instagram-bot
sudo python3 -m venv .venv && sudo .venv/bin/pip install -r requirements.txt
sudo cp .env.example .env && sudo chmod 600 .env && sudo nano .env
sudo mkdir -p data && sudo chown -R igbot:igbot /opt/instagram-bot
sudo cp deploy/instagram-bot.service /etc/systemd/system/
sudo cp deploy/nginx.conf /etc/nginx/sites-available/ig.stland.ir
sudo ln -s /etc/nginx/sites-available/ig.stland.ir /etc/nginx/sites-enabled/
sudo certbot --nginx -d ig.stland.ir
sudo systemctl daemon-reload && sudo systemctl enable --now instagram-bot
sudo nginx -t && sudo systemctl reload nginx
curl -s https://ig.stland.ir/health
```

بکاپ شبانه: `0 4 * * * /opt/instagram-bot/deploy/backup.sh` در crontab کاربر root.

## مسیرها
- `GET /health`: وضعیت سرویس و تعداد رویدادهای در صف
- `GET /webhook`: تأیید وبهوک متا
- `POST /webhook`: دریافت رویداد کامنت و پیام (با بررسی امضا)
