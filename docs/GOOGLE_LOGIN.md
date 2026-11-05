# ورود به پنل با گوگل

دکمه‌ی «ورود با گوگل» روی صفحه‌ی ورود؛ اگر مرورگر یا گوشی با یکی از ایمیل‌های مجاز به گوگل وصل باشد، پنل خودکار
وارد می‌شود. ورود با رمز همیشه می‌ماند. فقط ایمیل‌های فهرست `LOGIN_EMAILS` پذیرفته می‌شوند و درستی هر ورود را
خود گوگل (tokeninfo) تأیید می‌کند. هیچ راز تازه‌ای لازم نیست: شناسه‌ی دکمه (Client ID) عمومی است.

## ساخت شناسه (یک بار، رایگان)
1. [console.cloud.google.com](https://console.cloud.google.com) ← پروژه‌ی تازه (مثلاً `stockland-panel`).
   از داخل ایران ممکن است این سایت فقط با تغییر IP باز شود.
2. **APIs & Services ← OAuth consent screen**: نوع **External**، نام برنامه و ایمیل پشتیبانی؛ در **Test users**
   همان ایمیل خودتان را اضافه کنید (یا برنامه را Publish کنید).
3. **APIs & Services ← Credentials ← Create credentials ← OAuth client ID**: نوع **Web application**.
   در **Authorized JavaScript origins** فقط بنویسید: `https://ig.stland.ir` (Redirect URI لازم نیست).
4. **Client ID** را کپی کنید (شبیه `1234…apps.googleusercontent.com`). Client secret لازم نیست.

## ثبت در پنل
**تنظیمات ← حساب ← ورود با گوگل**: Client ID و ایمیل(های) مجاز (با ویرگول جدا) را ثبت کنید.
در ‎/opt/igbot/.env‎ با نام‌های `GOOGLE_CLIENT_ID` و `LOGIN_EMAILS` ذخیره و بی‌ری‌استارت فعال می‌شود.
