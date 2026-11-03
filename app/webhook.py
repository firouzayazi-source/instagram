"""فرستادن لید و سفارش به یک سیستم دیگر (مثلاً حساب‌لند یا CRM) با وبهوک.

تنظیم در پنل: آدرس https و یک رمز امضا. هر رویداد با POST و بدنه‌ی JSON می‌رود و سربرگ
X-Igbot-Signature برابر sha256=HMAC(رمز، بدنه) است تا گیرنده مطمئن شود از همین سرور آمده.
رمز هرگز به پنل برگردانده نمی‌شود. خطای گیرنده کار ربات را متوقف نمی‌کند؛ فقط در لاگ می‌ماند.
"""
import asyncio
import hashlib
import hmac
import json
import time

import httpx

from . import db

EVENTS = {"lead": "شماره‌ی تازه‌ی مشتری", "order": "سفارش تازه", "order_status": "تغییر وضعیت سفارش"}
_LOG_MAX = 30


def settings(c) -> dict:
    d = json.loads(db.kv_get(c, "webhook") or "{}")
    return {"url": d.get("url", ""), "secret": d.get("secret", ""), "events": d.get("events") or list(EVENTS)}


def public(c) -> dict:
    s = settings(c)
    return {"url": s["url"], "secret_set": bool(s["secret"]), "events": s["events"], "all_events": EVENTS,
            "log": json.loads(db.kv_get(c, "webhook_log") or "[]")}


def save(c, patch: dict) -> dict:
    s = settings(c)
    if "url" in patch:
        url = str(patch["url"] or "").strip()
        if url and not url.startswith("https://"):
            raise ValueError("آدرس وبهوک باید با https:// شروع شود")
        s["url"] = url[:500]
    if patch.get("secret"):
        s["secret"] = str(patch["secret"]).strip()[:200]
    if "events" in patch:
        s["events"] = [e for e in patch["events"] or [] if e in EVENTS]
    db.kv_set(c, "webhook", json.dumps(s, ensure_ascii=False))
    return public(c)


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _log(event: str, ok: bool, info: str) -> None:
    with db.connect() as c:
        log = json.loads(db.kv_get(c, "webhook_log") or "[]")
        log.insert(0, {"at": time.time(), "event": event, "ok": ok, "info": info[:200]})
        db.kv_set(c, "webhook_log", json.dumps(log[:_LOG_MAX], ensure_ascii=False))


async def deliver(url: str, secret: str, event: str, data: dict, transport=None) -> bool:
    body = json.dumps({"event": event, "at": int(time.time()), "data": data}, ensure_ascii=False).encode()
    headers = {"Content-Type": "application/json", "X-Igbot-Event": event}
    if secret:
        headers["X-Igbot-Signature"] = sign(secret, body)
    last = ""
    async with httpx.AsyncClient(timeout=15, transport=transport) as http:
        for attempt in range(3):
            try:
                r = await http.post(url, content=body, headers=headers)
                if r.status_code < 400:
                    _log(event, True, f"HTTP {r.status_code}")
                    return True
                last = f"HTTP {r.status_code}"
            except httpx.HTTPError as e:
                last = type(e).__name__
            await asyncio.sleep(2 ** attempt)
    _log(event, False, last)
    return False


def fire(c, event: str, data: dict) -> bool:
    """اگر وبهوک برای این رویداد تنظیم شده، بی‌آنکه منتظر بماند می‌فرستد."""
    s = settings(c)
    if not s["url"] or event not in s["events"]:
        return False
    try:
        asyncio.get_running_loop().create_task(deliver(s["url"], s["secret"], event, data))
    except RuntimeError:
        return False     # بیرون از حلقه‌ی async (مثلاً تست همگام)
    return True
