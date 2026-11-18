"""تبدیل پیام صوتی فارسی به متن، با همان کلید هوش مصنوعی که صاحب پیج در پنل ثبت کرده.

اول OpenAI (مدل مخصوص گفتار)، اگر نبود Gemini (فهم صوت). هیچ‌کدام نبود: None و ربات مثل قبل ویس را
برای همکار می‌فرستد. فایل فقط برای همین تبدیل فرستاده و جایی ذخیره نمی‌شود.
"""
import base64

import httpx

from . import config

MAX_BYTES = 8 * 1024 * 1024
PROMPT = "متن دقیق این پیام صوتی فارسی را بنویس. فقط خود متن، بی هیچ توضیح اضافه."


def available() -> str:
    if getattr(config, "OPENAI_API_KEY", ""):
        return "openai"
    if getattr(config, "GEMINI_API_KEY", ""):
        return "gemini"
    return ""


async def transcribe(data: bytes, filename: str = "voice.ogg", mime: str = "audio/ogg", transport=None) -> str | None:
    if not data or len(data) > MAX_BYTES:
        return None
    which = available()
    async with httpx.AsyncClient(timeout=60, transport=transport) as h:
        if which == "openai":
            r = await h.post("https://api.openai.com/v1/audio/transcriptions",
                             headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                             data={"model": "gpt-4o-mini-transcribe", "language": "fa"},
                             files={"file": (filename, data, mime)})
            r.raise_for_status()
            return (r.json().get("text") or "").strip() or None
        if which == "gemini":
            r = await h.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
                             headers={"x-goog-api-key": config.GEMINI_API_KEY},
                             json={"contents": [{"parts": [
                                 {"text": PROMPT},
                                 {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}}]}]})
            r.raise_for_status()
            parts = (((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}])
            return (parts[0].get("text") or "").strip() or None
    return None
