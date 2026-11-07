"""API پنل. همه‌ی مسیرها جز /api/login نشست می‌خواهند."""
import asyncio
import contextlib
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from . import ai, ai_admin, auth, channels, config, crm, db, orders, reports, webhook
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


@router.get("/login/google")
def login_google_config():
    """عمومی: فقط شناسه‌ی عمومی دکمه‌ی گوگل (ایمیل‌های مجاز برنمی‌گردد)."""
    g = auth.google_config()
    return {"enabled": g["enabled"], "client_id": g["client_id"] if g["enabled"] else ""}


@router.post("/login/google")
async def login_google(body: dict, request: Request, response: Response):
    token = await auth.google_login(request, str(body.get("credential") or ""))
    response.set_cookie(auth.COOKIE, token, max_age=config.SESSION_TTL, httponly=True,
                        secure=config.COOKIE_SECURE, samesite="lax", path="/")
    return {"ok": True}


@protected.post("/logout")
def logout(response: Response, session: str = Depends(auth.require_session)):
    with db.connect() as c:
        db.delete_session(c, session)
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@protected.post("/password")
def password_change(request: Request, body: dict, session: str = Depends(auth.require_session)):
    auth.change_password(request, session, str(body.get("current") or ""), str(body.get("new") or ""))
    return {"ok": True}


@protected.get("/me")
def me():
    return {"ok": True, "ig_user_id": config.IG_USER_ID}


@protected.get("/stats")
def stats():
    with db.connect() as c:
        st = db.stats(c)
        day = time.time() - 86400
        incoming = st["comments_24h"] + c.execute(
            "SELECT COUNT(*) FROM messages WHERE direction='in' AND created_at>?", (day,)).fetchone()[0]
        auto = c.execute(
            "SELECT COUNT(DISTINCT event_id) FROM replies WHERE ok=1 AND created_at>? "
            "AND event_id NOT LIKE 'manual:%' AND event_id NOT LIKE 'fu:%'", (day,)).fetchone()[0]
        st["orders_open"] = c.execute("SELECT COUNT(*) FROM orders WHERE status IN ('new','awaiting_payment','receipt')").fetchone()[0]
        st["orders_receipt"] = c.execute("SELECT COUNT(*) FROM orders WHERE status='receipt'").fetchone()[0]
        st["lost_open"] = sum(1 for x in reports.lost(c, 7, 3) if x["window_left"] > 0)
        return {**st, "incoming_24h": incoming, "auto_answered_24h": auto, "ai": ai.stats(c),
                "recent": db.recent_replies(c, 20)}


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


@protected.post("/comments/{cid}/hide")
async def comment_hide(cid: str, request: Request, body: dict | None = None):
    """مخفی کردن یا برگرداندن کامنت در خود اینستاگرام. body: {"hide": true|false}"""
    hide = bool((body or {}).get("hide", True))
    try:
        await ig(request).hide_comment(cid, hide)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"اینستاگرام قبول نکرد: {str(e)[:200]}")
    with db.connect() as c:
        c.execute("UPDATE comments SET hidden=?, hidden_reason=? WHERE id=?", (int(hide), "دستی" if hide else "", cid))
    return {"ok": True, "hidden": hide}


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
                db.add_message(c, ig_id or f"out:{target}", row[0], "out", text, sender="admin")
                db.set_human(c, row[0], ai.settings(c)["human_pause_minutes"])
        else:
            db.add_message(c, ig_id or f"out:{target}:{time.time()}", target, "out", text, sender="admin")
            db.set_human(c, target, ai.settings(c)["human_pause_minutes"])   # همکار وارد گفتگو شد
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


# ---------- کانال‌ها ----------

@protected.get("/channels")
def channels_list():
    with db.connect() as c:
        return channels.describe(c)


@protected.put("/channels/{ch}")
def channels_set(ch: str, body: dict):
    if ch not in channels.CHANNELS:
        raise HTTPException(404)
    try:
        channels.set_enabled(ch, bool(body.get("enabled")))
    except ValueError as e:
        raise HTTPException(422, str(e))
    with db.connect() as c:
        return next(x for x in channels.describe(c) if x["id"] == ch)


@protected.get("/conversations/{uid}/human")
def human_get(uid: str):
    with db.connect() as c:
        return {"until": db.human_until(c, uid)}


@protected.delete("/conversations/{uid}/human")
def human_clear(uid: str):
    """برگرداندن گفتگو به ربات پیش از تمام شدن زمان سکوت."""
    with db.connect() as c:
        db.clear_human(c, uid)
    return {"until": 0}


# ---------- اینستاگرام: سؤال‌های شروع گفتگو ----------

@protected.post("/instagram/ice-breakers")
async def ice_breakers_apply(request: Request, body: dict):
    """ذخیره و ثبت در اینستاگرام. فهرست خالی یعنی برداشتن."""
    with db.connect() as c:
        s = ai.save_settings(c, {"ice_breakers": body.get("questions") or []})
    if not (config.IG_ACCESS_TOKEN and config.IG_USER_ID):
        raise HTTPException(409, "ذخیره شد، ولی اینستاگرام هنوز وصل نیست؛ بعد از اتصال دوباره «ثبت در اینستاگرام» را بزنید")
    try:
        await ig(request).set_ice_breakers(s["ice_breakers"])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"اینستاگرام قبول نکرد: {str(e)[:200]}")
    return {"ok": True, "questions": s["ice_breakers"]}


# ---------- پرونده‌ی مشتری ----------

@protected.get("/customers")
def customers_list(q: str = "", tag: str = "", phone: str = "", window: str = "", days: int = 0, ordered: str = ""):
    with db.connect() as c:
        return {"items": crm.search(c, q, tag, phone=phone, window=window, days=max(0, min(365, days)), ordered=ordered),
                "tags": crm.all_tags(c)}


@protected.get("/customers/{key}")
def customer_get(key: str):
    with db.connect() as c:
        d = crm.get(c, key)
        if not d:
            raise HTTPException(404)
        d["blocked"] = bool(c.execute("SELECT 1 FROM blocked_users WHERE user_id=?", (d["user_id"],)).fetchone())
        return d


@protected.put("/customers/{key}")
def customer_put(key: str, body: dict):
    with db.connect() as c:
        try:
            return crm.update(c, key, body)
        except ValueError as e:
            raise HTTPException(422, str(e))


# ---------- گزارش‌ها ----------

@protected.get("/reports")
async def reports_get(request: Request, days: int = 30):
    days = min(365, max(1, days))
    with db.connect() as c:
        r = reports.report(c, days)
        acc = json.loads(db.kv_get(c, "ig_account") or "{}")
    if config.IG_ACCESS_TOKEN and time.time() - acc.get("at", 0) > 6 * 3600:
        try:
            a = await ig(request).account()
            acc = {"at": time.time(), "followers": a.get("followers_count"), "media": a.get("media_count")}
            with db.connect() as c:
                db.kv_set(c, "ig_account", json.dumps(acc))
        except Exception:  # noqa: BLE001
            pass
    r["followers"] = acc.get("followers")
    return r


# ---------- تحلیل محتوا (آمار استوری، ریلز و پست؛ فقط خواندن) ----------

@protected.get("/insights")
def insights_get(request: Request, days: int = 14):
    from . import insights
    with db.connect() as c:
        d = insights.summary(c, min(90, max(1, days)))
        d["status"] = {k: json.loads(db.kv_get(c, f"insights_{k}") or "null") for k in ("stories", "media")}
    src = insights.source(ig(request))
    d["source"] = src.name if src else ""
    return d


@protected.post("/insights/collect")
async def insights_collect(request: Request):
    """گرفتن همین الان: استوری‌ها همین‌جا؛ ریلز و پست‌ها (ده‌ها درخواست) در پس‌زمینه تا درخواست پنل قطع نشود."""
    from . import insights

    async def collect(what):
        try:
            with db.connect() as c:
                r = await insights.run(c, ig(request), what)
                db.kv_set(c, f"insights_{what}", json.dumps({"at": time.time(), "ok": True, **r}, ensure_ascii=False))
            return r
        except Exception as e:  # noqa: BLE001
            with db.connect() as c:
                db.kv_set(c, f"insights_{what}", json.dumps({"at": time.time(), "ok": False, "error": str(e)[:300]},
                                                          ensure_ascii=False))
            raise HTTPException(502, str(e)[:300])
    stories = await collect("stories")
    task = getattr(request.app.state, "insights_media", None)
    if task is None or task.done():
        async def media():
            with contextlib.suppress(HTTPException):     # خطا در وضعیت ذخیره و در پنل نشان داده می‌شود
                await collect("media")
        request.app.state.insights_media = asyncio.create_task(media())
    return {"stories": stories, "media": {"running": True}}


# ---------- پست و استوری: یادداشت و محصول ----------

@protected.get("/instagram/media-notes")
async def media_notes(request: Request):
    posts, stories, err = [], [], None
    if config.IG_ACCESS_TOKEN:
        try:
            posts = await media(request)
            stories = await ig(request).stories()
        except Exception as e:  # noqa: BLE001
            err = _friendly(str(e))
    with db.connect() as c:
        notes = {r["media_id"]: dict(r) for r in c.execute("SELECT * FROM media_notes")}
    for m in posts + stories:
        n = notes.get(m["id"], {})
        m["note"], m["product"] = n.get("note", ""), n.get("product", "")
    return {"posts": posts, "stories": stories, "error": err, "connected": bool(config.IG_ACCESS_TOKEN)}


@protected.put("/instagram/media-notes/{mid}")
def media_note_put(mid: str, body: dict):
    kind = body.get("kind") if body.get("kind") in ("post", "story") else "post"
    with db.connect() as c:
        db.set_media_note(c, mid, kind, str(body.get("note") or ""), str(body.get("product") or ""))
    return {"ok": True}


# ---------- فروش در دایرکت: سفارش‌ها ----------

@protected.get("/orders")
def orders_list(status: str = ""):
    with db.connect() as c:
        return {"items": orders.list_orders(c, status), "statuses": orders.STATUSES, "stats": orders.stats(c)}


@protected.get("/orders/{oid}")
def order_get(oid: int):
    with db.connect() as c:
        o = orders.get(c, oid)
        if not o:
            raise HTTPException(404, "سفارش پیدا نشد")
        return {**o, "statuses": orders.STATUSES}


@protected.put("/orders/{oid}")
def order_put(oid: int, body: dict):
    with db.connect() as c:
        try:
            return orders.update(c, oid, body)
        except ValueError as e:
            raise HTTPException(422, str(e))


# ---------- وبهوک لید و سفارش ----------

@protected.get("/webhook")
def webhook_get():
    with db.connect() as c:
        return webhook.public(c)


@protected.put("/webhook")
def webhook_put(body: dict):
    with db.connect() as c:
        try:
            return webhook.save(c, body)
        except ValueError as e:
            raise HTTPException(422, str(e))


@protected.post("/webhook/test")
async def webhook_test():
    with db.connect() as c:
        s = webhook.settings(c)
    if not s["url"]:
        raise HTTPException(422, "اول آدرس وبهوک را ذخیره کنید")
    ok = await webhook.deliver(s["url"], s["secret"], "test", {"message": "آزمایش وبهوک از پنل استوک لند"})
    return {"ok": ok}


# ---------- دستورها: کپی به کانال دیگر ----------

@protected.post("/rules/{rule_id}/copy")
def rule_copy(rule_id: int, body: dict):
    """کپی یک دستور برای کانال دیگر (مثلاً دستور دایرکت برای کامنت یا جواب استوری)."""
    with db.connect() as c:
        src = next((r for r in db.all_rules(c) if r["id"] == rule_id), None)
    if not src:
        raise HTTPException(404, "دستور پیدا نشد")
    chs = [x for x in body.get("channels") or [] if x in ("comment", "dm", "story_reply", "mention")] or src["channels"]
    rule = {k: src[k] for k in ("priority", "triggers", "actions", "advanced", "post_scope")}
    rule.update(name=f"{src['name']} (کپی)", enabled=False, channels=chs)
    if "comment" not in chs and "story_reply" not in chs:
        rule["post_scope"] = "all"
    return _save_rule(rule)


# ---------- مخاطبین: کار گروهی و فرصت‌های ازدست‌رفته ----------

@protected.post("/customers/bulk")
def customers_bulk(body: dict):
    with db.connect() as c:
        try:
            return crm.bulk(c, body.get("ids") or [], str(body.get("action") or ""), str(body.get("value") or ""))
        except ValueError as e:
            raise HTTPException(422, str(e))


@protected.get("/reports/lost")
def reports_lost(days: int = 14, idle_hours: float = 3):
    with db.connect() as c:
        return {"items": reports.lost(c, min(90, max(1, days)), min(24 * 30, max(0.5, idle_hours)))}


# ---------- تنظیم ربات با حرف ----------

@protected.post("/ai/admin-chat")
async def admin_chat(body: dict):
    with db.connect() as c:
        try:
            return await ai_admin.propose(c, str(body.get("text") or ""), body.get("history") or [])
        except ValueError as e:
            raise HTTPException(422, str(e))


@protected.post("/ai/admin-apply")
def admin_apply(body: dict):
    ops = [o for o in body.get("ops") or [] if isinstance(o, dict)]
    if not ops:
        raise HTTPException(422, "تغییری برای اعمال نیست")
    with db.connect() as c:
        return {"results": ai_admin.apply(c, ops)}
