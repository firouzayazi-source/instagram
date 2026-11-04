"""ارتباط داخلی کانال‌ها با هسته‌ی مرکزی (مثلاً ربات تلگرام ← هوش مصنوعی مرکزی).

فقط روی همین سرور: کلید مشترک در data/internal.key (فقط کاربر igbot می‌خواندش) و درخواستی که از
nginx (یعنی از اینترنت) رسیده باشد رد می‌شود. کلید هیچ‌وقت در لاگ یا پاسخ نمی‌آید.
"""
import hmac
import time
import os
import secrets
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from . import ai, config, db, orders

router = APIRouter(prefix="/internal")


def key_path() -> Path:
    return Path(config.DB_PATH).parent / "internal.key"


def ensure_key() -> None:
    p = key_path()
    if p.exists() and p.read_text().strip():
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(secrets.token_urlsafe(32))


def _check(request: Request, key: str | None) -> None:
    # پشت nginx همه‌ی درخواست‌های بیرونی این سربرگ را دارند؛ کانال داخلی مستقیم به 127.0.0.1:8011 می‌آید
    if request.headers.get("x-forwarded-for"):
        raise HTTPException(404)
    try:
        real = key_path().read_text().strip()
    except OSError:
        raise HTTPException(503)
    if not key or not real or not hmac.compare_digest(key, real):
        raise HTTPException(403)


class ThinkIn(BaseModel):
    channel: str
    user_id: str
    username: str = ""
    text: str
    test: bool = False


@router.post("/think")
async def think(body: ThinkIn, request: Request, x_internal_key: str | None = Header(None)):
    """هوش مصنوعی مرکزی برای کانالی که موتور فهم خودش را اجرا کرده و نفهمیده (فعلاً تلگرام)."""
    _check(request, x_internal_key)
    if body.channel != "telegram" or not body.text.strip():
        raise HTTPException(422)
    with db.connect() as c:
        d = await ai.decide(c, channel="telegram", text=body.text.strip()[:2000], user_id=f"tg:{body.user_id}",
                            username=body.username or None, is_test=body.test, skip_brain=True)
        if d.log_id and d.action == "reply" and not body.test:
            ai.mark_log(c, d.log_id, "sent")
    return {"action": d.action, "reply": d.reply, "intent": d.intent, "handoff_reason": d.handoff_reason,
            "skip_reason": d.skip_reason}


class OrderIn(BaseModel):
    channel: str
    user_id: str
    username: str = ""
    text: str = ""
    image: bool = False        # مشتری عکس فرستاد (شاید رسید)
    product_id: str = ""       # دکمه‌ی «رزرو می‌کنم» زیر کارت کالا
    hint: str = ""             # مدلی که درباره‌اش حرف می‌زد


@router.post("/order")
def order(body: OrderIn, request: Request, x_internal_key: str | None = Header(None)):
    """گفتگوی سفارش برای کانال دیگر (فعلاً تلگرام)، تا سفارش‌های همه‌ی کانال‌ها یکجا در هسته باشند.
    خروجی: reply (متن برای مشتری یا null اگر پیام به سفارش ربطی نداشت)، order_id (سفارشی که همین الان
    ثبت شد یا رسیدش آمد) و receipt (این پیام رسید پرداخت بود)."""
    _check(request, x_internal_key)
    if body.channel != "telegram":
        raise HTTPException(422)
    ch, uid = "tg", body.user_id.strip()[:40]
    with db.connect() as c:
        s = ai.settings(c)
        if not s["order_enabled"]:
            return {"reply": None, "order_id": None, "receipt": False}
        last = c.execute("SELECT MAX(id) FROM orders").fetchone()[0] or 0
        user = body.username or None
        if body.product_id:
            reply = orders.start(c, uid, user, product_id=body.product_id, channel=ch)
        else:
            reply = orders.handle(c, uid, user, body.text[:2000], ["telegram"] if body.image else [], s,
                                  channel=ch, hint=body.hint[:60])
        new = c.execute("SELECT id FROM orders WHERE id>? AND channel=? AND user_id=?", (last, ch, uid)).fetchone()
        rec = c.execute("SELECT id FROM orders WHERE channel=? AND user_id=? AND status='receipt' AND updated_at>?",
                        (ch, uid, time.time() - 5)).fetchone() if body.image and reply else None
    return {"reply": reply, "order_id": (new or rec or [None])[0], "receipt": bool(rec)}
