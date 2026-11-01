"""پردازشگر صف: رویداد → قانون → ارسال → لاگ."""
import asyncio
import json
import random
import time

from . import config, db
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


async def handle_event(ig, row, c) -> str:
    """یک رویداد را پردازش می‌کند. خروجی: done | skipped"""
    payload = json.loads(row["payload"])
    inc = parse_event(row["kind"], payload)
    if inc is None or not inc.user_id or inc.user_id == config.IG_USER_ID:
        return "skipped"
    rules = db.load_rules(c)
    rule = find_rule(rules, inc, lambda rid, uid: db.last_hit(c, rid, uid))
    if rule is None:
        return "skipped"  # مرحله‌ی ۳: این‌جا پاسخ هوشمند می‌آید
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
    return "done"


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
        if not rows:
            await asyncio.sleep(1)
            continue
        for row in rows:
            with db.connect() as c:
                try:
                    status = await handle_event(ig, row, c)
                    db.finish_event(c, row["id"], status)
                except Exception as e:  # noqa: BLE001
                    db.finish_event(c, row["id"], "error", str(e))


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
