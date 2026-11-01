"""API پنل. همه‌ی مسیرها جز /api/login نشست می‌خواهند."""
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from . import auth, config, db
from .importer import validate
from .rules import Incoming, find_rule

router = APIRouter(prefix="/api")
protected = APIRouter(prefix="/api", dependencies=[Depends(auth.require_session)])
_media_cache: dict = {"at": 0, "data": []}


def ig(request: Request):
    return request.app.state.ig


class Login(BaseModel):
    password: str


class Text(BaseModel):
    text: str


class RuleIn(BaseModel):
    name: str
    enabled: bool = True
    priority: int = 100
    channels: list[str]
    post_scope: str | list[str] = "all"
    triggers: list[dict] = [{"match": "any"}]
    actions: dict = {}
    advanced: dict = {}


@router.post("/login")
def login(body: Login, request: Request, response: Response):
    token = auth.check_password(request, body.password)
    response.set_cookie(auth.COOKIE, token, max_age=config.SESSION_TTL, httponly=True,
                        secure=config.COOKIE_SECURE, samesite="lax", path="/")
    return {"ok": True}


@protected.post("/logout")
def logout(response: Response, session: str = Depends(auth.require_session)):
    with db.connect() as c:
        db.delete_session(c, session)
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@protected.get("/me")
def me():
    return {"ok": True, "ig_user_id": config.IG_USER_ID}


@protected.get("/stats")
def stats():
    with db.connect() as c:
        return {**db.stats(c), "recent": db.recent_replies(c, 20)}


# ---------- کامنت‌ها ----------

@protected.get("/comments")
def comments(filter: str = "all", before: float | None = None):
    with db.connect() as c:
        return db.list_comments(c, filter, before=before)


@protected.post("/comments/{cid}/read")
def comment_read(cid: str):
    with db.connect() as c:
        db.mark_comment(c, cid, read=True)
    return {"ok": True}


@protected.post("/comments/{cid}/reply")
async def comment_reply(cid: str, body: Text, request: Request):
    """پاسخ عمومی دستی زیر کامنت."""
    return await _send(request, "public", cid, body.text)


@protected.post("/comments/{cid}/private")
async def comment_private(cid: str, body: Text, request: Request):
    """دایرکت خصوصی دستی به کامنت‌گذار."""
    return await _send(request, "private", cid, body.text)


# ---------- دایرکت ----------

@protected.get("/conversations")
def conversations(filter: str = "all"):
    with db.connect() as c:
        return db.list_conversations(c, filter)


@protected.get("/conversations/{user_id}/messages")
def conversation_messages(user_id: str):
    with db.connect() as c:
        db.mark_conversation(c, user_id, read=True)
        return db.list_messages(c, user_id)


@protected.post("/conversations/{user_id}/send")
async def conversation_send(user_id: str, body: Text, request: Request):
    return await _send(request, "dm", user_id, body.text)


async def _send(request: Request, kind: str, target: str, text: str):
    text = text.strip()
    if not text:
        raise HTTPException(400, "متن خالی است")
    client = ig(request)
    try:
        if kind == "public":
            ig_id = await client.reply_comment(target, text)
        elif kind == "private":
            ig_id = await client.private_reply(target, text)
        else:
            ig_id = await client.send_dm(target, text)
    except RuntimeError as e:
        with db.connect() as c:
            db.log_reply(c, f"manual:{target}", None, kind, target, text, ok=False, error=str(e))
        raise HTTPException(502, _friendly(str(e)))
    with db.connect() as c:
        db.log_reply(c, f"manual:{target}", None, kind, target, text, ig_id=ig_id, ok=True)
        if kind == "public":
            db.mark_comment(c, target, answered=True, read=True)
        elif kind == "private":
            db.mark_comment(c, target, answered=True, read=True)
            row = c.execute("SELECT user_id FROM comments WHERE id=?", (target,)).fetchone()
            if row:
                db.add_message(c, ig_id or f"out:{target}", row[0], "out", text)
        else:
            db.add_message(c, ig_id or f"out:{target}:{time.time()}", target, "out", text)
    return {"ok": True, "id": ig_id}


def _friendly(err: str) -> str:
    if "2534022" in err:
        return "پنجره‌ی ۲۴ ساعت اینستاگرام بسته شده؛ تا کاربر دوباره پیام ندهد نمی‌شود جواب داد."
    if "7 days" in err or "private reply" in err.lower():
        return "مهلت ۷ روزه‌ی دایرکت خصوصی به این کامنت گذشته است."
    return f"اینستاگرام خطا داد: {err[:200]}"


# ---------- قانون‌ها ----------

@protected.get("/rules")
def rules():
    with db.connect() as c:
        return db.all_rules(c)


@protected.post("/rules")
def rule_create(body: RuleIn):
    return _save_rule(body.model_dump())


@protected.put("/rules/{rule_id}")
def rule_update(rule_id: int, body: RuleIn):
    return _save_rule({**body.model_dump(), "id": rule_id})


def _save_rule(rule: dict):
    errs = validate(rule)
    if errs:
        raise HTTPException(422, "؛ ".join(errs))
    with db.connect() as c:
        rid = db.upsert_rule(c, rule)
    return {"ok": True, "id": rid}


@protected.delete("/rules/{rule_id}")
def rule_delete(rule_id: int):
    with db.connect() as c:
        db.delete_rule(c, rule_id)
    return {"ok": True}


@protected.post("/rules/{rule_id}/enable")
def rule_enable(rule_id: int, body: dict):
    with db.connect() as c:
        db.set_rule_enabled(c, rule_id, bool(body.get("enabled")))
    return {"ok": True}


class RuleTest(BaseModel):
    channel: str = "comment"
    text: str
    media_id: str | None = None


@protected.post("/rules/test")
def rule_test(body: RuleTest):
    """کدام قانون ذخیره‌شده به این متن می‌خورد؟ (بدون در نظر گرفتن سابقه‌ی کاربر)"""
    with db.connect() as c:
        rule = find_rule(db.load_rules(c), Incoming(body.channel, "test", body.text, body.media_id), lambda *_: None)
    return {"rule": {"id": rule["id"], "name": rule["name"]} if rule else None}


@protected.get("/saved-replies")
def saved_replies():
    """متن‌های استفاده‌شده در قانون‌ها، برای «انتخاب از پیام‌های قبلی»."""
    seen: list[str] = []
    with db.connect() as c:
        for r in db.all_rules(c):
            for k in ("public_replies", "private_replies", "dm_replies"):
                for t in r["actions"].get(k, []):
                    if t not in seen:
                        seen.append(t)
    return seen


@protected.get("/media")
async def media(request: Request):
    if time.time() - _media_cache["at"] > 300:
        try:
            _media_cache["data"] = await ig(request).media()
            _media_cache["at"] = time.time()
        except RuntimeError as e:
            if not _media_cache["data"]:
                raise HTTPException(502, _friendly(str(e)))
    return _media_cache["data"]


# ---------- تنظیمات و پوش ----------

@protected.get("/settings")
def settings_get():
    with db.connect() as c:
        return {"push_mode": db.kv_get(c, "push_mode") or "unanswered",
                "push_enabled": bool(config.VAPID_PUBLIC_KEY), "vapid_public_key": config.VAPID_PUBLIC_KEY}


@protected.put("/settings")
def settings_put(body: dict):
    mode = body.get("push_mode")
    if mode not in ("unanswered", "all", "off"):
        raise HTTPException(422, "push_mode نامعتبر")
    with db.connect() as c:
        db.kv_set(c, "push_mode", mode)
    return {"ok": True}


@protected.post("/push/subscribe")
def push_subscribe(sub: dict):
    if not sub.get("endpoint") or not sub.get("keys", {}).get("p256dh"):
        raise HTTPException(422, "اشتراک نامعتبر")
    with db.connect() as c:
        db.add_push_sub(c, sub)
    return {"ok": True}


@protected.delete("/push/subscribe")
def push_unsubscribe(body: dict):
    with db.connect() as c:
        db.delete_push_sub(c, body.get("endpoint", ""))
    return {"ok": True}
