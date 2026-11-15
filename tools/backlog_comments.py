"""جواب به کامنت‌های بی‌پاسخ پست‌های اخیر (صف عقب‌افتاده)، به خواست صاحب پیج (۲۴ آبان ۱۴۰۵).

کامنت‌ها مستقیم فرستاده نمی‌شوند: در همان صف برنامه گذاشته می‌شوند تا سقف ساعتی، ثبت در صندوق، جلوگیری از
تکرار و گزارش خطا همه رعایت شود. کامنت‌های تازه همیشه جلوترند و ۲۰ جای هر ساعت برایشان می‌ماند.

برای هر کامنت سطح اولی که پیج هنوز زیرش جواب نداده:
- اگر یکی از دستورهای پاسخ هوشمند به آن می‌خورد، همان دستور جواب می‌دهد. اگر بیش از ۷ روز از کامنت گذشته،
  اینستاگرام دایرکت به کامنت‌گذار را نمی‌پذیرد؛ پس به‌جای دایرکت زیر کامنت --old-text نوشته می‌شود.
- وگرنه بر اساس متن: سؤال قیمت و خرید ← --question-text، سلام ← --greet-text، بقیه ← یکی از متن‌های تشکر
  (به نوبت). کامنتی که فقط تگ دوست است یا متن ندارد جواب نمی‌گیرد.

    cd /opt/igbot && sudo -u igbot .venv/bin/python tools/backlog_comments.py              # فقط گزارش
    cd /opt/igbot && sudo -u igbot .venv/bin/python tools/backlog_comments.py --apply      # گذاشتن در صف
"""
import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

THANKS = ["ممنونم از همراهیت 🌸", "زنده باد مچکرم", "دمت گرم 👌", "سرت سلامت 😎", "مچکرم 👌", "زنده باد 🌸"]
QUESTION = "سلام 🌸 برای قیمت و شرایط به دایرکت پیج یا ربات پشتیبان تلگرام @Poshtibani_stland_bot پیام بده"
GREET = "سلام 🌸 جانم، در خدمتم؛ سؤالی داری به دایرکت پیام بده"
OLD = "برای دریافت، یه پیام به دایرکت پیج بده 📩"
DM_WINDOW = 7 * 86400
_Q = re.compile(r"قیمت|چند|چنده|موجود|خرید|بخرم|ارسال|قسط|اقساط|شرایط|آدرس|کجا|تماس|شماره|فروش|گارانتی|\?|؟")
_GREET = re.compile(r"^\s*(سلام|درود|salam|slm|salm|سلا)\W*$", re.I)
_MENTION_ONLY = re.compile(r"^(\s*@[\w.]+\s*)+[\W_]*$")


def ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("+0000", "+00:00")).timestamp() if s else 0.0


def classify(text: str) -> str:
    t = (text or "").strip()
    if not t or _MENTION_ONLY.match(t):
        return "skip"
    if _GREET.match(t):
        return "greet"
    if _Q.search(t):
        return "question"
    return "thanks"


async def collect(ig, days: int, me: str, only: str | None = None) -> list[dict]:
    """کامنت‌های سطح اول بی‌جواب پست‌های days روز اخیر: [{id, text, from, media, ts}]"""
    since = time.time() - days * 86400
    posts = [m for m in (await ig._get("me/media", fields="id,timestamp,comments_count", limit=100)).get("data", [])
             if ts(m.get("timestamp", "")) >= since and m.get("comments_count") and (not only or m["id"] == only)]
    out = []
    for m in posts:
        after = None
        while True:
            params = {"fields": "id,text,timestamp,from,replies{username}", "limit": 50}
            if after:
                params["after"] = after
            d = await ig._get(f"{m['id']}/comments", **params)
            for x in d.get("data", []) or []:
                frm = x.get("from") or {}
                if frm.get("username") == me or not frm.get("id"):
                    continue
                if any(r.get("username") == me for r in ((x.get("replies") or {}).get("data") or [])):
                    continue                                   # پیج قبلاً جواب داده
                out.append({"id": x["id"], "text": x.get("text", ""), "from": frm, "media": m["id"], "ts": ts(x.get("timestamp", ""))})
            after = ((d.get("paging") or {}).get("cursors") or {}).get("after")
            if not d.get("data") or not (d.get("paging") or {}).get("next"):
                break
    return out


def plan(c, comments: list[dict], texts: dict, now: float | None = None) -> list[dict]:
    """برای هر کامنت: kind (rule | question | greet | thanks | skip | queued) و payload رویداد."""
    from app import db
    from app.rules import Incoming, find_rule
    now = now or time.time()
    rules = db.load_rules(c)
    out, n = [], 0
    for x in comments:
        if c.execute("SELECT 1 FROM events WHERE id=?", (f"c:{x['id']}",)).fetchone():
            out.append({**x, "kind": "queued"})           # قبلاً در صف یا جواب‌داده
            continue
        old = now - x["ts"] > DM_WINDOW
        rule = find_rule(rules, Incoming("comment", str(x["from"]["id"]), x["text"], x["media"]), lambda *_: None)
        bl = {"old": old, "old_text": texts["old"]}
        if rule:
            kind = "rule"
        else:
            kind = classify(x["text"])
            if kind == "thanks":
                bl["reply"] = texts["thanks"][n % len(texts["thanks"])]
                n += 1
            elif kind in ("question", "greet"):
                bl["reply"] = texts[kind]
        payload = {"id": x["id"], "text": x["text"], "from": x["from"], "media": {"id": x["media"]}, "_via": "poll", "_backlog": bl}
        out.append({**x, "kind": kind, "rule": rule["name"] if rule else "", "old": old, "payload": payload})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30, help="پست‌های چند روز اخیر (پیش‌فرض ۳۰)")
    ap.add_argument("--post", help="فقط همین پست (شناسه)")
    ap.add_argument("--apply", action="store_true", help="گذاشتن در صف؛ بی آن فقط گزارش")
    ap.add_argument("--question-text", default=QUESTION)
    ap.add_argument("--greet-text", default=GREET)
    ap.add_argument("--old-text", default=OLD, help="به‌جای دایرکت، برای کامنت‌های قدیمی‌تر از ۷ روز")
    a = ap.parse_args(argv)
    from app import db, worker
    from app.instagram import Instagram
    ig = Instagram()
    if not ig.via_composio() and not ig.token:
        sys.exit("اتصال اینستاگرام (Composio یا توکن Meta) پیدا نشد")
    db.init()

    async def run():
        me = (await ig._get("me", fields="username")).get("username", "")
        return await collect(ig, a.days, me, a.post)
    comments = asyncio.run(run())
    texts = {"question": a.question_text, "greet": a.greet_text, "old": a.old_text, "thanks": THANKS}
    with db.connect() as c:
        items = plan(c, comments, texts)
        limit = worker.comment_limit(c)
    count = {}
    for it in items:
        k = it["kind"] + ("-old" if it.get("old") and it["kind"] == "rule" else "")
        count[k] = count.get(k, 0) + 1
    send = [it for it in items if it["kind"] not in ("skip", "queued")]
    fa = {"rule": "با دستور (دایرکت + جواب)", "rule-old": "با دستور، قدیمی‌تر از ۷ روز (فقط جواب زیر کامنت)",
          "question": "سؤال قیمت و خرید", "greet": "سلام", "thanks": "تشکر", "skip": "بی‌جواب (فقط تگ یا خالی)",
          "queued": "قبلاً در صف یا جواب‌داده"}
    print(f"کامنت بی‌جواب پست‌های {a.days} روز اخیر: {len(items)}")
    for k, v in sorted(count.items(), key=lambda kv: -kv[1]):
        print(f"  {fa.get(k, k)}: {v}")
    print("\nبه تفکیک پست (کدام دستور جواب می‌دهد):")
    per = {}
    for it in send:
        key = (it["media"], it.get("rule") or "—")
        per[key] = per.get(key, 0) + 1
    for (mid, rule), v in sorted(per.items(), key=lambda kv: -kv[1]):
        print(f"  پست {mid} · {('دستور «' + rule + '»') if rule != '—' else 'متن‌های عمومی بالا'}: {v}")
    rate = max(1, limit - worker.BACKLOG_RESERVE)
    print(f"\nمتن سؤال: {a.question_text}\nمتن سلام: {a.greet_text}\nمتن کامنت‌های قدیمی دستورها: {a.old_text}")
    print(f"\nبا سقف {limit} در ساعت (۲۰ تا برای کامنت‌های تازه)، حدود {len(send) / rate:.1f} ساعت طول می‌کشد.")
    if not a.apply:
        print("\nفقط گزارش بود؛ چیزی فرستاده نشد. برای گذاشتن در صف: --apply")
        return 0
    with db.connect() as c:
        added = sum(db.add_event(c, f"c:{it['id']}", "comment", it["payload"]) for it in send)
    print(f"\n✅ {added} کامنت در صف گذاشته شد. پیشرفت: پنل ← پاسخ هوشمند (جواب‌های ساعت گذشته و کامنت‌های در صف).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
