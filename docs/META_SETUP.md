# راه‌اندازی اپ متا (مرحله‌ی ۰)

هدف: اپی از نوع **Instagram API with Instagram Login** که پیج `stock_land.ir` روی آن نقش تستر دارد. برای پیج خودمان بازبینی متا لازم نیست.

## ۱. ساخت اپ
1. به [developers.facebook.com/apps](https://developers.facebook.com/apps) بروید و **Create App** را بزنید.
2. در Use case گزینه‌ی **Manage messaging and content on Instagram** را انتخاب کنید (یا نوع **Business** و بعد افزودن محصول Instagram).
3. نام اپ: مثلاً `StockLand Bot`. ایمیل تماس را پر کنید.
4. بعد از ساخت، از منوی چپ وارد **Instagram > API setup with Instagram login** شوید.

## ۲. مقدارهای لازم برای `.env`
| متغیر | از کجا |
|---|---|
| `IG_APP_SECRET` | App settings > Basic > **Instagram App Secret** (نه App Secret فیسبوک) |
| `IG_VERIFY_TOKEN` | خودتان یک رشته‌ی تصادفی بسازید، مثل `openssl rand -hex 16` |
| `IG_ACCESS_TOKEN` | مرحله‌ی ۳ |
| `IG_USER_ID` | شناسه‌ی عددی پیج؛ در پاسخ مرحله‌ی ۳ یا از `GET /me?fields=user_id` |

## ۳. افزودن پیج و گرفتن توکن
1. در بخش **Generate access tokens**، روی **Add account** بزنید و با حساب `stock_land.ir` وارد شوید.
2. در اینستاگرام (برنامه‌ی موبایل): **Settings > Website permissions > Apps and websites > Tester invites** و دعوت را بپذیرید.
3. دوباره در داشبورد روی **Generate token** بزنید و همه‌ی دسترسی‌ها را تأیید کنید:
   - `instagram_business_basic`
   - `instagram_business_manage_messages`
   - `instagram_business_manage_comments`
   - `instagram_business_content_publish`
4. توکن بلندمدت (۶۰ روزه) را کپی کنید و در `.env` بگذارید. ربات خودش هر ۳۰ روز تمدیدش می‌کند.

## ۴. وبهوک
1. در **Instagram > Webhooks**: Callback URL را `https://ig.stland.ir/webhook` و Verify token را همان `IG_VERIFY_TOKEN` بگذارید. سرویس باید از قبل روی سرور بالا باشد تا تأیید موفق شود.
2. در فیلدها **comments** و **messages** را Subscribe کنید.
3. در تنظیمات اپ، **App Mode** را در **Development** بگذارید؛ برای پیج تستر کافی است.

## ۵. تست
- در داشبورد وبهوک روی **Test** بزنید؛ در لاگ سرویس باید `queued` دیده شود:
  ```bash
  sudo journalctl -u instagram-bot -f
  ```
- یک کامنت آزمایشی از حساب دیگری روی پستی بگذارید که قانون دارد، و پاسخ را ببینید.

## نکته‌ها
- اگر ساخت اپ خطای منطقه داد، با VPN و همان حساب دوباره امتحان کنید.
- توکن و App Secret را هیچ‌جا جز `.env` روی سرور نگذارید.
