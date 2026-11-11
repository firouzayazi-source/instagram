"""نظارت، قیف فروش و خلاصه‌ی روزانه.

- هشدار: اگر خوانش کامنت، دایرکت یا آمار بیش از ۱۰ دقیقه خطا بدهد یا بی‌خبر بماند، یک پیام به تلگرام
  مدیر می‌رود (یک بار برای هر خرابی) و با درست شدنش یک پیام «برطرف شد».
- قیف: کامنت ← دایرکت خودکار ← ورود به ربات تلگرام از اینستاگرام ← سفارش.
- خلاصه‌ی روزانه: هر شب ساعت ۲۲:۳۰ تهران به تلگرام مدیر. فقط عدد؛ متن پیام مشتری‌ها در آن نیست.
"""
import asyncio
import json
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import comment_poll, config, db, tg_notify

TEHRAN = ZoneInfo("Asia/Tehran")
STATE_KEY = "monitor_state"
DIGEST_KEY = "digest_enabled"       # "0" یعنی خاموش؛ پیش‌فرض روشن
DIGEST_AT = (22, 30)
FAIL_AFTER = 600                    # ثانیه خطای پیوسته پیش از هشدار
STALE_AFTER = 900                   # ثانیه بی‌خبری از خوانشی که باید هر دقیقه اجرا شود
CHECKS = {comment_poll.STATUS_KEY: ("خوانش کامنت‌ها", True), comment_poll.DM_STATUS_KEY: ("خوانش دایرکت‌ها", True),
          "insights_stories": ("ذخیره‌ی آمار استوری", False)}
fa = lambda n: f"{int(n or 0):,}".translate(str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬"))  # noqa: E731


def check_health(c, bridge_active: bool, now: float | None = None) -> list[str]:
    """پیام‌هایی که باید به مدیر برود (خرابی تازه یا برطرف شدن). وضعیت در kv نگه داشته می‌شود."""
    now = now or time.time()
    state = json.loads(db.kv_get(c, STATE_KEY) or "{}")
    out = []
    for key, (label, frequent) in CHECKS.items():
        st = json.loads(db.kv_get(c, key) or "null")
        s = state.setdefault(key, {})
        if not bridge_active or st is None:
            s.clear()
            continue
        stale = frequent and now - st.get("at", now) > STALE_AFTER
        bad = stale or not st.get("ok")
        if bad:
            s.setdefault("since", now)
            if not s.get("alerted") and now - s["since"] >= (0 if stale else FAIL_AFTER):
                s["alerted"] = True
                why = "چند دقیقه است اجرا نشده" if stale else str(st.get("error", ""))[:200]
                out.append(f"⚠️ {label} کار نمی‌کند\n{why}\n\nپنل ← کانال‌ها ← اینستاگرام ← اتصال و وضعیت")
        else:
            if s.get("alerted"):
                out.append(f"✅ {label} دوباره کار می‌کند")
            s.clear()
    db.kv_set(c, STATE_KEY, json.dumps(state, ensure_ascii=False))
    return out


def tg_entries(since: float, until: float | None = None) -> int | None:
    """کاربران تازه‌ی ربات تلگرام که از لینک‌های اینستاگرام (start=insta…) آمده‌اند. None اگر در دسترس نیست."""
    p = Path(config.TG_DATA_DIR) / "users.db"
    if not p.exists():
        return None
    f = lambda t: datetime.fromtimestamp(t, TEHRAN).strftime("%Y-%m-%d %H:%M:%S")  # noqa: E731
    try:
        with sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=3) as t:
            return t.execute("SELECT COUNT(*) FROM users WHERE source LIKE 'insta%' AND joined_at>=? AND joined_at<?",
                             (f(since), f(until or time.time() + 60))).fetchone()[0]
    except sqlite3.Error:
        return None


def funnel(c, days: int = 7, now: float | None = None) -> dict:
    from . import insights
    insights.ensure(c)
    now = now or time.time()
    since = now - days * 86400
    q = lambda sql, *a: c.execute(sql, a).fetchone()[0]  # noqa: E731
    posts = []
    for r in c.execute(
            "SELECT c.media_id m, COUNT(*) n, SUM(c.answered) a,"
            " (SELECT COUNT(*) FROM replies r JOIN comments c2 ON c2.id=r.target_id"
            "   WHERE c2.media_id=c.media_id AND r.kind='private' AND r.ok=1 AND r.created_at>?) dm"
            " FROM comments c WHERE c.created_at>? AND c.media_id IS NOT NULL GROUP BY c.media_id ORDER BY n DESC LIMIT 10",
            (since, since)):
        ms = c.execute("SELECT caption, permalink, kind FROM media_stats WHERE media_id=?", (r["m"],)).fetchone()
        posts.append({"media_id": r["m"], "comments": r["n"], "answered": r["a"] or 0, "dms": r["dm"],
                      "caption": ms["caption"] if ms else "", "permalink": ms["permalink"] if ms else "",
                      "kind": ms["kind"] if ms else ""})
    return {
        "days": days,
        "comments": q("SELECT COUNT(*) FROM comments WHERE created_at>?", since),
        "auto_public": q("SELECT COUNT(*) FROM replies WHERE kind='public' AND ok=1 AND event_id NOT LIKE 'manual:%' AND created_at>?", since),
        "auto_dms": q("SELECT COUNT(*) FROM replies WHERE kind='private' AND ok=1 AND created_at>?", since),
        "dm_in": q("SELECT COUNT(*) FROM messages WHERE direction='in' AND created_at>?", since),
        "waiting": q("SELECT COUNT(*) FROM conversations WHERE answered=0 AND last_at>?", now - 86400),
        "tg_entries": tg_entries(since, now),
        "orders": q("SELECT COUNT(*) FROM orders WHERE created_at>?", since),
        "orders_ig": q("SELECT COUNT(*) FROM orders WHERE channel='ig' AND created_at>?", since),
        "send_errors": q("SELECT COUNT(*) FROM replies WHERE ok=0 AND created_at>?", since),
        "posts": posts,
    }


def digest_text(c, now: float | None = None) -> str:
    now = now or time.time()
    f = funnel(c, 1, now)
    day = datetime.fromtimestamp(now, TEHRAN)
    start = day.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    st = [json.loads(r[0]) for r in c.execute("SELECT metrics FROM story_stats WHERE posted_at>=?", (start,))]
    lines = ["📊 خلاصه‌ی امروز اینستاگرام",
             f"💬 کامنت تازه: {fa(f['comments'])} · جواب خودکار: {fa(f['auto_public'])} · دایرکت خودکار: {fa(f['auto_dms'])}",
             f"📩 دایرکت دریافتی: {fa(f['dm_in'])} · منتظر جواب: {fa(f['waiting'])}"]
    if f["tg_entries"] is not None:
        lines.append(f"🤖 ورود به ربات از اینستاگرام: {fa(f['tg_entries'])}")
    lines.append(f"🛒 سفارش تازه: {fa(f['orders'])}")
    if st:
        views = [m.get("views") or 0 for m in st]
        lines.append(f"📱 استوری امروز: {fa(len(st))} عدد · میانگین ویو {fa(sum(views) / len(views))}")
    if f["send_errors"]:
        lines.append(f"⚠️ ارسال ناموفق: {fa(f['send_errors'])} (پنل ← صندوق)")
    if f["waiting"]:
        lines.append("\nپیام‌های منتظر را در پنل ← صندوق ببینید.")
    return "\n".join(lines)


def digest_due(c, now: float | None = None) -> bool:
    now = now or time.time()
    if db.kv_get(c, DIGEST_KEY) == "0":
        return False
    t = datetime.fromtimestamp(now, TEHRAN)
    due = t.replace(hour=DIGEST_AT[0], minute=DIGEST_AT[1], second=0, microsecond=0)
    return due <= t < due + timedelta(hours=1) and db.kv_get(c, "digest_last") != t.strftime("%Y-%m-%d")


async def monitor_loop(ig, stop: asyncio.Event, interval: float = 300, grace: float = 180) -> None:
    try:       # بعد از ری‌استارت، اول خوانش‌ها فرصت اجرا داشته باشند (هشدار بی‌خبری الکی نیاید)
        await asyncio.wait_for(stop.wait(), timeout=grace)
        return
    except asyncio.TimeoutError:
        pass
    while not stop.is_set():
        try:
            with db.connect() as c:
                for msg in check_health(c, comment_poll.active(ig)):
                    tg_notify.send(msg)
                if digest_due(c):
                    if tg_notify.send(digest_text(c)):
                        db.kv_set(c, "digest_last", datetime.now(TEHRAN).strftime("%Y-%m-%d"))
        except Exception as e:  # noqa: BLE001
            print("monitor failed:", e)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
