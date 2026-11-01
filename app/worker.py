"""پردازشگر صف: رویداد → قانون → ارسال → لاگ."""
import asyncio
import json
import random
import time

from . import ai, config, db, knowledge, push
from .rules import Incoming, find_rule, pick

MAX_RETRIES = 3


def parse_event(kind: str, payload: dict) -> Incoming | None:
    if kind == "comment":
        return Incoming(
            channel="comment",
            user_id=str(payload.get("from", {}).get("id", "")),
            text=payload.get("text", ""),
            media_id=str(payload.get("media", {}).get("id", "")),
        )
    if kind == "message":
        msg = payload.get("message", {})
        if msg.get("is_echo") or not msg.get("text"):
            return None
        return Incoming(channel="dm", user_id=str(payload.get("sender", {}).get("id", "")), text=msg["text"])
    return None


async def store_incoming(ig, c, kind: str, payload: dict, inc: Incoming) -> None:
    """کامنت یا پیام را در صندوق ثبت می‌کند."""
    if kind == "comment":
        db.add_comment(c, payload["id"], inc.media_id, inc.user_id,
                       payload.get("from", {}).get("username"), inc.text, payload.get("parent_id"))
    else:
        ts = payload.get("timestamp")
        db.add_message(c, payload["message"]["mid"], inc.user_id, "in", inc.text, ts / 1000 if ts else None)
        if not db.conversation_username(c, inc.user_id):
            p = await ig.profile(inc.user_id)
            if p.get("username"):
                db.set_conversation_username(c, inc.user_id, p["username"])
            if "is_user_follow_business" in p:
                inc.is_follower = bool(p["is_user_follow_business"])


async def handle_event(ig, row, c) -> str:
    """یک رویداد را پردازش می‌کند. خروجی: done | skipped"""
    payload = json.loads(row["payload"])
    inc = parse_event(row["kind"], payload)
    if inc is None or not inc.user_id or inc.user_id == config.IG_USER_ID:
        return "skipped"
    await store_incoming(ig, c, row["kind"], payload, inc)
    if knowledge.is_blocked(c, inc.user_id):
        return "ignored"
    rules = db.load_rules(c)
    rule = find_rule(rules, inc, lambda rid, uid: db.last_hit(c, rid, uid))
    if rule is None:
        return await handle_ai(ig, row, c, payload, inc)
    adv = rule.get("advanced", {})
    if adv.get("require_follow"):
        if inc.is_follower is None:
            inc.is_follower = await ig.is_follower(inc.user_id)
        if not inc.is_follower:
            text = adv.get("follow_prompt") or "اول پیج رو فالو کن، بعد دوباره پیام بده 🙏"
            await _send(ig, c, row["id"], rule["id"], "public" if inc.channel == "comment" else "dm", payload, inc, text)
            return "done"
    n = db.bump_rule(c, rule["id"])
    acts = rule["actions"]
    sent = False
    if inc.channel == "comment":
        for kind in ("private", "public"):
            text = pick(acts.get(f"{kind}_replies", []), n - 1)
            if text:
                sent |= await _send(ig, c, row["id"], rule["id"], kind, payload, inc, text)
    else:
        text = pick(acts.get("dm_replies", []), n - 1)
        if text:
            sent |= await _send(ig, c, row["id"], rule["id"], "dm", payload, inc, text)
    if sent:
        db.record_hit(c, rule["id"], inc.user_id)
        fu = adv.get("followup")  # {"after_seconds": 3600, "text": "..."}
        if fu and fu.get("text") and fu.get("after_seconds"):
            db.add_followup(c, rule["id"], inc.user_id, fu["text"], float(fu["after_seconds"]))
    return "done"


async def handle_ai(ig, row, c, payload, inc: Incoming) -> str:
    """وقتی هیچ قانونی نخورد: پاسخ هوشمند. خروجی: done | ignored | skipped"""
    if inc.channel == "comment":
        username = payload.get("from", {}).get("username")
    else:
        username = db.conversation_username(c, inc.user_id)
    d = await ai.decide(c, channel=inc.channel, text=inc.text, user_id=inc.user_id, username=username, event_id=row["id"])
    if d.action == "ignore" or (d.action == "skip" and d.skip_reason == "emoji"):
        return "ignored"
    if d.action in ("skip", "error"):
        return "skipped"
    sent = False
    if inc.channel == "comment":
        if d.reply:
            sent |= await _send(ig, c, row["id"], None, "private", payload, inc, d.reply)
        if d.public_reply:
            sent |= await _send(ig, c, row["id"], None, "public", payload, inc, d.public_reply)
    elif d.reply:
        sent = await _send(ig, c, row["id"], None, "dm", payload, inc, d.reply)
    ai.mark_log(c, d.log_id, "sent" if sent else "failed")
    if d.action == "handoff":
        ai.create_handoff(c, d, channel=inc.channel, user_id=inc.user_id, username=username, text=inc.text,
                          comment_id=payload.get("id") if inc.channel == "comment" else None)
        title = "🔥 مشتری آماده‌ی خرید" if d.intent == "purchase" else (
            "⚠️ شکایت مشتری" if d.intent == "complaint" else "نیاز به پاسخ شما 🙋")
        body = f"{username or inc.user_id}: {d.handoff_reason or inc.text}"[:160]
        asyncio.create_task(push.notify_all(title, body, "/#/ai/handoffs"))
    return "done"


async def process_followups(ig, c, now: float | None = None) -> int:
    """پیگیری‌های سررسیده را به دایرکت می‌فرستد. فقط اگر پنجره‌ی ۲۴ ساعت باز باشد موفق می‌شود."""
    n = 0
    for f in db.due_followups(c, now):
        try:
            ig_id = await ig.send_dm(f["user_id"], f["text"])
            db.log_reply(c, f"fu:{f['id']}", f["rule_id"], "dm", f["user_id"], f["text"], ig_id=ig_id, ok=True)
            db.finish_followup(c, f["id"], "done")
            n += 1
        except Exception as e:  # noqa: BLE001
            db.log_reply(c, f"fu:{f['id']}", f["rule_id"], "dm", f["user_id"], f["text"], ok=False, error=str(e))
            db.finish_followup(c, f["id"], "error", str(e))
    return n


async def _send(ig, c, event_id, rule_id, kind, payload, inc, text) -> bool:
    await asyncio.sleep(random.uniform(config.SEND_DELAY_MIN, config.SEND_DELAY_MAX))
    target = payload.get("id", "") if kind in ("public", "private") else inc.user_id
    for attempt in range(MAX_RETRIES):
        try:
            if kind == "public":
                ig_id = await ig.reply_comment(target, text)
            elif kind == "private":
                ig_id = await ig.private_reply(target, text)
            else:
                ig_id = await ig.send_dm(target, text)
            db.log_reply(c, event_id, rule_id, kind, target, text, ig_id=ig_id, ok=True)
            if kind == "public":
                db.mark_comment(c, target, answered=True)
            else:
                if kind == "private":
                    db.mark_comment(c, target, answered=True)
                db.add_message(c, ig_id or f"out:{event_id}:{kind}", inc.user_id, "out", text)
            return True
        except Exception as e:  # noqa: BLE001
            err = str(e)
            # خطاهای پنجره‌ی زمانی (۲۴ ساعت / ۷ روز) با تکرار درست نمی‌شوند
            if "2534022" in err or attempt == MAX_RETRIES - 1:
                db.log_reply(c, event_id, rule_id, kind, target, text, ok=False, error=err)
                return False
            await asyncio.sleep(2 ** attempt)
    return False


async def run_forever(ig, stop: asyncio.Event) -> None:
    while not stop.is_set():
        with db.connect() as c:
            rows = db.pending_events(c)
            await process_followups(ig, c)
        if not rows:
            await asyncio.sleep(1)
            continue
        for row in rows:
            with db.connect() as c:
                try:
                    status = await handle_event(ig, row, c)
                    db.finish_event(c, row["id"], status)
                except Exception as e:  # noqa: BLE001
                    status = "error"
                    db.finish_event(c, row["id"], "error", str(e))
                mode = db.kv_get(c, "push_mode") or "unanswered"
            if status == "error" or mode == "all" or (mode == "unanswered" and status == "skipped"):
                asyncio.create_task(_notify(row, status))


async def _notify(row, status: str) -> None:
    payload = json.loads(row["payload"])
    inc = parse_event(row["kind"], payload)
    if inc is None:
        return
    who = payload.get("from", {}).get("username") or inc.user_id
    kind = "کامنت" if inc.channel == "comment" else "دایرکت"
    title = f"{kind} جدید" + (" (بی‌پاسخ)" if status != "done" else "")
    url = "/#/comments" if inc.channel == "comment" else f"/#/messages/{inc.user_id}"
    await push.notify_all(title, f"{who}: {inc.text[:80]}", url)


async def refresh_token_loop(ig, stop: asyncio.Event) -> None:
    """هر روز چک می‌کند؛ اگر کمتر از ۳۰ روز از انقضا مانده بود تمدید می‌کند."""
    while not stop.is_set():
        with db.connect() as c:
            exp = float(db.kv_get(c, "token_expires_at") or 0)
        if exp and exp - time.time() < 30 * 86400:
            try:
                token, ttl = await ig.refresh_token()
                ig.token = token
                with db.connect() as c:
                    db.kv_set(c, "access_token", token)
                    db.kv_set(c, "token_expires_at", str(time.time() + ttl))
            except Exception as e:  # noqa: BLE001
                print("token refresh failed:", e)
        await asyncio.sleep(86400)
