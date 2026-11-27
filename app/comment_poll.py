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
OVERLAP = 600         # ثانیه: کامنت‌هایی که اینستاگرام دیرتر نشان می‌دهد هم خوانده شوند (تکراری‌ها با شناسه کنار می‌روند)
COUNT_RETRY = 5       # دور: تعداد کامنت بالا رفت ولی کامنت تازه هنوز دیده نشد؛ تا این‌قدر دوباره خوانده می‌شود
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
    if not me:
        # بی نام کاربری پیج، جواب‌های خود پیج از کامنت مشتری جدا نمی‌شوند (ربات به خودش جواب می‌داد): این دور رد
        raise RuntimeError("نام کاربری پیج خوانده نشد؛ دور بعد دوباره")
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
        force = mid in watched or (mid in latest and now - st.get("forced_at", 0) >= FORCE_EVERY) or st.get("resume") \
            or st.get("retry", 0) > 0
        if n <= st["count"] and not force:
            st["count"] = n
            continue
        if force:
            st["forced_at"] = now
        checked += 1
        # کف سخت: کامنت‌های پیش از روشن شدن خوانش (یا پیش از اولین دیدن این پست) هرگز جواب نمی‌گیرند
        floor = st.setdefault("floor", st["since"])
        low = max(st["since"] - OVERLAP, floor)
        rows, resume = await _comments(ig, mid, low, st.get("resume"))
        newest = max(st["since"], st.get("pending_newest", 0))
        fresh_seen = False
        for x in rows:
            t = _ts(x.get("timestamp", ""))
            frm = x.get("from") or {}
            if t <= low or not x.get("id") or not frm.get("id"):
                continue
            newest = max(newest, t)
            fresh_seen |= t > st["since"]
            if me and frm.get("username") == me:
                continue               # جواب‌های خود پیج
            payload = {"id": x["id"], "text": x.get("text", ""), "from": frm, "media": {"id": mid},
                       "parent_id": x.get("parent_id"), "_via": "poll"}
            queued += db.add_event(c, f"c:{x['id']}", "comment", payload)
        if resume:
            # موج بزرگ‌تر از ۴ صفحه: نقطه‌ی شروع جلو نمی‌رود و دور بعد از همان صفحه ادامه می‌یابد
            st.update(resume=resume, pending_newest=newest)
        else:
            st.pop("resume", None); st.pop("pending_newest", None)
            old_count = st.get("count", 0)
            if n > old_count and not fresh_seen and st.get("retry", 0) < COUNT_RETRY:
                st["retry"] = st.get("retry", 0) + 1         # تعداد زودتر از خود کامنت عوض شده: دور بعد دوباره
            else:
                st.update(count=n, since=newest, retry=0)
        c.commit()
    db.kv_set(c, STATE_KEY, json.dumps(state, ensure_ascii=False))
    return {"queued": queued, "checked": checked}


COMMENT_PAGE = 50
COMMENT_PAGES = 4


async def _comments(ig, mid: str, since: float, after: str | None = None) -> tuple[list[dict], str | None]:
    """کامنت‌های پست به‌همراه جواب‌هایشان (ریپلای زیر کامنت دیگر)، صفحه‌به‌صفحه تا به کامنت‌های قبل از since برسد.
    حداکثر ۴ صفحه‌ی ۵۰تایی در هر دور؛ اگر موج بزرگ‌تر بود، نشانگر صفحه‌ی بعد برمی‌گردد تا دور بعد از همان‌جا ادامه دهد.
    خروجی: (کامنت‌ها، نشانگر ادامه یا None)"""
    out = []
    for _ in range(COMMENT_PAGES):
        params = {"fields": "id,text,timestamp,from,parent_id,replies{id,text,timestamp,from}", "limit": COMMENT_PAGE}
        if after:
            params["after"] = after
        d = await ig._get(f"{mid}/comments", **params)
        page = d.get("data", []) or []
        for x in page:
            out.append(x)
            for r in ((x.get("replies") or {}).get("data") or []):
                out.append({**r, "parent_id": x.get("id")})
        after = ((d.get("paging") or {}).get("cursors") or {}).get("after")
        if len(page) < COMMENT_PAGE or not after or all(_ts(x.get("timestamp", "")) <= since for x in page):
            return out, None
    return out, after


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
    me = await _own_username(ig, state)
    if not me:
        raise RuntimeError("نام کاربری پیج خوانده نشد؛ دور بعد دوباره")    # پیش از علامت «دیده‌شده»، تا پیامی گم نشود
    convs = (await ig._get("me/conversations", platform="instagram", fields="id,updated_time", limit=DM_CONVS)).get("data", [])
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


DM_FAST = 15          # ثانیه: وقتی گفتگوی زنده هست (پیام رفت یا آمد در ۱۰ دقیقه‌ی اخیر)
DM_HOT_WINDOW = 600


def dm_interval(c, slow: float = INTERVAL) -> float:
    """خوانش دایرکت در گفتگوی زنده هر ۱۵ ثانیه، وگرنه هر دقیقه (۶ آذر ۱۴۰۵؛ پیش‌تر همیشه یک دقیقه بود و مشتری
    به‌طور میانگین نیم دقیقه فقط منتظر دیده شدن پیامش می‌ماند). خواندن، پیام روی پیج نمی‌فرستد؛ خطای سقف نرخ
    خواندن هم ترمز نمی‌کشد (safety.dangerous_read)."""
    last = c.execute("SELECT MAX(created_at) FROM messages").fetchone()[0] or 0
    return DM_FAST if time.time() - last < DM_HOT_WINDOW else slow


async def _poll_one(ig, key, fn) -> None:
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


async def _loop(ig, stop: asyncio.Event, key, fn, wait) -> None:
    while not stop.is_set():
        if active(ig):
            await _poll_one(ig, key, fn)
        try:
            with db.connect() as c:
                t = wait(c)
        except Exception:  # noqa: BLE001
            t = INTERVAL
        try:
            await asyncio.wait_for(stop.wait(), timeout=t)
        except asyncio.TimeoutError:
            pass


async def poll_loop(ig, stop: asyncio.Event, interval: float = INTERVAL) -> None:
    """کامنت‌ها و دایرکت‌ها دو حلقه‌ی جدا: خوانش کند کامنت‌ها (چند پست) دیگر دایرکت را معطل نمی‌کند."""
    await asyncio.gather(_loop(ig, stop, STATUS_KEY, poll_once, lambda c: interval),
                         _loop(ig, stop, DM_STATUS_KEY, poll_dms_once, lambda c: dm_interval(c, interval)))
