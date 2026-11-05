"""پردازشگر صف: رویداد → قانون → ارسال → لاگ."""
import asyncio
import json
import random
import time

from . import ai, channels, config, crm, db, knowledge, learning, memory, moderation, orders, push, tg_notify
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
    sender = str(payload.get("sender", {}).get("id", ""))
    if kind == "message":
        msg = payload.get("message", {})
        if msg.get("is_echo") or msg.get("is_deleted"):
            return None
        if any(a.get("type") == "story_mention" for a in msg.get("attachments") or []):
            return Incoming(channel="dm", user_id=sender, text=msg.get("text") or "", source="mention")
        images = [str((a.get("payload") or {}).get("url") or "") for a in msg.get("attachments") or []
                  if a.get("type") == "image" and str((a.get("payload") or {}).get("url") or "").startswith("https://")]
        if not msg.get("text"):
            if images:     # عکس بدون متن: شاید رسید پرداخت سفارش باشد
                return Incoming(channel="dm", user_id=sender, text="", images=images)
            return None     # ویس، استیکر و… بدون متن: جواب خودکار ندارد
        story = (msg.get("reply_to") or {}).get("story") or {}
        return Incoming(channel="dm", user_id=sender, text=msg["text"], source="story_reply" if story else "",
                        media_id=str(story.get("id") or "") or None, images=images)
    if kind == "postback":
        pb = payload.get("postback") or {}
        text = pb.get("title") or pb.get("payload") or ""
        return Incoming(channel="dm", user_id=sender, text=text, source="icebreaker",
                        payload=str(pb.get("payload") or "")) if text else None
    return None


def _message_id(kind: str, payload: dict) -> str:
    return (payload.get("postback") if kind == "postback" else payload.get("message", {})).get("mid", "")


def _shown_text(inc: Incoming) -> str:
    if inc.source == "mention":
        return "📣 شما را در استوری‌اش منشن کرد" + (f": {inc.text}" if inc.text else "")
    if inc.source == "story_reply":
        return f"↩️ (جواب به استوری) {inc.text}"
    if inc.images and not inc.text:
        return "🖼 عکس"
    return inc.text


FEEDBACK_QR = ["👍 مفید بود", "👎 نه"]     # زیر جواب‌های هوش مصنوعی؛ لمسش همین متن را برمی‌گرداند
STORY_NOTE = ("این پیام جواب مشتری به یکی از استوری‌های پیج است. متن یا تصویر استوری را نمی‌بینی؛ اگر به آن "
              "اشاره کرد و از متن پیام معلوم نیست درباره‌ی کدام محصول است، کوتاه بپرس.")


async def store_incoming(ig, c, kind: str, payload: dict, inc: Incoming) -> None:
    """کامنت یا پیام را در صندوق و پرونده‌ی مشتری ثبت می‌کند."""
    if kind == "comment":
        username = payload.get("from", {}).get("username")
        db.add_comment(c, payload["id"], inc.media_id, inc.user_id, username, inc.text, payload.get("parent_id"))
        crm.touch(c, "ig", inc.user_id, username, "comment", inc.text)
    else:
        ts = payload.get("timestamp")
        db.add_message(c, _message_id(kind, payload), inc.user_id, "in", _shown_text(inc), ts / 1000 if ts else None)
        if not db.conversation_username(c, inc.user_id):
            p = await ig.profile(inc.user_id)
            if p.get("username"):
                db.set_conversation_username(c, inc.user_id, p["username"])
            if "is_user_follow_business" in p:
                inc.is_follower = bool(p["is_user_follow_business"])
        crm.touch(c, "ig", inc.user_id, db.conversation_username(c, inc.user_id), "message", inc.text)


async def handle_echo(c, payload: dict) -> str:
    """پیامی که از طرف پیج رفته. اگر ربات نفرستاده، همکار از خود اپ اینستاگرام جواب داده:
    در صندوق ثبت می‌شود و ربات برای آن نفر ساکت می‌شود."""
    msg = payload.get("message", {})
    mid, user = msg.get("mid", ""), str(payload.get("recipient", {}).get("id", ""))
    if not mid or not user or c.execute("SELECT 1 FROM messages WHERE id=?", (mid,)).fetchone():
        return "skipped"           # پیام خود ربات (یا تکراری)
    db.add_message(c, mid, user, "out", msg.get("text") or "📎 پیوست", sender="admin")
    db.set_human(c, user, ai.settings(c)["human_pause_minutes"])
    return "admin"


async def handle_event(ig, row, c, extra_texts: list[str] | None = None, store_only: bool = False) -> str:
    """یک رویداد را پردازش می‌کند. خروجی: done | skipped | ignored | hidden | human | merged | admin
    extra_texts: پیام‌های قبلی همان نفر که منتظر ماندند و با این یکی یک جواب می‌گیرند.
    store_only: فقط ثبت در صندوق (پیامی که با پیام بعدی‌اش یکی شد)."""
    payload = json.loads(row["payload"])
    if row["kind"] == "message" and payload.get("message", {}).get("is_echo"):
        return await handle_echo(c, payload)
    inc = parse_event(row["kind"], payload)
    if inc is None or not inc.user_id or inc.user_id == config.IG_USER_ID:
        return "skipped"
    await store_incoming(ig, c, row["kind"], payload, inc)
    if store_only:
        return "merged"
    if extra_texts and inc.text:
        inc.text = "\n".join([*extra_texts, inc.text])
    if not channels.enabled("instagram"):
        return "ignored"   # کانال خاموش: پیام در صندوق ثبت می‌شود ولی پاسخ خودکار نمی‌رود
    if knowledge.is_blocked(c, inc.user_id):
        return "ignored"
    s = ai.settings(c)
    if inc.channel == "dm" and inc.text.strip() in FEEDBACK_QR:
        return await handle_feedback(ig, row, c, payload, inc, s)
    if inc.channel == "dm":
        # فروش در دایرکت: دکمه‌ی «سفارش»، گفتگوی سفارش در حال انجام، یا عکس رسید
        username = db.conversation_username(c, inc.user_id)
        human = bool(db.human_until(c, inc.user_id))
        hint = memory.recall(c, inc.user_id).get("product", "")    # «ثبت سفارش» برای همان مدلی که می‌پرسید
        memory.remember(c, inc.user_id, inc.text)
        reply = None
        if inc.payload.startswith("ORDER:") and s["order_enabled"] and not human:
            reply = orders.start(c, inc.user_id, username, product_id=inc.payload[6:])
        elif inc.images and not inc.text:
            reply = orders.receipt(c, inc.user_id, username, inc.images[0])   # رسید حتی وقتی همکار در گفتگوست
        elif not human:
            reply = orders.handle(c, inc.user_id, username, inc.text, inc.images, s, hint=hint)
        if reply:
            await _send(ig, c, row["id"], None, "dm", payload, inc, reply)
            return "done"
        if inc.images and not inc.text:
            return "skipped"    # عکس بی‌متن که رسید نبود: همکار ببیند
        if human:
            return "human"      # همکار در حال گفتگوست؛ ربات ساکت می‌ماند
    if inc.channel == "comment":
        reason = moderation.check(inc.text, s)
        if reason:
            await hide_comment(ig, c, payload["id"], reason)
            return "hidden"     # کامنت مخفی‌شده جواب نمی‌گیرد
    if inc.channel == "dm" and s["welcome_text"].strip() and db.is_first_message(c, inc.user_id):
        await _send(ig, c, row["id"], None, "dm", payload, inc, s["welcome_text"].strip())
    rules = db.load_rules(c)
    rule = find_rule(rules, inc, lambda rid, uid: db.last_hit(c, rid, uid))
    if rule is None:
        if inc.source == "mention":
            return await handle_mention(ig, row, c, payload, inc, s)
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
            sent |= await _send(ig, c, row["id"], rule["id"], "dm", payload, inc, text,
                                quick_replies=acts.get("quick_replies") or None)
    if adv.get("pause_ai_minutes") and inc.channel == "dm":
        db.set_human(c, inc.user_id, float(adv["pause_ai_minutes"]))   # «توقف هوش مصنوعی» بعد از این دستور
    if adv.get("handoff"):
        _rule_handoff(c, rule, inc, payload, s)
    if sent:
        db.record_hit(c, rule["id"], inc.user_id)
        fu = adv.get("followup")  # {"after_seconds": 3600, "text": "..."}
        if fu and fu.get("text") and fu.get("after_seconds"):
            db.add_followup(c, rule["id"], inc.user_id, fu["text"], float(fu["after_seconds"]))
    return "done"


def _rule_handoff(c, rule: dict, inc: Incoming, payload: dict, s: dict) -> None:
    """دستوری که «سپردن به همکار» دارد: در فهرست ارجاع‌ها، پوش و تلگرام."""
    username = payload.get("from", {}).get("username") if inc.channel == "comment" else db.conversation_username(c, inc.user_id)
    reason = f"دستور «{rule['name']}»"
    c.execute("INSERT INTO handoffs(created_at,channel,user_id,username,comment_id,text,reason) VALUES (?,?,?,?,?,?,?)",
              (time.time(), inc.channel, inc.user_id, username, payload.get("id") if inc.channel == "comment" else None,
               inc.text, reason))
    asyncio.create_task(push.notify_all("نیاز به پاسخ شما 🙋", f"{username or inc.user_id}: {inc.text}"[:160], "/#/ai/handoffs"))
    if s["notify_telegram"]:
        tg_notify.send(f"🙋 {reason}\n📸 اینستاگرام · {'@' + username if username else inc.user_id}\n\n💬 {inc.text[:500]}"
                       f"\n\n🔗 https://ig.stland.ir/#/customers/ig:{inc.user_id}")


async def handle_feedback(ig, row, c, payload, inc: Incoming, s: dict) -> str:
    """«👍 مفید بود» / «👎 نه» زیر جواب هوش مصنوعی: رأی ثبت می‌شود؛ جواب پسندیده به دانش آفلاین می‌رود؛
    ناپسند به همکار سپرده می‌شود."""
    r = c.execute("SELECT id FROM ai_log WHERE user_id=? AND channel='dm' AND action='reply' AND customer_vote='' "
                  "AND model<>'brain' AND created_at>? ORDER BY created_at DESC LIMIT 1",
                  (inc.user_id, time.time() - 6 * 3600)).fetchone()
    up = inc.text.strip() == FEEDBACK_QR[0]
    if r:
        learning.vote(c, r[0], learning.UP if up else learning.DOWN, s, owner=inc.user_id)
    if up:
        await _send(ig, c, row["id"], None, "dm", payload, inc, "ممنون از نظرت 🙏 اگه سؤال دیگه‌ای داری بپرس.")
        return "done"
    await _send(ig, c, row["id"], None, "dm", payload, inc, "ممنون که گفتی 🙏 سؤالت رو به همکارم دادم تا دقیق‌تر جواب بده.")
    username = db.conversation_username(c, inc.user_id)
    c.execute("INSERT INTO handoffs(created_at,channel,user_id,username,text,reason,ai_log_id) VALUES (?,?,?,?,?,?,?)",
              (time.time(), "dm", inc.user_id, username, inc.text, "مشتری جواب هوش مصنوعی را نپسندید", r[0] if r else None))
    db.set_human(c, inc.user_id, s["human_pause_minutes"])
    asyncio.create_task(push.notify_all("👎 جواب ربات پسندیده نشد", f"{username or inc.user_id}", "/#/ai/handoffs"))
    if s["notify_telegram"]:
        tg_notify.send(f"👎 مشتری جواب هوش مصنوعی را نپسندید\n📸 اینستاگرام · {'@' + username if username else inc.user_id}"
                       f"\n\n🔗 https://ig.stland.ir/#/customers/ig:{inc.user_id}")
    return "done"


async def hide_comment(ig, c, comment_id: str, reason: str) -> bool:
    try:
        await ig.hide_comment(comment_id, True)
    except Exception as e:  # noqa: BLE001
        print("hide comment failed:", e)
        return False
    c.execute("UPDATE comments SET hidden=1, hidden_reason=?, read=1 WHERE id=?", (reason, comment_id))
    return True


async def handle_mention(ig, row, c, payload, inc: Incoming, s: dict) -> str:
    """منشن در استوری بدون دستور مخصوص: تشکر خودکار (اگر روشن باشد)، به نوبت."""
    if not (s["mention_reply_enabled"] and s["mention_replies"]):
        return "ignored"
    n = int(db.kv_get(c, "mention_count") or 0)
    db.kv_set(c, "mention_count", str(n + 1))
    ok = await _send(ig, c, row["id"], None, "dm", payload, inc, pick(s["mention_replies"], n))
    return "done" if ok else "skipped"


async def handle_ai(ig, row, c, payload, inc: Incoming) -> str:
    """وقتی هیچ قانونی نخورد: پاسخ هوشمند. خروجی: done | ignored | skipped"""
    if inc.channel == "comment":
        username = payload.get("from", {}).get("username")
    else:
        username = db.conversation_username(c, inc.user_id)
    s = ai.settings(c)
    mnote = db.media_note(c, inc.media_id)
    notes = [STORY_NOTE] if inc.source == "story_reply" else []
    if mnote.get("note") or mnote.get("product"):
        what = "استوری" if inc.source == "story_reply" else "پستی"
        notes.append(f"این پیام درباره‌ی {what} است که صاحب پیج درباره‌اش نوشته: "
                     f"{mnote.get('product', '')} {mnote.get('note', '')}".strip())
    memo = memory.recall(c, inc.user_id) if inc.channel == "dm" else {}
    if memory.note(memo):
        notes.append(memory.note(memo))
    d = await ai.decide(c, channel=inc.channel, text=inc.text, user_id=inc.user_id, username=username, event_id=row["id"],
                        note="\n".join(notes), s=s, product_hint=mnote.get("product", "") or memo.get("product", ""),
                        budget=memo.get("budget", 0))
    crm.auto_tag(c, crm.cid("ig", inc.user_id), d.intent)
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
    elif d.cards and s["showcase_cards"]:
        intro = d.reply.split("\n")[0].strip() or "موجودی‌ها 👇"
        hint = next((ln for ln in d.reply.split("\n") if ln.startswith("💡")), "")
        if hint:
            intro = f"{intro}\n{hint}"     # اشاره به مدل‌های نزدیک، در همان پیام، نه پیام جدا
        sent = await _send(ig, c, row["id"], None, "dm", payload, inc, intro)
        if sent and not await _send_cards(ig, c, row["id"], inc, d.cards):
            await _send(ig, c, row["id"], None, "dm", payload, inc, d.reply)    # کارت نرفت: همان متن کامل
    elif d.reply:
        text = d.reply
        model = (c.execute("SELECT model FROM ai_log WHERE id=?", (d.log_id,)).fetchone() or [""])[0] if d.log_id else ""
        ask = s["ask_feedback"] and d.action == "reply" and model not in ("", "brain")   # فقط جواب هوش مصنوعی
        if s["order_enabled"] and d.intent == "price" and "💰" in text:      # نتیجه‌ی قیمت با کالای موجود
            text = f"{text}\n\n{orders.cta(len(inc.user_id) + int(time.time() // 3600))}"
        sent = await _send(ig, c, row["id"], None, "dm", payload, inc, text,
                           quick_replies=((FEEDBACK_QR if ask else []) +
                                          (s["dm_quick_replies"] if s["quick_replies_enabled"] else []))[:13] or None)
    ai.mark_log(c, d.log_id, "sent" if sent else "failed")
    if d.action == "handoff":
        ai.create_handoff(c, d, channel=inc.channel, user_id=inc.user_id, username=username, text=inc.text,
                          comment_id=payload.get("id") if inc.channel == "comment" else None)
        title = "🔥 مشتری آماده‌ی خرید" if d.intent == "purchase" else (
            "⚠️ شکایت مشتری" if d.intent == "complaint" else "نیاز به پاسخ شما 🙋")
        body = f"{username or inc.user_id}: {d.handoff_reason or inc.text}"[:160]
        asyncio.create_task(push.notify_all(title, body, "/#/ai/handoffs"))
        if s["notify_telegram"]:
            tg_notify.send(f"{title}\n📸 اینستاگرام · {'@' + username if username else inc.user_id}"
                           f" ({'کامنت' if inc.channel == 'comment' else 'دایرکت'})\n\n💬 {inc.text[:500]}"
                           + (f"\n\n📝 {d.handoff_reason}" if d.handoff_reason else "")
                           + f"\n\n🔗 https://ig.stland.ir/#/customers/ig:{inc.user_id}")
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


async def _send(ig, c, event_id, rule_id, kind, payload, inc, text, quick_replies=None) -> bool:
    target = payload.get("id", "") if kind in ("public", "private") else inc.user_id
    if kind == "dm" and ai.settings(c)["typing_indicator"]:
        for action in ("mark_seen", "typing_on"):      # بهترین تلاش؛ خطایش ارسال را متوقف نمی‌کند
            try:
                await ig.sender_action(target, action)
            except Exception:  # noqa: BLE001
                pass
    await asyncio.sleep(random.uniform(config.SEND_DELAY_MIN, config.SEND_DELAY_MAX))
    for attempt in range(MAX_RETRIES):
        try:
            if kind == "public":
                ig_id = await ig.reply_comment(target, text)
            elif kind == "private":
                ig_id = await ig.private_reply(target, text)
            elif quick_replies:
                ig_id = await ig.send_dm(target, text, quick_replies=quick_replies)
            else:
                ig_id = await ig.send_dm(target, text)
            db.log_reply(c, event_id, rule_id, kind, target, text, ig_id=ig_id, ok=True)
            if kind == "public":
                db.mark_comment(c, target, answered=True)
            else:
                if kind == "private":
                    db.mark_comment(c, target, answered=True)
                db.add_message(c, ig_id or f"out:{event_id}:{kind}", inc.user_id, "out", text, sender="bot")
            return True
        except Exception as e:  # noqa: BLE001
            err = str(e)
            # خطاهای پنجره‌ی زمانی (۲۴ ساعت / ۷ روز) با تکرار درست نمی‌شوند
            if "2534022" in err or attempt == MAX_RETRIES - 1:
                db.log_reply(c, event_id, rule_id, kind, target, text, ok=False, error=err)
                return False
            await asyncio.sleep(2 ** attempt)
    return False


async def _send_cards(ig, c, event_id, inc, cards: list[dict]) -> bool:
    text = "🛍 " + " | ".join(x["title"] for x in cards[:10])
    try:
        ig_id = await ig.send_cards(inc.user_id, cards)
    except Exception as e:  # noqa: BLE001
        db.log_reply(c, event_id, None, "dm", inc.user_id, text, ok=False, error=str(e))
        return False
    db.log_reply(c, event_id, None, "dm", inc.user_id, text, ig_id=ig_id, ok=True)
    db.add_message(c, ig_id or f"out:{event_id}:cards", inc.user_id, "out", text, sender="bot")
    return True


INTEREST = ("price", "purchase", "availability", "installment")


def followup_candidates(c, s: dict, now: float | None = None) -> list[dict]:
    """مشتری‌هایی که قیمت یا موجودی پرسیدند، جواب گرفتند و دست‌کم چند ساعت ساکت‌اند؛ هنوز پنجره‌ی ۲۴ ساعته باز است،
    سفارش نداده‌اند، پیگیری نگرفته‌اند، همکار با آن‌ها در گفتگو نیست و مسدود نیستند."""
    now = now or time.time()
    lo, hi = now - 23 * 3600, now - s["auto_followup_hours"] * 3600
    ph = ",".join("?" * len(INTEREST))
    rows = c.execute(
        f"""SELECT cv.user_id FROM conversations cv
            WHERE cv.answered=1
              AND (SELECT MAX(created_at) FROM messages m WHERE m.user_id=cv.user_id AND m.direction='in') BETWEEN ? AND ?
              AND EXISTS (SELECT 1 FROM ai_log a WHERE a.user_id=cv.user_id AND a.intent IN ({ph}) AND a.created_at>?)
              AND NOT EXISTS (SELECT 1 FROM orders o WHERE o.user_id=cv.user_id AND o.created_at>?)
              AND NOT EXISTS (SELECT 1 FROM auto_followups f WHERE f.user_id=cv.user_id)
              AND NOT EXISTS (SELECT 1 FROM blocked_users b WHERE b.user_id=cv.user_id)
              AND NOT EXISTS (SELECT 1 FROM order_flow w WHERE w.user_id=cv.user_id)
            LIMIT 20""", (lo, hi, *INTEREST, lo, now - 7 * 86400)).fetchall()
    return [{"user_id": r[0]} for r in rows if not db.human_until(c, r[0])]


async def auto_followups(ig, c, now: float | None = None) -> int:
    """پیگیری خودکار (اگر در پنل روشن باشد): هر نفر فقط یک بار، با مدلی که درباره‌اش پرسیده بود."""
    s = ai.settings(c)
    if not s["auto_followup_enabled"] or not channels.enabled("instagram"):
        return 0
    n = 0
    for x in followup_candidates(c, s, now):
        uid = x["user_id"]
        product = memory.recall(c, uid, max_age=24 * 3600).get("product") or "گوشی"
        text = s["auto_followup_text"].replace("{product}", product)
        ok, err, ig_id = True, None, None
        try:
            ig_id = await ig.send_dm(uid, text)
        except Exception as e:  # noqa: BLE001
            ok, err = False, str(e)
        c.execute("INSERT OR REPLACE INTO auto_followups(user_id,sent_at,ok) VALUES (?,?,?)", (uid, time.time(), int(ok)))
        db.log_reply(c, f"afu:{uid}", None, "dm", uid, text, ig_id=ig_id, ok=ok, error=err)
        if ok:
            db.add_message(c, ig_id or f"afu:{uid}", uid, "out", text, sender="bot")
            n += 1
    return n


def _sender(row) -> str:
    try:
        p = json.loads(row["payload"])
    except ValueError:
        return ""
    return str(p.get("sender", {}).get("id", "")) if row["kind"] in ("message", "postback") else ""


def plan_batches(rows, wait: float, now: float | None = None) -> list[tuple]:
    """با انتظار روشن، دایرکت‌های پشت‌سرهم هر نفر یک گروه می‌شوند و فقط وقتی آخرینشان «جا افتاد»
    (wait ثانیه از آن گذشت) با هم پردازش می‌شوند. خروجی: [(row، store_only، extra_texts)]."""
    now = now or time.time()
    if wait <= 0:
        return [(r, False, None) for r in rows]
    out, groups = [], {}
    for r in rows:
        s = _sender(r) if r["kind"] == "message" else ""
        if not s:
            out.append((r, False, None))
        else:
            groups.setdefault(s, []).append(r)
    for rs in groups.values():
        if now - rs[-1]["created_at"] < wait:
            continue                     # هنوز ممکن است پیام بعدی بیاید؛ در صف می‌ماند
        texts = []
        for r in rs[:-1]:
            out.append((r, True, None))
            t = (json.loads(r["payload"]).get("message") or {}).get("text")
            if t:
                texts.append(t)
        out.append((rs[-1], False, texts or None))
    return out


async def run_forever(ig, stop: asyncio.Event) -> None:
    next_afu = 0.0
    while not stop.is_set():
        with db.connect() as c:
            rows = db.pending_events(c, limit=50)
            await process_followups(ig, c)
            if time.time() >= next_afu:
                next_afu = time.time() + 600       # پیگیری خودکار: هر ۱۰ دقیقه یک بار بررسی
                try:
                    await auto_followups(ig, c)
                except Exception as e:  # noqa: BLE001
                    print("auto followup failed:", e)
            wait = ai.settings(c)["batch_wait_seconds"]
        plan = plan_batches(rows, wait)
        if not plan:
            await asyncio.sleep(1)
            continue
        for row, store_only, extra in plan:
            with db.connect() as c:
                try:
                    status = await handle_event(ig, row, c, extra_texts=extra, store_only=store_only)
                    db.finish_event(c, row["id"], status)
                except Exception as e:  # noqa: BLE001
                    status = "error"
                    db.finish_event(c, row["id"], "error", str(e))
                mode = db.kv_get(c, "push_mode") or "unanswered"
            if status == "error" or mode == "all" or (mode == "unanswered" and status == "skipped"):
                asyncio.create_task(_notify(row, status))


async def insights_loop(ig, stop: asyncio.Event) -> None:
    """تحلیل محتوا: هر ۹۰ دقیقه عکس فوری از استوری‌های زنده (آمارشان بعد از ۲۴ ساعت از دست می‌رود)،
    هر ۱۲ ساعت آمار پست‌ها و ریلزهای ۴۵ روز اخیر. اگر منبعی تنظیم نباشد، بی‌صدا منتظر می‌ماند."""
    from . import insights
    next_media = 0.0
    while not stop.is_set():
        for what in ("stories", "media"):
            if what == "media" and time.time() < next_media:
                continue
            if insights.source(ig) is None:
                break
            try:
                with db.connect() as c:
                    r = await insights.run(c, ig, what)
                    db.kv_set(c, f"insights_{what}", json.dumps({"at": time.time(), "ok": True, **r}, ensure_ascii=False))
                if what == "media":
                    next_media = time.time() + 12 * 3600
            except Exception as e:  # noqa: BLE001
                with db.connect() as c:
                    db.kv_set(c, f"insights_{what}", json.dumps({"at": time.time(), "ok": False, "error": str(e)[:300]},
                                                              ensure_ascii=False))
                if what == "media":
                    next_media = time.time() + 3600
        try:
            await asyncio.wait_for(stop.wait(), timeout=90 * 60)
        except asyncio.TimeoutError:
            pass


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
