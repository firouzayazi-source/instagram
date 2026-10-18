# ربات جواب‌دهی اینستاگرام (با تأیید تلگرام)

هر کامنت یا دایرکت جدید پیج اینستاگرام، فوری با یه پیش‌نویس جواب فارسی (نوشته‌ی Claude با لحن خود شما) توی تلگرام‌تون میاد.
شما تأیید، ویرایش یا رد می‌کنید و جواب از طرف پیج ارسال می‌شه. **بدون تأیید شما هیچ چیزی ارسال نمی‌شه.**

```
اینستاگرام ──webhook──▶ سرور ──▶ Claude (پیش‌نویس فارسی)
                          │
                          ▼
                     تلگرام شما  ──[✅ ارسال | ✏️ ویرایش | 🔄 دوباره | 🙈 مخفی | ❌ رد]
                          │
                          ▼
              Instagram Graph API (ریپلای کامنت / جواب دایرکت)
```

فقط از **API رسمی متا** استفاده می‌کنه؛ بدون رمز عبور، بدون ربات مرورگر، بدون خطر بلاک شدن پیج.

## کارت تلگرام

```
💬 کامنت جدید از @ali
روی پست: «۵ اشتباه رایج در قیمت‌گذاری»
│ قیمت رو چطور تعیین کنم؟
🏷 دسته: سؤال
✍️ پیش‌نویس:
│ قیمت رو بر اساس ارزشی که می‌سازی بذار، نه ساعتی که کار می‌کنی.
ℹ️ سؤال پرتکرار؛ ارزش یه ریلز جدا رو داره.

[✅ ارسال] [✏️ ویرایش]
[🔄 دوباره بنویس] [🙈 مخفی کن] [❌ رد]
```

- **✏️ ویرایش:** متن خودتون رو بفرستید تا جایگزین بشه. اگه پیام رو با `!` شروع کنید، دستور بازنویسیه، مثلاً `!کوتاه‌تر و خودمونی‌تر`.
- اگه Claude اطلاعاتی نداشته باشه (مثلاً قیمت)، جاش `{{قیمت دوره}}` می‌ذاره و تا پرش نکنید دکمه‌ی ارسال کار نمی‌کنه.
- اسپم و توهین با پیشنهاد «بی‌جواب» میان و می‌تونید با 🙈 مخفی‌شون کنید.
- دستور `/token` توی تلگرام توکن اینستاگرام رو تمدید می‌کنه. خود ربات هم هر هفته خودکار تمدیدش می‌کنه.

## محدودیت‌های اینستاگرام (از طرف متا، نه این ربات)

- جواب دایرکت فقط تا **۲۴ ساعت** بعد از آخرین پیام طرف ممکنه. بعدش ربات هشدار می‌ده و باید از خود اپ جواب بدید.
- فقط کامنت‌های **پست‌های خودتون** رو می‌شه جواب داد. لایک، فالو و کامنت زیر پست دیگران با API ممکن نیست.
- پیج باید **Professional** باشه (Business یا Creator).

---

## راه‌اندازی

### ۱. صدای خودتون رو بنویسید
فایل [`voice.md`](voice.md) رو پر کنید: لحن، قیمت‌ها، لینک‌ها، سؤال‌های پرتکرار. این مهم‌ترین قدمه.

### ۲. ربات تلگرام
1. توی تلگرام به [@BotFather](https://t.me/BotFather) پیام بدید، `/newbot` رو بزنید و توکن رو بگیرید. می‌شه `TELEGRAM_BOT_TOKEN`.
2. یه رشته‌ی تصادفی بسازید برای `TELEGRAM_WEBHOOK_SECRET` (فقط حروف انگلیسی، عدد، `_` و `-`).
3. `TELEGRAM_ADMIN_CHAT_ID` رو فعلاً خالی بذارید (مرحله‌ی ۶).

### ۳. کلید Claude
از [console.anthropic.com](https://console.anthropic.com) یه API Key بسازید. می‌شه `ANTHROPIC_API_KEY`.

### ۴. اپ متا (اینستاگرام)
1. پیج اینستاگرام رو از تنظیمات به **Professional account** تغییر بدید.
2. توی [developers.facebook.com](https://developers.facebook.com) یه App بسازید. نوع کاربرد (use case) رو **«Manage messaging & content on Instagram»** انتخاب کنید.
3. توی بخش **Instagram → API setup with Instagram login**:
   - اکانت اینستاگرام‌تون رو اضافه کنید و **Generate token** رو بزنید. توکن می‌شه `IG_ACCESS_TOKEN` و شناسه‌ی اکانت (عدد ۱۷۸۴۱…) می‌شه `IG_USER_ID`.
   - **Instagram app secret** رو کپی کنید. می‌شه `IG_APP_SECRET`.
   - این دسترسی‌ها باید فعال باشن: `instagram_business_basic`، `instagram_business_manage_comments`، `instagram_business_manage_messages`.
4. Webhook رو بعد از بالا آوردن سرور تنظیم می‌کنیم (مرحله‌ی ۶).

> **دسترسی و App Review:** تا وقتی App در حالت Development باشه، متا رویدادها رو معمولاً فقط برای اکانت‌هایی می‌فرسته که روی App نقش دارن (برای تست عالیه).
> برای دریافت کامنت و دایرکت واقعی از همه‌ی کاربرها، احتمالاً باید App رو **Live** کنید و برای دو دسترسی comments و messages **Advanced Access** بگیرید. این کار App Review لازم داره: یه ویدیوی کوتاه از کارکرد ربات و یه صفحه‌ی Privacy Policy. ممکنه Business Verification هم بخواد.
> قوانین متا مدام عوض می‌شه، پس همون‌جا توی داشبورد App چک کنید.

### ۵. سرور
یه سرور با آدرس HTTPS لازمه. ساده‌ترین راه [Railway](https://railway.app) هست:
1. این ریپو رو به Railway وصل کنید (Deploy from GitHub). خودش Dockerfile رو می‌شناسه.
2. یه **Volume** با مسیر `/data` اضافه کنید. دیتابیس اونجا ذخیره می‌شه و با هر deploy پاک نمی‌شه.
3. توی Settings → Networking یه دامنه بسازید (Generate Domain). همین آدرس می‌شه `PUBLIC_URL`.
4. متغیرهای [`.env.example`](.env.example) رو توی بخش **Variables** پر کنید.

> کلیدها و توکن‌ها رو **هیچ‌وقت** توی ریپو، چت یا جای عمومی نذارید. فقط توی Variables سرور.

هر سرویس دیگه‌ای که Docker اجرا کنه هم کار می‌کنه (Render، Fly.io، VPS):
```bash
docker build -t ig-bot . && docker run -p 8000:8000 --env-file .env -v $(pwd)/data:/data ig-bot
```

### ۵ (روش دیگه). سرور شخصی (VPS)
پیش‌نیازها:
- سرور **خارج از ایران** باشه. سرورهای داخل ایران به API تلگرام و Claude دسترسی ندارن.
- Docker نصب باشه.
- یه دامنه یا ساب‌دامنه داشته باشید که رکورد A اون به IP سرور اشاره کنه. تلگرام و متا فقط به آدرس HTTPS معتبر وصل می‌شن.
- پورت‌های ۸۰ و ۴۴۳ باز باشن.

```bash
git clone https://github.com/firouzayazi-source/instagram.git && cd instagram
cp .env.example .env && nano .env      # DOMAIN و بقیه رو پر کنید؛ PUBLIC_URL=https://<DOMAIN>
docker compose up -d --build
docker compose logs -f bot             # دیدن لاگ‌ها
```
Caddy گواهی HTTPS رو خودکار از Let's Encrypt می‌گیره و تمدید می‌کنه. دیتابیس توی پوشه‌ی `data/` می‌مونه.
برای آپدیت: `git pull && docker compose up -d --build`.

### ۶. وصل کردن
1. **تلگرام:** وقتی سرور بالا اومد، webhook تلگرام خودکار ثبت می‌شه. به ربات‌تون `/start` بفرستید. عددی که جواب می‌ده رو بذارید توی `TELEGRAM_ADMIN_CHAT_ID` و سرور رو ری‌استارت کنید. از این به بعد ربات فقط به شما جواب می‌ده.
2. **اینستاگرام:** توی App متا، بخش **Webhooks** (زیر API setup with Instagram login):
   - Callback URL: `https://<PUBLIC_URL>/instagram/webhook`
   - Verify token: همون مقدار `IG_VERIFY_TOKEN`
   - فیلدهای **`comments`** و **`messages`** رو Subscribe کنید.
   - کنار اکانت اینستاگرام، اشتراک Webhook رو روشن کنید.
3. توی اپ اینستاگرام: **Settings → Messages and story replies → Message controls → Connected tools → Allow access to messages** رو روشن کنید.
4. تست: با یه اکانت دیگه زیر پست‌تون کامنت بذارید. باید چند ثانیه بعد توی تلگرام بیاد.

---

## توسعه

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest
cp .env.example .env   # پر کنید
uvicorn app.main:app --reload
```

| فایل | کار |
|---|---|
| `app/main.py` | مسیرهای وب: `/instagram/webhook`، `/telegram/webhook` |
| `app/bot.py` | روند کار: دریافت، پیش‌نویس، کارت تلگرام، دکمه‌ها، ارسال |
| `app/drafter.py` | پرامپت فارسی و فراخوانی Claude (خروجی JSON ساختاریافته) |
| `app/instagram.py` | تأیید امضای webhook، پارس رویدادها، فراخوانی Graph API |
| `app/telegram.py` | کلاینت Bot API تلگرام |
| `app/store.py` | SQLite: کامنت‌ها، دایرکت‌ها، تاریخچه‌ی گفتگو، توکن |

قواعد دسته‌بندی و نگارش جواب‌ها از [instagram-agent-skill](https://github.com/Jakeschincariol/instagram-agent-skill) (MIT) گرفته و برای فارسی بازنویسی شده.
