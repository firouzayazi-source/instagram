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
    if getattr(config, "ANTHROPIC_API_KEY", ""):     # ۷ آذر ۱۴۰۵: همان کلیدی که صاحب پیج دارد
        return "anthropic"
    return ""


ANTHROPIC_MODEL = "claude-haiku-5-5"


async def _ask(prompt: str, data: bytes, mime: str, max_tokens: int, transport=None) -> str:
    """یک پرسش متن+عکس از سرویس موجود؛ خروجی متن خام."""
    which = available()
    b64 = base64.b64encode(data).decode()
    async with httpx.AsyncClient(timeout=45, transport=transport) as h:
        if which == "openai":
            r = await h.post("https://api.openai.com/v1/chat/completions",
                             headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                             json={"model": "gpt-4o-mini", "max_tokens": max_tokens, "temperature": 0,
                                   "messages": [{"role": "user", "content": [
                                       {"type": "text", "text": prompt},
                                       {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"}}]}]})
            r.raise_for_status()
            return ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        if which == "gemini":
            r = await h.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
                             headers={"x-goog-api-key": config.GEMINI_API_KEY},
                             json={"contents": [{"parts": [{"text": prompt},
                                                           {"inline_data": {"mime_type": mime, "data": b64}}]}]})
            r.raise_for_status()
            parts = (((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}])
            return parts[0].get("text") or ""
        if which == "anthropic":
            r = await h.post("https://api.anthropic.com/v1/messages",
                             headers={"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
                             json={"model": ANTHROPIC_MODEL, "max_tokens": max_tokens,
                                   "messages": [{"role": "user", "content": [
                                       {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
                                       {"type": "text", "text": prompt}]}]})
            r.raise_for_status()
            return "".join(b.get("text", "") for b in r.json().get("content") or [] if b.get("type") == "text")
    return ""


PHONE_PROMPT = (
    "این اسکرین‌شات را مشتری از تنظیمات آیفون خودش فرستاده تا گوشی‌اش ارزیابی شود (مثلاً «درباره‌ی گوشی» یا "
    "«باتری ← سلامت باتری»). فقط چیزهایی را که روی تصویر خوانا نوشته شده بیرون بکش و یک شیء JSON بنویس با کلیدهای "
    "model (نام مدل انگلیسی مثل «iPhone 13 Pro» یا خالی)، storage_gb (عدد ظرفیت یا null)، battery (عدد درصد سلامت "
    "باتری یا null)، parts (فهرست پیام‌های «قطعه‌ی ناشناخته/Unknown Part» یا «سرویس» که روی تصویر هست، یا خالی). "
    "اگر چیزی روی تصویر نیست حدس نزن و null بگذار. فقط JSON، بی توضیح.")


async def phone_info(data: bytes, mime: str = "image/jpeg", transport=None) -> dict | None:
    """اسکرین‌شات تنظیمات آیفون ← {model, storage_gb, battery, parts}؛ None = خاموش یا ناخوانا."""
    if not data or len(data) > MAX_BYTES or not available():
        return None
    import json
    import re
    raw = await _ask(PHONE_PROMPT, data, mime, 200, transport)
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return None
    try:
        j = json.loads(m.group())
    except ValueError:
        return None
    out = {"model": str(j.get("model") or "").strip()[:40]}
    for k, lo, hi in (("storage_gb", 16, 2048), ("battery", 40, 100)):
        try:
            v = int(float(j.get(k)))
            out[k] = v if lo <= v <= hi else None
        except (TypeError, ValueError):
            out[k] = None
    out["parts"] = [str(x)[:60] for x in (j.get("parts") or []) if str(x).strip()][:4]
    return out if (out["model"] or out["battery"] or out["storage_gb"]) else None


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
    if which == "anthropic":
        return _clean(await _ask(prompt, data, mime, 80, transport))
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
