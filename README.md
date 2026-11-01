# ربات اینستاگرام استوک لند

ربات مستقل پاسخ خودکار به کامنت و دایرکت پیج `stock_land.ir`، جایگزین نوین‌هاب. طرح کامل در `docs/PLAN.md`، وضعیت در `STATUS.md`.

## اجرا در محیط توسعه

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # مقدارها را پر کنید
python -m pytest -q
uvicorn app.main:app --reload --port 8011
```

## پنل (React PWA)

```bash
cd web && npm install && npm run dev     # توسعه، با پروکسی به بک‌اند روی 8011
cd web && npm run build                  # خروجی در web/dist؛ بک‌اند همان را سرو می‌کند
```

پنل روی `https://ig.stland.ir/` با رمز `PANEL_PASSWORD` باز می‌شود. روی گوشی با «Add to Home Screen» نصب می‌شود و بعد از فعال‌کردن اعلان در تنظیمات، اعلان پوش می‌گیرد. کلید اعلان:

```bash
.venv/bin/python -m app.push --gen   # دو خط خروجی را در .env بگذارید
```

## پاسخ هوشمند

کلید یکی از سرویس‌ها را در `.env` بگذارید: `ANTHROPIC_API_KEY`، `OPENAI_API_KEY`، `GEMINI_API_KEY`، `DEEPSEEK_API_KEY`، `OPENROUTER_API_KEY`، یا برای هر سرویس سازگار با OpenAI، `CUSTOM_AI_BASE_URL` و `CUSTOM_AI_API_KEY`. بعد از ری‌استارت سرویس، از پنل ← هوش مصنوعی ← تنظیمات ربات ← «مدل و هزینه» سرویس، مدل و در صورت تمایل سرویس پشتیبان را انتخاب و ربات را روشن کنید. جزئیات در بخش ۸ `docs/PLAN.md`. برای بارگذاری فایل تا ۱۰ مگابایت، `client_max_body_size 11m;` در تنظیم nginx لازم است.

## وارد کردن قانون‌ها

```bash
python -m app.importer rules.json
```

فرمت فایل در `app/importer.py` توضیح داده شده است.

## نصب روی سرور

```bash
sudo apt install -y python3-venv nginx certbot python3-certbot-nginx sqlite3 nodejs npm
sudo useradd -r -s /usr/sbin/nologin igbot
sudo git clone https://github.com/firouzayazi-source/instagram /opt/igbot
cd /opt/igbot
sudo python3 -m venv .venv && sudo .venv/bin/pip install -r requirements.txt
(cd web && sudo npm ci --no-audit --no-fund && sudo npm run build)
sudo cp .env.example .env && sudo chmod 600 .env && sudo nano .env
sudo mkdir -p data && sudo chown -R igbot:igbot /opt/igbot
sudo cp deploy/igbot.service /etc/systemd/system/
sudo cp deploy/nginx.conf /etc/nginx/sites-available/ig.stland.ir
sudo ln -s /etc/nginx/sites-available/ig.stland.ir /etc/nginx/sites-enabled/
sudo certbot --nginx -d ig.stland.ir
sudo systemctl daemon-reload && sudo systemctl enable --now igbot
sudo nginx -t && sudo systemctl reload nginx
curl -s https://ig.stland.ir/health
```

بکاپ شبانه: `0 4 * * * /opt/igbot/deploy/backup.sh` در crontab کاربر root.

به‌روزرسانی بعدی‌ها: `sudo /opt/igbot/deploy/deploy.sh` (کد تازه، ساخت پنل، تست، راه‌اندازی مجدد، وارسی سلامت).

## مسیرها
- `GET /health`: وضعیت سرویس و تعداد رویدادهای در صف
- `GET /webhook`: تأیید وبهوک متا
- `POST /webhook`: دریافت رویداد کامنت و پیام (با بررسی امضا)
- `/api/*`: API پنل (نشست لازم است)
- هر مسیر دیگر: پنل
