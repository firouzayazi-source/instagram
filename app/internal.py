"""ارتباط داخلی کانال‌ها با هسته‌ی مرکزی (مثلاً ربات تلگرام ← هوش مصنوعی مرکزی).

فقط روی همین سرور: کلید مشترک در data/internal.key (فقط کاربر igbot می‌خواندش) و درخواستی که از
nginx (یعنی از اینترنت) رسیده باشد رد می‌شود. کلید هیچ‌وقت در لاگ یا پاسخ نمی‌آید.
"""
import hmac
import os
import secrets
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from . import ai, config, db

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
