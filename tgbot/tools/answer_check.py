"""سنجش پاسخ‌گویی دستیار — همان مسیر واقعی ربات (assistant_reply)، بدون تلگرام.

    python3 tools/answer_check.py                   # تست ثابت: tests/phrases.tsv
    python3 tools/answer_check.py scan FILE         # پیام‌های واقعی مشتری (unmatched.json یا یک خط در هر پیام)
    گزینه‌ها:  --faq faq.json   --catalog catalog.json   (نسخه‌ی سرور؛ بی‌آن پیش‌فرض‌های کد و یک لیست کالای کوچک)

هر پیام یک «مسیر» می‌گیرد:
    i_xxx      نیتی که اجرا شد
    catalog    لیست/جستجوی کالا
    smalltalk  سلام و احوال‌پرسی و تشکر
    dym        «منظورتون کدومه؟»
    human      به همکار سپرده شد (شکایت، درخواست همکار…)
    unknown    نفهمید

فایل تست: «جمله<TAB>مسیر مورد انتظار» (چند مسیر با |). خطی که با ! شروع شود شکستِ
شناخته‌شده است: گزارش می‌شود ولی تست را رد نمی‌کند.
"""
import asyncio, json, os, shutil, sys, tempfile, time
from types import SimpleNamespace as NS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_CATALOG = [  # چند کالای نمونه تا مسیرهای کالا هم سنجیده شوند
    ("آیفون 13 128 گیگ", "iPhone 13", "128 گیگابایت", "Midnight", "کارکرده", 125_000_000, "آیفون کارکرده"),
    ("آیفون 13 پرو 256", "iPhone 13 Pro", "256 گیگابایت", "Gold", "کارکرده", 190_000_000, "آیفون کارکرده"),
    ("آیفون 15 پرو مکس 256", "iPhone 15 Pro Max", "256 گیگابایت", "Natural", "کارکرده", 420_000_000, "آیفون کارکرده"),
    ("آیفون 16 128", "iPhone 16", "128 گیگابایت", "Black", "نو", 380_000_000, "آیفون"),
    ("شارژر 20 وات اپل", None, None, None, None, 2_500_000, "شارژر"),
]


def _args():
    a = sys.argv[1:]
    opt = {}
    for k in ("--faq", "--catalog"):
        if k in a:
            i = a.index(k); opt[k] = os.path.abspath(a[i + 1]); del a[i:i + 2]
    mode = a[0] if a and a[0] == "scan" else "check"
    target = a[1] if mode == "scan" and len(a) > 1 else os.path.join(ROOT, "tests", "phrases.tsv")
    return mode, os.path.abspath(target), opt


def _load_messages(path):
    raw = open(path, encoding="utf-8").read()
    try:
        d = json.loads(raw)
        out = []
        for x in d:
            if isinstance(x, dict): out.append((x.get("text", ""), int(x.get("count", 1) or 1)))
            elif isinstance(x, (list, tuple)): out.append((x[0], int(x[1]) if len(x) > 1 else 1))
            else: out.append((str(x), 1))
        return [m for m in out if m[0].strip()]
    except ValueError:
        return [(l.strip(), 1) for l in raw.splitlines() if l.strip()]


async def main():
    mode, target, opt = _args()
    work = tempfile.mkdtemp(prefix="answer_check_")
    if opt.get("--faq"): shutil.copy(opt["--faq"], os.path.join(work, "faq.json"))
    os.chdir(work)                      # فایل‌های داده‌ی ربات اینجا ساخته می‌شوند، نه در ریپو
    os.environ.setdefault("BOT_TOKEN", "0:check"); os.environ.setdefault("ADMIN_ID", "1")
    sys.path.insert(0, ROOT)
    import logging; logging.disable(logging.CRITICAL)
    import bot as B, catalog as C

    # همان بارگذاری راه‌اندازی ربات (post_init)
    await B.init_db(); await B.load_human(); await B.load_pages(); await B.load_topics(); await B.load_data()
    await B.load_banners(); await B.load_workhours(); await B.load_buttons(); await B.load_settings()
    await B.load_stats(); await B.load_menu(); await B.load_places(); await B.load_admins()
    await B.load_faq(); await B.load_unmatched(); await B.load_learn()
    B.settings.update(typing_delay=False, forward_user_msgs=True)
    if opt.get("--catalog"):
        C.load(opt["--catalog"])
    else:
        C.set_items([C.normalize({"id": i, "name": n, "permalink": f"https://stland.ir/p/{i}", "is_in_stock": True,
                                  "prices": {"price": str(p), "currency_minor_unit": 0}, "categories": [{"name": cat}],
                                  "attributes": [{"name": k, "terms": [{"name": v}]} for k, v in
                                                 (("مدل", m), ("حافظه", g), ("رنگ", c), ("وضعیت", s)) if v]})
                     for i, (n, m, g, c, s, p, cat) in enumerate(SAMPLE_CATALOG)])
    C.updated = time.time()

    route = {}
    orig_run, orig_cat = B.run_intent, B.send_catalog
    async def run_intent(msg, item, user, bot, *a, **k):
        route.setdefault(user.id, item["id"])
        return await orig_run(msg, item, user, bot, *a, **k)
    async def send_catalog(*a, **k):
        ok = await orig_cat(*a, **k)
        if ok and k.get("uid"): route[k["uid"]] = "catalog"
        return ok
    async def to_human(update, *a, **k):
        route.setdefault(update.effective_user.id, "human"); return True
    async def handoff(bot, user, *a, **k): route.setdefault(user.id, "human")
    B.run_intent, B.send_catalog, B.forward_to_admin, B.notify_handoff = run_intent, send_catalog, to_human, handoff

    class Msg:
        def __init__(s, uid, text): s.chat_id = uid; s.text = text; s.message_id = 1; s.caption = None; s.photo = None; s.replies = []
        async def reply_text(s, t, **k): s.replies.append(t); return NS(message_id=2, photo=None)
        async def reply_photo(s, *a, **k): return NS(message_id=2, photo=None)
        async def edit_text(s, *a, **k): pass
    async def nop(*a, **k): return NS(message_id=3)
    bot = NS(send_chat_action=nop, send_message=nop, set_message_reaction=nop)

    async def classify(text, uid):
        try: return await asyncio.wait_for(_classify(text, uid), 10)
        except asyncio.TimeoutError: return "timeout"      # مسیری که منتظر چیزی ماند — خودش یک باگ است
        except Exception as e: return f"error:{type(e).__name__}"

    async def _classify(text, uid):
        """هر پیام با مشتری تازه — بی‌حافظه‌ی گفتگو، تا نتیجه‌ها مستقل باشند."""
        u = NS(id=uid, first_name="مشتری", username=None, last_name=None, language_code="fa", is_bot=False)
        await B.save_user(u)
        m = Msg(uid, text)
        ok = await B.assistant_reply(NS(message=m, effective_user=u, effective_chat=NS(id=uid, type="private")),
                                     NS(bot=bot, user_data={}), text, u)
        c = B.brain_ctx.get(uid) or {}
        if c.get("dym"): return "dym"
        if "unk" in c and route.get(uid) in (None, "human"): return "unknown"   # نفهمید و به همکار سپرد
        if uid in route: return route[uid]
        return "smalltalk" if ok and m.replies else "unknown"

    ok_routes = lambda r: r not in ("unknown", "human", "dym", "timeout") and not r.startswith("error")
    if mode == "check":
        rows = []
        for ln in open(target, encoding="utf-8"):
            ln = ln.rstrip("\n")
            if not ln.strip() or ln.lstrip().startswith("#"): continue
            known = ln.startswith("!")
            text, _, want = ln.lstrip("!").partition("\t")
            rows.append((text.strip(), {w.strip() for w in want.split("|")}, known))
        fails = known_fails = fixed = 0
        for i, (text, want, known) in enumerate(rows):
            got = await classify(text, 10_000 + i)
            good = got in want
            if good and known: fixed += 1; print(f"🎉 درست شد (! را بردارید): {text}  →  {got}")
            elif not good and known: known_fails += 1
            elif not good: fails += 1; print(f"❌ {text}  →  {got}   (انتظار: {'|'.join(sorted(want))})")
        n = len(rows)
        print(f"\n{n - fails - known_fails}/{n} درست · {fails} شکست تازه · {known_fails} شکست شناخته‌شده"
              + (f" · {fixed} شناخته‌شده درست شد" if fixed else ""))
        sys.stdout.flush()   # os._exit بافر را خالی نمی‌کند
        os._exit(1 if fails else 0)
    else:
        msgs = _load_messages(target)
        res = []
        for i, (text, cnt) in enumerate(msgs):
            res.append((text, cnt, await classify(text, 20_000 + i)))
        tot = sum(c for _, c, _ in res) or 1
        good = sum(c for _, c, r in res if ok_routes(r))
        print(f"پوشش: {good}/{tot} = {100 * good / tot:.0f}٪  ({len(res)} پیام یکتا)\n")
        by = {}
        for t, c, r in res: by.setdefault(r, []).append((c, t))
        for r in sorted(by, key=lambda r: (ok_routes(r), -sum(c for c, _ in by[r]))):
            items = sorted(by[r], reverse=True)
            print(f"── {r} ({sum(c for c, _ in items)})")
            for c, t in items[:40]: print(f"   ×{c}  {t}")
        sys.stdout.flush()
        os._exit(0)


if __name__ == "__main__":
    try: asyncio.run(main())
    finally:
        sys.stdout.flush()
        os._exit(2)     # رشته‌ی aiosqlite نگذارد پایان برنامه گیر کند (خروجی‌های عادی زودتر os._exit می‌زنند)
