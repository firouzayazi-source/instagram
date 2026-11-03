"""گزارش‌ها: چه کسی جواب می‌دهد (ربات یا همکار)، پیام‌های بیرون از ساعت کاری، منتظرهای بیش از ۲۴ ساعت."""
import json
import time

from . import brain_engine


def report(c, days: int = 30) -> dict:
    now = time.time()
    since = now - days * 86400
    q = lambda sql, *a: c.execute(sql, a).fetchone()[0]  # noqa: E731
    bot = q("SELECT COUNT(*) FROM replies WHERE ok=1 AND event_id NOT LIKE 'manual:%' AND created_at>?", since)
    admin_panel = q("SELECT COUNT(*) FROM replies WHERE ok=1 AND event_id LIKE 'manual:%' AND created_at>?", since)
    # جواب همکار از خود اپ اینستاگرام (پیام بیرونی که ربات یا پنل نفرستاده)
    admin_app = q("SELECT COUNT(*) FROM messages WHERE direction='out' AND sender='admin' AND created_at>? "
                  "AND id NOT IN (SELECT ig_id FROM replies WHERE ig_id IS NOT NULL)", since)
    admin = admin_panel + admin_app
    total = bot + admin

    times = [r[0] for r in c.execute("SELECT created_at FROM messages WHERE direction='in' AND created_at>?", (since,))]
    times += [r[0] for r in c.execute("SELECT created_at FROM comments WHERE created_at>?", (since,))]
    flags = [brain_engine.open_at(t) for t in times]
    known = [f for f in flags if f is not None]
    off = sum(1 for f in known if f is False)

    day = 86400
    series = []
    for i in range(13, -1, -1):
        a, b = now - (i + 1) * day, now - i * day
        series.append({"bot": q("SELECT COUNT(*) FROM replies WHERE ok=1 AND event_id NOT LIKE 'manual:%' AND created_at>? AND created_at<=?", a, b),
                       "admin": q("SELECT COUNT(*) FROM replies WHERE ok=1 AND event_id LIKE 'manual:%' AND created_at>? AND created_at<=?", a, b)
                       + q("SELECT COUNT(*) FROM messages WHERE direction='out' AND sender='admin' AND created_at>? AND created_at<=? "
                           "AND id NOT IN (SELECT ig_id FROM replies WHERE ig_id IS NOT NULL)", a, b),
                       "incoming": q("SELECT COUNT(*) FROM messages WHERE direction='in' AND created_at>? AND created_at<=?", a, b)
                       + q("SELECT COUNT(*) FROM comments WHERE created_at>? AND created_at<=?", a, b)})

    tags = {}
    for (t,) in c.execute("SELECT tags FROM customers WHERE tags<>'[]'"):
        for x in json.loads(t):
            tags[x] = tags.get(x, 0) + 1
    return {
        "days": days,
        "replies": {"bot": bot, "admin": admin, "bot_pct": round(bot * 100 / total) if total else 0},
        "incoming": len(times),
        "out_of_hours": {"count": off, "pct": round(off * 100 / len(known)) if known else None},
        # پنجره‌ی ۲۴ ساعته‌ی اینستاگرام بسته شده؛ دیگر نمی‌شود جوابشان را داد
        "waiting_24h": q("SELECT COUNT(*) FROM conversations WHERE answered=0 AND last_at<?", now - day),
        "waiting_open": q("SELECT COUNT(*) FROM conversations WHERE answered=0 AND last_at>=?", now - day),
        "handoffs_open": q("SELECT COUNT(*) FROM handoffs WHERE status='open'"),
        "customers_new": q("SELECT COUNT(*) FROM customers WHERE first_seen>?", since),
        "customers_total": q("SELECT COUNT(*) FROM customers"),
        "tags": tags,
        "series": series,
        "hidden_comments": q("SELECT COUNT(*) FROM comments WHERE hidden=1 AND created_at>?", since),
    }


INTEREST = ("price", "purchase", "availability", "installment")


def lost(c, days: int = 14, idle_hours: float = 3) -> list[dict]:
    """فرصت‌های از‌دست‌رفته: کسانی که قیمت یا موجودی پرسیدند یا قصد خرید داشتند، سفارشی ثبت نکردند و
    دست‌کم idle_hours ساعت است پیامی نداده‌اند. پنجره‌ی باز یعنی هنوز می‌شود پیام پیگیری فرستاد."""
    from . import crm
    now = time.time()
    since, idle = now - days * 86400, now - idle_hours * 3600
    ph = ",".join("?" * len(INTEREST))
    rows = c.execute(
        f"SELECT * FROM customers WHERE last_seen>? AND last_seen<? AND ("
        f" tags LIKE '%\"قصد خرید\"%' OR user_id IN (SELECT user_id FROM ai_log WHERE intent IN ({ph}) AND created_at>?))"
        " AND NOT EXISTS (SELECT 1 FROM orders o WHERE o.user_id=customers.user_id AND o.created_at>?)"
        " ORDER BY last_seen DESC LIMIT 200", (since, idle, *INTEREST, since, since)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["tags"] = json.loads(d["tags"] or "[]")
        last_in = c.execute("SELECT MAX(created_at) FROM messages WHERE user_id=? AND direction='in'",
                            (d["user_id"],)).fetchone()[0] or 0
        d["window_left"] = max(0, int(last_in + crm.WINDOW - now))
        q = c.execute("SELECT input, intent FROM ai_log WHERE user_id=? AND intent IN "
                      f"({ph}) ORDER BY created_at DESC LIMIT 1", (d["user_id"], *INTEREST)).fetchone()
        d["asked"] = q["input"][:200] if q else ""
        out.append(d)
    return out
