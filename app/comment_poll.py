"""خواندن دوره‌ای کامنت‌های تازه وقتی وبهوک اپ Meta خود پروژه نیست (پل Composio).

هر دقیقه یک درخواست: فهرست پست‌های اخیر با تعداد کامنت. فقط پستی که تعداد کامنتش بالا رفته (یا پستی که
دستور مخصوص دارد و در فهرست اخیر نیست) کامنت‌هایش خوانده می‌شود. کامنت تازه با همان شناسه‌ی وبهوک
(c:<id>) در صف می‌رود، پس اگر بعداً وبهوک هم بیاید تکراری پردازش نمی‌شود. کامنت‌های قبل از روشن شدن
خوانش هرگز جواب نمی‌گیرند (بار اول فقط نقطه‌ی شروع ثبت می‌شود). کامنتی که از این راه آمده فقط با دستورها
جواب می‌گیرد؛ هوش مصنوعی خودسر زیر پست‌ها جواب عمومی نمی‌دهد (worker، `_via: poll`).
"""
import asyncio
import json
import time
from datetime import datetime

from . import channels, db

INTERVAL = 60
RECENT = 25          # پست‌های اخیری که بررسی می‌شوند
STATE_KEY = "comment_poll_state"
STATUS_KEY = "comment_poll"


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
    queued = checked = 0
    for mid, n in counts.items():
        st = media.get(mid)
        if st is None:
            # پستی که بعد از روشن شدن خوانش منتشر شده: همه‌ی کامنت‌هایش تازه‌اند. پست قدیمی: فقط نقطه‌ی شروع.
            fresh = posted.get(mid, 0) > started
            st = media[mid] = {"count": 0 if fresh else n, "since": posted[mid] if fresh else now}
        if n <= st["count"]:
            st["count"] = n
            continue
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
    db.kv_set(c, STATE_KEY, json.dumps(state, ensure_ascii=False))
    return {"queued": queued, "checked": checked}


async def poll_loop(ig, stop: asyncio.Event, interval: float = INTERVAL) -> None:
    while not stop.is_set():
        if active(ig):
            try:
                with db.connect() as c:
                    r = await poll_once(ig, c)
                    db.kv_set(c, STATUS_KEY, json.dumps({"at": time.time(), "ok": True, **r}, ensure_ascii=False))
            except Exception as e:  # noqa: BLE001
                with db.connect() as c:
                    db.kv_set(c, STATUS_KEY, json.dumps({"at": time.time(), "ok": False, "error": str(e)[:300]},
                                                        ensure_ascii=False))
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
