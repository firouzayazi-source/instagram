"""خواندن دوره‌ای کامنت‌ها و دایرکت‌های تازه وقتی وبهوک اپ Meta خود پروژه نیست (پل Composio).

هر دقیقه یک درخواست: فهرست پست‌های اخیر با تعداد کامنت. فقط پستی که تعداد کامنتش بالا رفته (یا پستی که
دستور مخصوص دارد و در فهرست اخیر نیست) کامنت‌هایش خوانده می‌شود. کامنت تازه با همان شناسه‌ی وبهوک
(c:<id>) در صف می‌رود، پس اگر بعداً وبهوک هم بیاید تکراری پردازش نمی‌شود. کامنت‌های قبل از روشن شدن
خوانش هرگز جواب نمی‌گیرند (بار اول فقط نقطه‌ی شروع ثبت می‌شود). کامنتی که از این راه آمده فقط با دستورها
جواب می‌گیرد؛ هوش مصنوعی خودسر زیر پست‌ها جواب عمومی نمی‌دهد (worker، `_via: poll`).

دایرکت‌ها: هر دقیقه فهرست ۲۵ گفتگوی اخیر؛ فقط گفتگویی که تازه شده خوانده می‌شود. پیام مشتری و پیام خود پیج
(echo، تا ربات وقتی همکار یا ابزار دیگری جواب داده ساکت بماند) با شناسه‌ی m:<id> در صف می‌روند. پیش‌فرض فقط در
صندوق ثبت می‌شوند؛ جواب خودکار فقط وقتی صاحب پیج روشنش کند (`DM_REPLY_KEY`).
"""
import asyncio
import json
import time
from datetime import datetime

from . import channels, db

INTERVAL = 60
RECENT = 25          # پست‌های اخیری که بررسی می‌شوند
FORCE_RECENT = 3
FORCE_EVERY = 180
STATE_KEY = "comment_poll_state"
STATUS_KEY = "comment_poll"
DM_STATE_KEY = "dm_poll_state"
DM_STATUS_KEY = "dm_poll"
DM_REPLY_KEY = "dm_poll_reply"      # "1": دایرکت‌های خوانده‌شده جواب خودکار بگیرند؛ پیش‌فرض خاموش (فقط صندوق)
DM_CONVS = 25
POLL_TIMEOUT = 240


def _ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("+0000", "+00:00")).timestamp() if s else 0.0


def active(ig) -> bool:
    return bool(getattr(ig, "via_composio", lambda: False)()) and channels.enabled("instagram")


def watched_media(c) -> set[str]:
    """پست‌هایی که دستور کامنت مخصوص دارند (حتی اگر قدیمی باشند)."""
    out = set()
    for r in db.load_rules(c):
        if "comment" in r["channels"] and r["post_scope"] != "all":
            out.update(str(x) for x in r["post_scope"])
    return out


def has_all_posts_rule(c) -> bool:
    return any("comment" in r["channels"] and r["post_scope"] == "all" for r in db.load_rules(c))


async def _own_username(ig, state: dict) -> str:
    if not state.get("_me"):
        try:
            state["_me"] = (await ig._get("me", fields="username")).get("username", "")
        except Exception:  # noqa: BLE001
            return ""
    return state["_me"]


async def poll_once(ig, c, now: float | None = None) -> dict:
    """یک دور. خروجی: {"queued": n, "checked": n}"""
    now = now or time.time()
    state = json.loads(db.kv_get(c, STATE_KEY) or "{}")
    media = state.setdefault("media", {})
    started = state.setdefault("started", now)
    recent = (await ig._get(f"{ig.user_id}/media", fields="id,comments_count,timestamp", limit=RECENT)).get("data", [])
    counts = {str(m["id"]): int(m.get("comments_count") or 0) for m in recent}
    posted = {str(m["id"]): _ts(m.get("timestamp", "")) for m in recent}
    for mid in watched_media(c) - set(counts):
        try:
            counts[mid] = int((await ig._get(mid, fields="comments_count")).get("comments_count") or 0)
        except Exception:  # noqa: BLE001
            continue
    me = await _own_username(ig, state)
    # تعداد کامنت همیشه عوض نمی‌شود (کامنتی پاک و کامنت تازه گذاشته شود): پست‌هایی که دستور دارند بی‌توجه به
    # تعداد هم خوانده می‌شوند؛ پست‌های مشخص هر دور، و برای دستور «همه‌ی پست‌ها» سه پست آخر هر ۳ دقیقه.
    watched = watched_media(c)
    latest = [str(m["id"]) for m in recent[:FORCE_RECENT]] if has_all_posts_rule(c) else []
    queued = checked = 0
    for mid, n in counts.items():
        st = media.get(mid)
        if st is None:
            # پستی که بعد از روشن شدن خوانش منتشر شده: همه‌ی کامنت‌هایش تازه‌اند. پست قدیمی: فقط نقطه‌ی شروع.
            fresh = posted.get(mid, 0) > started
            st = media[mid] = {"count": 0 if fresh else n, "since": posted[mid] if fresh else now}
            if fresh:
                db.bind_next_post(c, mid, posted[mid])       # دستورهای «پست یا ریل بعدی»
        force = mid in watched or (mid in latest and now - st.get("forced_at", 0) >= FORCE_EVERY)
        if n <= st["count"] and not force:
            st["count"] = n
            continue
        if force:
            st["forced_at"] = now
        checked += 1
        rows = (await ig._get(f"{mid}/comments", fields="id,text,timestamp,from,parent_id", limit=50)).get("data", [])
        newest = st["since"]
        for x in rows:
            t = _ts(x.get("timestamp", ""))
            frm = x.get("from") or {}
            if t <= st["since"] or not x.get("id") or not frm.get("id"):
                continue
            newest = max(newest, t)
            if me and frm.get("username") == me:
                continue               # جواب‌های خود پیج
            payload = {"id": x["id"], "text": x.get("text", ""), "from": frm, "media": {"id": mid},
                       "parent_id": x.get("parent_id"), "_via": "poll"}
            queued += db.add_event(c, f"c:{x['id']}", "comment", payload)
        st.update(count=n, since=newest)
        c.commit()
    db.kv_set(c, STATE_KEY, json.dumps(state, ensure_ascii=False))
    return {"queued": queued, "checked": checked}


def dm_reply_enabled(c) -> bool:
    return db.kv_get(c, DM_REPLY_KEY) == "1"


def _dm_payload(x: dict, me: str) -> dict | None:
    """پیام API گفتگوها ← همان شکل رویداد وبهوک (messaging)؛ پیام خود پیج به شکل echo."""
    frm = x.get("from") or {}
    mid, ts = x.get("id"), _ts(x.get("created_time", ""))
    if not mid or not frm.get("id"):
        return None
    msg = {"mid": mid}
    if x.get("message"):
        msg["text"] = x["message"]
    story = x.get("story") or {}
    if (story.get("reply_to") or {}).get("id"):
        msg["reply_to"] = {"story": {"id": str(story["reply_to"]["id"])}}
    atts = []
    if story.get("mention"):
        atts.append({"type": "story_mention", "payload": {"url": (story["mention"] or {}).get("link", "")}})
    for a in (x.get("attachments") or {}).get("data", []):
        url = (a.get("image_data") or {}).get("url")
        if url:
            atts.append({"type": "image", "payload": {"url": url}})
    if atts:
        msg["attachments"] = atts
    if frm.get("username") == me:
        to = ((x.get("to") or {}).get("data") or [{}])[0]
        if not to.get("id"):
            return None
        msg["is_echo"] = True
        return {"sender": {"id": str(frm["id"])}, "recipient": {"id": str(to["id"])}, "timestamp": int(ts * 1000),
                "message": msg, "_via": "poll"}
    return {"sender": {"id": str(frm["id"]), "username": frm.get("username", "")}, "timestamp": int(ts * 1000),
            "message": msg, "_via": "poll"}


async def poll_dms_once(ig, c, now: float | None = None) -> dict:
    """دایرکت‌های تازه. بار اول فقط نقطه‌ی شروع ثبت می‌شود؛ پیام‌های قبل از آن هرگز وارد صف نمی‌شوند."""
    now = now or time.time()
    state = json.loads(db.kv_get(c, DM_STATE_KEY) or "{}")
    first = "since" not in state
    since = state.setdefault("since", now)
    seen = state.setdefault("conv", {})
    convs = (await ig._get("me/conversations", platform="instagram", fields="id,updated_time", limit=DM_CONVS)).get("data", [])
    me = await _own_username(ig, state)
    queued = checked = 0
    for cv in convs:
        cid, upd = cv.get("id"), cv.get("updated_time", "")
        if not cid or seen.get(cid) == upd:
            continue
        seen[cid] = upd
        if first or _ts(upd) <= since or not me:
            continue
        checked += 1
        rows = (await ig._get(f"{cid}/messages", limit=10,
                              fields="id,created_time,from,to,message,story,attachments{id,image_data{url}}")).get("data", [])
        for x in sorted(rows, key=lambda r: r.get("created_time", "")):
            if _ts(x.get("created_time", "")) <= since:
                continue
            p = _dm_payload(x, me)
            if p:
                queued += db.add_event(c, f"m:{p['message']['mid']}", "message", p)
        c.commit()
    if len(seen) > 400:                                    # فقط گفتگوهای اخیر نگه داشته شوند
        keep = {cv["id"] for cv in convs if cv.get("id")}
        state["conv"] = {k: v for k, v in seen.items() if k in keep}
    db.kv_set(c, DM_STATE_KEY, json.dumps(state, ensure_ascii=False))
    return {"queued": queued, "checked": checked}


async def poll_loop(ig, stop: asyncio.Event, interval: float = INTERVAL) -> None:
    while not stop.is_set():
        if active(ig):
            for key, fn in ((STATUS_KEY, poll_once), (DM_STATUS_KEY, poll_dms_once)):
                try:
                    with db.connect() as c:
                        r = await asyncio.wait_for(fn(ig, c), POLL_TIMEOUT)   # یک دور گیرکرده کل خوانش را نگه ندارد
                        db.kv_set(c, key, json.dumps({"at": time.time(), "ok": True, **r}, ensure_ascii=False))
                except Exception as e:  # noqa: BLE001
                    try:
                        with db.connect() as c:
                            db.kv_set(c, key, json.dumps({"at": time.time(), "ok": False, "error": str(e)[:300]},
                                                         ensure_ascii=False))
                    except Exception as e2:  # noqa: BLE001
                        print("poll status write failed:", e2)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
