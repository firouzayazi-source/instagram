"""سرنخ‌ها و سنجش: کدام دستور (پست) مشتری به ربات آورد، پیگیری تماس، یادآور روزانه و گزارش هفتگی.

- لینک ربات پشتیبان در متن هر دستور هنگام ارسال نشانه‌ی همان دستور را می‌گیرد (start=insta_r<شناسه>)؛
  ربات تلگرام اولین منبع ورود هر کاربر را ثبت می‌کند، پس معلوم می‌شود هر دستور چند نفر را به ربات آورد.
  ‎{bot}‎ در متن هم به همین لینک تبدیل می‌شود.
- هر مشتری‌ای که شماره دارد یک «سرنخ» است با وضعیت: تازه (پیش‌فرض)، تماس گرفته شد، خرید کرد، بی‌نتیجه.
- یادآور هر روز ساعت ۱۱:۱۰ تهران (شروع ساعت کاری) و گزارش هفتگی شنبه‌ها ۱۰:۴۰ به تلگرام مدیر؛ فقط عدد و
  عنوان پست، بی‌نام و شماره‌ی مشتری.
"""
import json
import re
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config, crm, db

TEHRAN = ZoneInfo("Asia/Tehran")
STATUSES = {"new": "تازه", "called": "تماس گرفته شد", "bought": "خرید کرد", "lost": "بی‌نتیجه"}
REMIND_AT, REMIND_KEY = (11, 10), "lead_remind_enabled"     # "0" یعنی خاموش
WEEKLY_AT, WEEKLY_KEY = (10, 40), "weekly_report_enabled"   # شنبه؛ "0" یعنی خاموش
fa = lambda n: f"{int(n or 0):,}".translate(str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬"))  # noqa: E731


# ---------- لینک ربات با نشانه‌ی دستور ----------

def bot_username() -> str:
    try:
        return json.loads((Path(config.TG_DATA_DIR) / "status.json").read_text(encoding="utf-8")).get("username", "")
    except (OSError, ValueError):
        return ""


def track_links(text: str, rule_id, username: str | None = None) -> str:
    """لینک ربات پشتیبان (بی start یا با start=insta) ← start=insta_r<شناسه>؛ بخش مقصد (‎-3‎) حفظ می‌شود.
    لینک‌هایی با منبع دیگر دست نمی‌خورند."""
    u = username if username is not None else bot_username()
    if not text or not u or not rule_id:
        return text.replace("{bot}", "") if text else text
    tag = f"insta_r{int(rule_id)}"
    text = text.replace("{bot}", f"https://t.me/{u}?start={tag}")
    rx = re.compile(rf"(?:https?://)?t\.me/{re.escape(u)}(?:\?start=insta(-[A-Za-z0-9_]+)?)?(?![A-Za-z0-9_?=-])", re.I)
    return rx.sub(lambda m: f"https://t.me/{u}?start={tag}{m.group(1) or ''}", text)


def rule_entries(since: float = 0) -> dict[int, int] | None:
    """شناسه‌ی دستور ← تعداد کاربر تازه‌ی ربات که از لینک همان دستور آمد. None اگر داده‌ی ربات در دسترس نیست."""
    p = Path(config.TG_DATA_DIR) / "users.db"
    if not p.exists():
        return None
    start = datetime.fromtimestamp(since, TEHRAN).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=3) as t:
            rows = t.execute("SELECT source, COUNT(*) FROM users WHERE source LIKE 'insta_r%' AND joined_at>=? GROUP BY source",
                             (start,)).fetchall()
    except sqlite3.Error:
        return None
    out: dict[int, int] = {}
    for src, n in rows:
        m = re.fullmatch(r"insta_r(\d+)", src or "")
        if m:
            out[int(m.group(1))] = out.get(int(m.group(1)), 0) + n
    return out


# ---------- وضعیت سرنخ ----------

def set_status(c, key: str, status: str) -> dict:
    if status not in STATUSES:
        raise ValueError("وضعیت نامعتبر است")
    if not c.execute("UPDATE customers SET lead_status=?, lead_at=? WHERE id=? AND phone<>''",
                     (status, time.time(), key)).rowcount:
        raise LookupError("سرنخ پیدا نشد (مشتری شماره ندارد)")
    if status == "bought":
        crm.add_tag(c, key, "خرید کرده")
    return {"key": key, "lead_status": status}


def waiting(c) -> int:
    return c.execute("SELECT COUNT(*) FROM customers WHERE phone<>'' AND lead_status IN ('','new')").fetchone()[0]


def _due(c, now: float, at: tuple, key: str, last_key: str, weekday: int | None = None) -> bool:
    if db.kv_get(c, key) == "0":
        return False
    t = datetime.fromtimestamp(now, TEHRAN)
    if weekday is not None and t.weekday() != weekday:
        return False
    due = t.replace(hour=at[0], minute=at[1], second=0, microsecond=0)
    return due <= t < due + timedelta(hours=1) and db.kv_get(c, last_key) != t.strftime("%Y-%m-%d")


def remind_due(c, now: float | None = None) -> bool:
    return _due(c, now or time.time(), REMIND_AT, REMIND_KEY, "lead_remind_last")


def remind_text(c, now: float | None = None) -> str | None:
    now = now or time.time()
    n = waiting(c)
    if not n:
        return None
    fresh = c.execute("SELECT COUNT(*) FROM customers WHERE phone<>'' AND lead_status IN ('','new') AND first_seen>?",
                      (now - 86400,)).fetchone()[0]
    return (f"📞 {fa(n)} سرنخ منتظر تماس" + (f" ({fa(fresh)} تازه از دیروز)" if fresh else "") +
            "\nپنل ← پاسخ هوشمند ← خروجی شماره‌ها؛ بعد از تماس وضعیتش را بزنید.")


# ---------- گزارش هفتگی ----------

def weekly_due(c, now: float | None = None) -> bool:
    return _due(c, now or time.time(), WEEKLY_AT, WEEKLY_KEY, "weekly_last", weekday=5)    # شنبه


def _views(m: dict) -> int:
    return int(m.get("views") or m.get("plays") or m.get("reach") or 0)


def weekly(c, now: float | None = None) -> dict:
    from . import insights, monitor
    insights.ensure(c)
    now = now or time.time()
    since = now - 7 * 86400
    f = monitor.funnel(c, 7, now)
    posts = []
    for r in c.execute("SELECT * FROM media_stats WHERE posted_at>=? ORDER BY posted_at", (since,)):
        m = json.loads(r["metrics"] or "{}")
        posts.append({"caption": (r["caption"] or "").split("\n")[0][:60], "permalink": r["permalink"], "kind": r["kind"],
                      "views": _views(m), "saves": int(m.get("saved") or 0), "shares": int(m.get("shares") or 0)})
    posts.sort(key=lambda p: p["views"], reverse=True)
    stories = [json.loads(r[0]) for r in c.execute("SELECT metrics FROM story_stats WHERE posted_at>=?", (since,))]
    sv = [_views(m) for m in stories]
    q = lambda sql, *a: c.execute(sql, a).fetchone()[0]  # noqa: E731
    entries = rule_entries(since)
    names = {r["id"]: r["name"] for r in db.all_rules(c)}
    top_rules = sorted(((names.get(k, f"دستور {k}"), v) for k, v in (entries or {}).items()), key=lambda x: -x[1])[:3]
    return {
        "funnel": f, "posts": posts, "stories": len(stories), "story_avg": (sum(sv) / len(sv)) if sv else 0,
        "new_leads": q("SELECT COUNT(*) FROM customers WHERE phone<>'' AND first_seen>?", since),
        "called": q("SELECT COUNT(*) FROM customers WHERE lead_status='called' AND lead_at>?", since),
        "bought": q("SELECT COUNT(*) FROM customers WHERE lead_status='bought' AND lead_at>?", since),
        "waiting": waiting(c), "rule_entries": top_rules, "tracked": entries is not None,
    }


def weekly_text(c, now: float | None = None) -> str:
    w = weekly(c, now)
    f = w["funnel"]
    out = ["📈 گزارش هفته‌ی اینستاگرام (۷ روز گذشته)",
           f"💬 کامنت: {fa(f['comments'])} · دایرکت خودکار: {fa(f['auto_dms'])} · دایرکت دریافتی: {fa(f['dm_in'])}"]
    if f["tg_entries"] is not None:
        out.append(f"🤖 ورود به ربات از اینستاگرام: {fa(f['tg_entries'])}")
    out.append(f"📞 شماره‌ی تازه: {fa(w['new_leads'])} · تماس گرفته‌شده: {fa(w['called'])} · خرید: {fa(w['bought'])}")
    out.append(f"🛒 سفارش: {fa(f['orders'])}")
    if w["posts"]:
        b = w["posts"][0]
        out.append(f"\n🏆 بهترین پست: «{b['caption'] or 'بی‌کپشن'}» · {fa(b['views'])} بازدید")
        if len(w["posts"]) > 1:
            z = w["posts"][-1]
            out.append(f"🔻 ضعیف‌ترین: «{z['caption'] or 'بی‌کپشن'}» · {fa(z['views'])} بازدید")
    if w["stories"]:
        out.append(f"📱 استوری: {fa(w['stories'])} عدد · میانگین بازدید {fa(w['story_avg'])}")
    if w["rule_entries"]:
        out.append("\n🎯 دستورهایی که بیشترین مشتری را به ربات آوردند:")
        out += [f"• {n}: {fa(v)} نفر" for n, v in w["rule_entries"]]
    tips = []
    if w["waiting"]:
        tips.append(f"{fa(w['waiting'])} سرنخ هنوز منتظر تماس است.")
    if w["tracked"] and not w["rule_entries"]:
        tips.append("هیچ دستوری این هفته کسی را به ربات نیاورد؛ لینک ربات پشتیبان (یا ‎{bot}‎) را در متن دستورها بگذارید.")
    if f["send_errors"]:
        tips.append(f"{fa(f['send_errors'])} ارسال ناموفق بود (پنل ← صندوق).")
    if tips:
        out.append("\n📝 برای این هفته:")
        out += [f"• {t}" for t in tips]
    return "\n".join(out)
