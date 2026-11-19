"""فهم عکس مشتری (برای ربات تلگرام)، با همان کلید هوش مصنوعی که صاحب پیج در پنل ثبت کرده.

بی کلید OpenAI یا Gemini این قابلیت خودبه‌خود خاموش است (available() خالی) و عکس مثل قبل برای همکار می‌رود.
خروجی فقط یک جمله‌ی کوتاه است که ربات مثل پیام نوشتاری مشتری جواب می‌دهد، یا RECEIPT / NONE.
مدل هرگز قیمت یا اطلاعات فروشگاه نمی‌دهد؛ جواب را موتور خود ربات از پایگاه دانش می‌سازد.
عکس فقط برای همین فرستاده و جایی ذخیره نمی‌شود.
"""
import base64

import httpx

from . import config

MAX_BYTES = 5 * 1024 * 1024
PROMPT = ("این عکس را مشتری یک فروشگاه موبایل (آیفون، اپل‌آیدی، لوازم جانبی) در چت فرستاده.{cap}\n"
          "اگر عکس گوشی، محصول یا اسکرین‌شات یک محصول است، در یک جمله‌ی کوتاه فارسی بنویس مشتری احتمالاً "
          "چه می‌پرسد، با نام مدل اگر روشن است؛ مثلاً «قیمت آیفون ۱۳ پرو» یا «این قاب برای آیفون ۱۵ موجوده؟».\n"
          "اگر رسید پرداخت، فیش واریز یا تراکنش بانکی است فقط بنویس RECEIPT.\n"
          "اگر نامربوط یا نامشخص است فقط بنویس NONE.\n"
          "هیچ قیمت، توضیح یا جمله‌ی دیگری ننویس.")


def available() -> str:
    if getattr(config, "OPENAI_API_KEY", ""):
        return "openai"
    if getattr(config, "GEMINI_API_KEY", ""):
        return "gemini"
    return ""


def _clean(t: str | None) -> str:
    t = (t or "").strip()
    t = t.splitlines()[0].strip().strip("«»\"'. ") if t else ""
    if t.upper().startswith("RECEIPT"):
        return "RECEIPT"
    if not t or t.upper().startswith("NONE"):
        return "NONE"
    return t[:150]


async def describe(data: bytes, caption: str = "", mime: str = "image/jpeg", transport=None) -> str | None:
    """None = قابلیت خاموش یا عکس نامعتبر؛ وگرنه جمله‌ی کوتاه، RECEIPT یا NONE."""
    if not data or len(data) > MAX_BYTES:
        return None
    which = available()
    if not which:
        return None
    prompt = PROMPT.format(cap=f"\nمتن همراه عکس: «{caption[:200]}»" if caption.strip() else "")
    b64 = base64.b64encode(data).decode()
    async with httpx.AsyncClient(timeout=45, transport=transport) as h:
        if which == "openai":
            r = await h.post("https://api.openai.com/v1/chat/completions",
                             headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                             json={"model": "gpt-4o-mini", "max_tokens": 80, "temperature": 0,
                                   "messages": [{"role": "user", "content": [
                                       {"type": "text", "text": prompt},
                                       {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "low"}}]}]})
            r.raise_for_status()
            return _clean(((r.json().get("choices") or [{}])[0].get("message") or {}).get("content"))
        r = await h.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
                         headers={"x-goog-api-key": config.GEMINI_API_KEY},
                         json={"contents": [{"parts": [{"text": prompt},
                                                       {"inline_data": {"mime_type": mime, "data": b64}}]}]})
        r.raise_for_status()
        parts = (((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}])
        return _clean(parts[0].get("text"))
