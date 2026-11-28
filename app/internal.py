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

from . import ai, config, db, learning, orders

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


# کانال‌های ربات (همان کد ربات): تلگرام و بله. کلید پرونده و سفارش: tg:… یا bale:…
BOT_CHANNELS = {"telegram": "tg", "bale": "bale"}


class ThinkIn(BaseModel):
    channel: str
    user_id: str
    username: str = ""
    text: str
    test: bool = False
    context: list[list[str]] = []     # چند پیام اخیر همین گفتگو در ربات: [["مشتری"|"ربات", متن], …]


@router.post("/think")
async def think(body: ThinkIn, request: Request, x_internal_key: str | None = Header(None)):
    """هوش مصنوعی مرکزی برای کانالی که موتور فهم خودش را اجرا کرده و نفهمیده (فعلاً تلگرام)."""
    _check(request, x_internal_key)
    if body.channel not in BOT_CHANNELS or not body.text.strip():
        raise HTTPException(422)
    lines = [f"{'مشتری' if (x[0] if x else '') == 'مشتری' else 'ربات'}: {str(x[1])[:300]}"
             for x in body.context[-6:] if isinstance(x, list) and len(x) == 2 and str(x[1]).strip()]
    note = ("گفتگوی اخیر همین مشتری در ربات (جواب‌های آماده‌ی خود ربات):\n" + "\n".join(lines)) if lines else ""
    with db.connect() as c:
        d = await ai.decide(c, channel="telegram", text=body.text.strip()[:2000], user_id=f"{BOT_CHANNELS[body.channel]}:{body.user_id}",
                            username=body.username or None, is_test=body.test, skip_brain=True, note=note)
        if d.log_id and d.action == "reply" and not body.test:
            ai.mark_log(c, d.log_id, "sent")
        ask = ai.settings(c)["ask_feedback"]
    return {"action": d.action, "reply": d.reply, "intent": d.intent, "handoff_reason": d.handoff_reason,
            "skip_reason": d.skip_reason, "log_id": d.log_id, "ask_feedback": bool(ask and d.action == "reply")}


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
    if body.channel not in BOT_CHANNELS:
        raise HTTPException(422)
    ch, uid = BOT_CHANNELS[body.channel], body.user_id.strip()[:40]
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


class FeedbackIn(BaseModel):
    channel: str
    user_id: str
    log_id: int
    vote: str            # up | down


@router.post("/feedback")
def feedback(body: FeedbackIn, request: Request, x_internal_key: str | None = Header(None)):
    """رأی مشتری به جواب هوش مصنوعی؛ جواب پسندیده به دانش آفلاین می‌رود. هر کس فقط به جواب خودش."""
    _check(request, x_internal_key)
    if body.channel not in BOT_CHANNELS:
        raise HTTPException(422)
    with db.connect() as c:
        return learning.vote(c, body.log_id, body.vote, ai.settings(c), owner=f"{BOT_CHANNELS[body.channel]}:{body.user_id}")


@router.post("/transcribe")
async def transcribe(request: Request, x_internal_key: str | None = Header(None), x_filename: str | None = Header(None)):
    """ویس مشتری ← متن (برای ربات تلگرام). بی کلید هوش مصنوعی: text خالی."""
    _check(request, x_internal_key)
    from . import voice
    data = await request.body()
    if len(data) > voice.MAX_BYTES:
        raise HTTPException(413)
    try:
        text = await voice.transcribe(data, x_filename or "voice.ogg")
    except Exception as e:  # noqa: BLE001
        return {"text": "", "error": str(e)[:200]}
    return {"text": text or "", "provider": voice.available()}


@router.post("/vision")
async def vision(request: Request, x_internal_key: str | None = Header(None), x_caption: str | None = Header(None),
                 x_mode: str | None = Header(None)):
    """عکس مشتری ← یک جمله‌ی کوتاه (برای ربات تلگرام). بی کلید هوش مصنوعی: provider خالی، یعنی خاموش.
    X-Mode: phone ← اسکرین‌شات تنظیمات آیفون برای کارشناسی معاوضه: {info: {model, storage_gb, battery, parts}}."""
    _check(request, x_internal_key)
    from urllib.parse import unquote
    from . import vision as vis
    if not vis.available():
        return {"text": "", "provider": ""}
    data = await request.body()
    if len(data) > vis.MAX_BYTES:
        raise HTTPException(413)
    if x_mode == "phone":
        try:
            return {"info": await vis.phone_info(data), "provider": vis.available()}
        except Exception as e:  # noqa: BLE001
            return {"info": None, "provider": vis.available(), "error": str(e)[:200]}
    try:
        text = await vis.describe(data, unquote(x_caption or ""))
    except Exception as e:  # noqa: BLE001
        return {"text": "", "provider": vis.available(), "error": str(e)[:200]}
    return {"text": text or "", "provider": vis.available()}


class TouchIn(BaseModel):
    channel: str = "tg"
    user_id: str
    username: str = ""
    name: str = ""
    text: str = ""


@router.post("/touch")
def touch(body: TouchIn, request: Request, x_internal_key: str | None = Header(None)):
    """پیام مشتری تلگرام ← پرونده‌ی مشتری در پنل (با شماره‌اش، تا با همان شخص در اینستاگرام یکی دیده شود)."""
    _check(request, x_internal_key)
    from . import crm
    uid = body.user_id.strip()[:40]
    if not uid.isdigit() or body.channel not in ("tg", "bale"):
        raise HTTPException(422)
    with db.connect() as c:
        key = crm.touch(c, body.channel, uid, body.username.strip()[:64] or None, "message", body.text[:2000])
        if body.name.strip():
            c.execute("UPDATE customers SET name=? WHERE id=? AND COALESCE(name,'')=''", (body.name.strip()[:100], key))
    return {"ok": True}

