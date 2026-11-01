"""مغز مشترک اینستاگرام و تلگرام: موتور فهم ربات تلگرام (tgbot/brain.py) برای هر کانال.

بدون هیچ API و بدون هزینه. همان نیت‌ها (faq.json)، همان فهرست کالای سایت (catalog.json) و همان
متن بخش‌ها (data.json) که ربات تلگرام دارد و از پنل مدیریتش ویرایش می‌شود، اینجا هم خوانده می‌شود؛
پس دانش یکی است. خروجی متن ساده است (بدون دکمه و HTML) تا در دایرکت اینستاگرام هم کار کند.

اگر پیام را محکم نفهمید None برمی‌گرداند تا لایه‌ی بعد (هوش مصنوعی یا ارجاع) تصمیم بگیرد؛
هیچ‌وقت چیزی از خودش نمی‌سازد.
"""
import html
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path

from . import config

TG_DIR = Path(__file__).resolve().parent.parent / "tgbot"
if str(TG_DIR) not in sys.path:
    sys.path.insert(0, str(TG_DIR))

import brain  # noqa: E402  (tgbot/brain.py)
import catalog  # noqa: E402  (tgbot/catalog.py)
import specs  # noqa: E402  (tgbot/specs.py)

SHOP_NAME = "استوک لند"
SITE = "https://stland.ir"
INACTIVE_BRANDS = ("آیپد", "مک‌بوک", "اپل‌واچ", "ایرپاد")
MAX_ITEMS = 3
# همان الگوهای ربات تلگرام (tgbot/bot.py)
LIST_RX = re.compile(r"(?:^|\s)(?:لیست|لیستتون|لیستو|لیستش)(?:\s|$)|چی\s*(?:دارید|دارین|داری)|"
                     r"چه\s*(?:گوشی|مدل|محصول|کالا|ایفون)\S*\s*(?:دارید|دارین|موجود)|"
                     r"موجودی(?:ا|ها)?(?:تون|تان)|محصولات(?:تون)?|کالاها(?:تون)?")
HAVE_RX = re.compile(r"(?<!\S)(?:دارید|دارین|داری|دارن|هست|هستش|موجود\S*|قیمت\S*|چند|چنده|چقدر\S*|چقد|"
                     r"میخوام|میخواستم|میخام|میخواهم|لازم دارم|بخرم)(?!\S)")
# نیت ربات تلگرام ← دسته‌ی نیت در لاگ پنل
_INTENT = {"i_price": "price", "i_stock": "availability", "i_installment": "installment", "i_greet": "greeting"}

_cache: dict = {}   # نام فایل → (mtime، داده)


def data_dir() -> Path:
    return Path(config.TG_DATA_DIR)


def _load_json(name: str, default):
    p = data_dir() / name
    try:
        mt = p.stat().st_mtime
    except OSError:
        return default
    hit = _cache.get(name)
    if hit and hit[0] == mt:
        return hit[1]
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return hit[1] if hit else default
    _cache[name] = (mt, d)
    if name == "catalog.json":
        catalog.set_items(d.get("items") or [])
        catalog.updated = float(d.get("updated") or 0)
    return d


def intents() -> list:
    faq = _load_json("faq.json", [])
    return [x for x in faq if isinstance(x, dict) and x.get("enabled", True) and (x.get("answer") or x.get("action"))]


def available() -> bool:
    return bool(intents())


def _catalog_ready() -> bool:
    _load_json("catalog.json", {})
    return bool(catalog.items)


def _plain(text: str) -> str:
    """HTML ربات تلگرام ← متن ساده؛ لینک‌ها به شکل «نام: آدرس»."""
    t = re.sub(r'<a\s+href="([^"]+)"[^>]*>(.*?)</a>', lambda m: f"{m.group(2)}: {m.group(1)}", text or "", flags=re.S)
    t = re.sub(r"<br\s*/?>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(t)).strip()


def _join(*parts) -> str:
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def _short_link(x: dict) -> str:
    return f"{SITE}/?p={x['id']}" if x.get("id") else x.get("link", "")


def _item_line(x: dict) -> str:
    a = x.get("attrs") or {}
    bits = [a.get("حافظه", ""), a.get("رنگ", ""), a.get("وضعیت", "") if x.get("model") else "",
            f"باتری {a['سلامت باتری']}" if a.get("سلامت باتری") else ""]
    bits = " · ".join(b for b in bits if b)
    last = " · 🔥 آخرین عدد" if x.get("left") == 1 else ""
    return f"• {x['name']}" + (f" · {bits}" if bits else "") + f"\n  💰 {catalog.fmt_price(x['price'])}{last}\n  {_short_link(x)}"


def _catalog_reply(text: str, product: str) -> str | None:
    """جستجوی کالا در فهرست سایت؛ None اگر پیام جستجوی کالا نبود."""
    q = catalog.parse(text, product)
    if not q:
        return None
    res = catalog.search(q)
    what = catalog.describe(q) or "این مورد"
    if res:
        lines = [_item_line(x) for x in res[:MAX_ITEMS]]
        more = f"\n\nو {catalog.fa(len(res) - MAX_ITEMS)} مورد دیگر؛ لیست کامل: {SITE}" if len(res) > MAX_ITEMS else ""
        return f"موجودی‌های {what}:\n\n" + "\n\n".join(lines) + more
    near = catalog.search(q, family=True) if q.get("model") else []
    if near:
        return (f"الان {what} موجود نداریم 🙏 گزینه‌های نزدیک:\n\n" + "\n\n".join(_item_line(x) for x in near[:2]))
    return f"الان {what} موجود نداریم 🙏 لیست به‌روز همه‌ی موجودی‌ها: {SITE}"


def _section(key: str) -> str:
    d = _load_json("data.json", {})
    return _plain(d.get(key, "")) if isinstance(d, dict) else ""


DAY_FA = {"0": "شنبه", "1": "یکشنبه", "2": "دوشنبه", "3": "سه‌شنبه", "4": "چهارشنبه", "5": "پنجشنبه", "6": "جمعه"}
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _hours_text() -> str:
    """ساعت کاری هفتگی از همان workhours.json ربات تلگرام، با وضعیت امروز."""
    import jdatetime
    st = _load_json("settings.json", {})
    if isinstance(st, dict) and st.get("store_open") is False:
        return "🔴 فروشگاه موقتاً بسته است"
    wh = _load_json("workhours.json", {})
    if not isinstance(wh, dict) or not wh.get("schedule") or not wh.get("enabled", True):
        return ""
    sched = wh["schedule"]
    today = str(jdatetime.datetime.fromgregorian(datetime=datetime.now(brain_tz())).weekday())
    rows = []
    for k, name in DAY_FA.items():
        day = sched.get(k, {})
        shifts = [s for s in day.get("shifts", []) if _HHMM.match(s.get("from", "")) and _HHMM.match(s.get("to", ""))]
        when = " و ".join(f"{catalog.fa(s['from'])} تا {catalog.fa(s['to'])}" for s in shifts)
        mark = "👈 " if k == today else ""
        rows.append(f"{mark}{name}: {when}" if day.get("open") and when else f"{mark}{name}: تعطیل")
    return "🕐 ساعت کاری:\n" + "\n".join(rows)


def _render(item: dict, text: str, product: str, name: str):
    """(متن، کار) یک نیت؛ کار: reply | handoff."""
    values = {"name": name, "product": product, "shop": SHOP_NAME, "status": "", "hours": ""}
    answer = _plain(brain.fill(brain.pick_variant(item.get("answer", ""), product=product), **values))
    action = item.get("action") or ""
    if action == "prices" or item.get("id") in ("i_stock", "i_accessory"):
        cat = _catalog_reply(text, "" if item.get("id") == "i_accessory" else product) if _catalog_ready() else None
        return (cat or _join(answer, f"قیمت‌های روز همیشه در سایت به‌روز است: {SITE}")), "reply"
    if action.startswith("section:"):
        return _join(answer, _section(action[8:])), "reply"
    if action == "hours":
        return _join(answer, _hours_text()), "reply"
    if action == "human":
        return answer or "پیامتون رو به همکارم دادم، به‌زودی جواب می‌ده 🙏", "handoff"
    if action == "notify":
        return answer or "حتماً! همکارم هر وقت رسید خبرتون می‌کنه 🔔", "handoff"
    if action in ("specs", "compare"):
        keys = specs.find_models(text)
        if action == "compare" and len(keys) >= 2:
            return _plain(specs.compare_text(keys)), "reply"
        if keys:
            return _plain(specs.spec_text(keys[0])), "reply"
    return answer, "reply"


def decide(text: str, username: str | None = None):
    """تصمیم موتور فهم: (action، reply، intent، score، handoff_reason) یا None اگر محکم نفهمید."""
    its = intents()
    if not its:
        return None
    name = ""   # نام کوچک اینستاگرام در دسترس نیست؛ نام کاربری را در سلام نمی‌آوریم
    a = brain.analyze(text, its)
    tags = a["tags"]
    hour = datetime.now(brain_tz()).hour
    lead = brain.greet_line(name, hour, text=text) if "greet" in tags else ""
    if "tired" in tags:
        lead = _join(lead, brain.say("tired"))

    mood = brain.mood(text)
    if mood in ("complaint", "wait"):
        reason = "شکایت مشتری" if mood == "complaint" else "مشتری منتظر جواب است و پیگیری می‌کند"
        return "handoff", _join(lead, random.choice(brain.MOOD_LEADS[mood])), "complaint", 1.0, f"{reason}: {text[:120]}"
    if mood == "issue":
        lead = _join(lead, random.choice(brain.MOOD_LEADS["issue"]))

    by_id = {x.get("id"): x for x in its}
    if by_id.get("i_other") and brain.product(text).startswith(INACTIVE_BRANDS):
        body, act = _render(by_id["i_other"], text, a["product"], name)
        return act, _join(lead, body), "other", 1.0, ""

    if _catalog_ready():
        q = catalog.parse(text, a["product"])
        n = brain.norm(text)
        shop = any(k in q for k in ("color", "max", "min", "sort", "storage", "battery"))
        strong = shop or any(k in q for k in ("variant", "acc"))
        other = a["intent"] and a["intent"].get("id") not in ("i_price", "i_stock", "i_accessory")
        ask = q.get("model") and HAVE_RX.search(n)
        if LIST_RX.search(n) or shop or ((strong or ask) and not other):
            cat = _catalog_reply(text, a["product"])
            if cat:
                return "reply", _join(lead, cat), "price", 1.0, ""

    multi = brain.match_all(text, its)
    if multi:
        parts, act = [], "reply"
        for it, _, clause in multi:
            body, k = _render(it, clause, brain.carry_product(clause, a["product"]) or a["product"], name)
            parts.append(body)
            act = "handoff" if k == "handoff" else act
        return act, _join(lead, *parts), _INTENT.get(multi[0][0].get("id"), "other"), 1.0, \
            ("درخواست همکار در پیام چندسؤالی: " + text[:120]) if act == "handoff" else ""

    it = a["intent"]
    if it:
        body, act = _render(it, text, a["product"], name)
        if not body:
            return None
        return act, _join(lead, body), _INTENT.get(it.get("id"), "other"), float(a["score"] or 0), \
            (f"{it.get('id')}: {text[:120]}" if act == "handoff" else "")

    if not a["rest"] and tags:
        if "who" in tags:
            return "reply", _join(lead, brain.who_reply(SHOP_NAME)), "greeting", 1.0, ""
        for t in ("thanks", "bye", "how", "laugh", "no"):
            if t in tags:
                return "reply", _join(lead, brain.say(t)), "thanks" if t == "thanks" else "greeting", 1.0, ""
        if "greet" in tags:
            return "reply", _join(lead, brain.say("greet_chat")), "greeting", 1.0, ""
    return None


def brain_tz():
    import pytz
    return pytz.timezone("Asia/Tehran")
