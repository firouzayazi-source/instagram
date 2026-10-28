"""لیست کالای زنده از سایت استوک لند (ووکامرس، خروجی عمومی Store API).

سایت با نوو (هسته‌ی مرکزی) هم‌گام است؛ ربات فقط همان داده‌ی عمومیِ منتشرشده
برای مشتری را می‌خواند — بی‌رمز، بی‌دسترسی به سیستم مرکزی. یک نسخه کنار ربات
(catalog.json) نگه داشته می‌شود تا اگر سایت موقتاً در دسترس نبود، ربات با آخرین
لیست جواب بدهد.
"""
import html, json, re, time
import brain, specs

SITE = "https://stland.ir"
API = SITE + "/wp-json/wc/store/v1/products"
SKIP_CATS = {"پرفروش‌ها"}        # دسته‌ی تبلیغی، نه نوع کالا

items: list = []
updated = 0.0                     # زمان آخرین دریافت موفق (epoch)

_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _model_key(m):
    """«iPhone 15 Pro Max» → «15 pro max» — همان کلید جدول مشخصات (specs)."""
    m = " ".join((m or "").lower().replace("iphone", "").split())
    return m or None


def normalize(p):
    pr = p.get("prices") or {}
    try:
        price = int(pr.get("price") or 0) // 10 ** int(pr.get("currency_minor_unit") or 0)
    except (TypeError, ValueError):
        price = 0
    cats = [c.get("name", "") for c in p.get("categories") or [] if c.get("name") not in SKIP_CATS]
    attrs = {a.get("name", ""): "، ".join(t.get("name", "") for t in a.get("terms") or [])
             for a in p.get("attributes") or []}
    return {"id": p.get("id"), "name": html.unescape(p.get("name", "")), "price": price,
            "stock": bool(p.get("is_in_stock")), "left": p.get("low_stock_remaining"),
            "cats": cats, "cat": cats[0] if cats else "سایر", "link": p.get("permalink", ""),
            "model": _model_key(attrs.get("مدل")), "attrs": attrs}


async def fetch(client):
    """همه‌ی صفحه‌های لیست (هر صفحه ۱۰۰ کالا)."""
    out, page = [], 1
    while True:
        r = await client.get(API, params={"per_page": 100, "page": page})
        r.raise_for_status()
        out += [normalize(p) for p in r.json()]
        if page >= int(r.headers.get("x-wp-totalpages") or 1) or page >= 20:
            return out
        page += 1


def set_items(new, path=None):
    global items, updated
    items, updated = new, time.time()
    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"updated": updated, "items": items}, f, ensure_ascii=False)


def load(path):
    global items, updated
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        items, updated = d.get("items") or [], float(d.get("updated") or 0)
    except (OSError, ValueError):
        pass


def fresh(max_age=6 * 3600):
    return bool(items) and time.time() - updated < max_age


def in_stock():
    return [x for x in items if x["stock"]]


def _used(x):
    return "کارکرده" in x["attrs"].get("وضعیت", "") or any("کارکرده" in c for c in x["cats"])


# ── پیدا کردن کالای خواسته‌شده
ACCESSORY_WORDS = {"شارژر": "شارژر", "اداپتور": "شارژر", "کلگی": "شارژر", "کابل": "کابل",
                   "محافظ": "محافظ صفحه", "گلس": "محافظ صفحه", "جانبی": "لوازم جانبی"}


def _storage(t):
    m = re.search(r"\b(64|128|256|512)\b", t)
    if m:
        return m.group(1)
    return "ترا" if re.search(r"\b1\s*(ترا|tb)", t) else ""


def find(text, product=""):
    """(کالاها, دقیق, برچسب). کالاها None یعنی پیام درباره‌ی کالای خاصی نیست.

    مدل دقیق نبود → هم‌خانواده‌های موجود (برای «۱۳» یعنی ۱۳ پرو، ۱۳ پرو مکس…)
    با دقیق=False؛ هیچ‌کدام نبود → لیست خالی.
    """
    t = brain.norm(text)
    stock = in_stock()
    # «۱۳ پرو» بی‌برند هم آیفون است — فروشگاه تخصصی اپل است
    cands = [product] + brain.products_all(text)
    key = next((k for p in cands if p for k in
                [specs.key_of(p if p.startswith("آیفون") else "آیفون " + p)] if k), None) \
        or next(iter(specs.find_models(text)), None)
    if key:
        label = specs.name_of(key)
        hit = [x for x in stock if x["model"] == key]
        gb = _storage(t)
        if gb and [x for x in hit if gb in brain.norm(x["attrs"].get("حافظه", ""))]:
            hit = [x for x in hit if gb in brain.norm(x["attrs"].get("حافظه", ""))]
        if hit:
            return hit, True, label
        num = key.split()[0]
        return [x for x in stock if x["model"] and x["model"].split()[0] == num], False, label
    for w, cat in ACCESSORY_WORDS.items():
        if w in t:
            return [x for x in stock if cat in x["cats"] or w in brain.norm(x["name"])], True, cat
    return None, True, ""


# ── پیشنهاد مشاور خرید
def _budget(b):
    """«۴۰ میلیون» / «40» → ۴۰٬۰۰۰٬۰۰۰ تومان؛ گزینه‌های آماده → None."""
    m = re.search(r"(\d+(?:\.\d+)?)", brain.norm(b or ""))
    if not m:
        return None
    n = float(m.group(1))
    return int(n * 1_000_000) if n < 1000 else int(n)


def suggest(st, limit=3):
    phones = [x for x in in_stock() if x["model"] and x["price"]]
    if st.get("n") == "آک":
        phones = [x for x in phones if not _used(x)]
    elif st.get("n") == "کارکرده":
        phones = [x for x in phones if _used(x)]
    f = st.get("f", "")
    def liked(x):
        m = x["model"]
        if f in ("دوربین", "سرعت و بازی"): return "pro" in m
        if f == "باتری و صفحه‌ی بزرگ": return "max" in m or "plus" in m
        if f == "سایز جمع‌وجور": return not ("max" in m or "plus" in m)
        return True
    b = st.get("b", "")
    budget = _budget(b)
    if budget:
        fit = [x for x in phones if x["price"] <= budget * 1.05]
        pool = sorted(fit, key=lambda x: (not liked(x), -x["price"])) if fit else \
            sorted(phones, key=lambda x: abs(x["price"] - budget))
    elif b == "اقتصادی":
        pool = sorted(phones, key=lambda x: (not liked(x), x["price"]))
    elif b == "بهترین مدل":
        pool = sorted(phones, key=lambda x: (not liked(x), -x["price"]))
    else:   # متوسط: نزدیک میانه‌ی قیمت‌ها
        mid = sorted(x["price"] for x in phones)[len(phones) // 2] if phones else 0
        pool = sorted(phones, key=lambda x: (not liked(x), abs(x["price"] - mid)))
    return pool[:limit]


# ── نمایش
def fmt_price(n):
    return f"{n:,}".replace(",", "٬").translate(_FA) + " تومان" if n else "قیمت: تماس بگیرید"


def line(x):
    a = x["attrs"]
    bits = [a.get("رنگ", ""), a.get("وضعیت", ""),
            f"باتری {a['سلامت باتری']}" if a.get("سلامت باتری") else ""]
    bits = " · ".join(html.escape(b) for b in bits if b)
    last = " · 🔥 آخرین عدد" if x.get("left") == 1 else ""
    return (f"• <a href=\"{html.escape(x['link'])}\">{html.escape(x['name'])}</a>"
            + (f" · {bits}" if bits else "") + f"\n   💰 {fmt_price(x['price'])}{last}")


def list_html(xs, title, foot="", limit=3800):
    """پیام(ها)ی لیست، گروه‌بندی‌شده بر اساس دسته (پرتعدادترها اول)."""
    groups = {}
    for x in xs:
        groups.setdefault(x["cat"], []).append(x)
    blocks = [f"<b>{html.escape(title)}</b>"]
    for cat, g in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(groups) > 1:
            blocks.append(f"\n<b>— {html.escape(cat)} ({str(len(g)).translate(_FA)}) —</b>")
        blocks += [line(x) for x in sorted(g, key=lambda x: x["price"])]
    if foot:
        blocks.append("\n" + foot)
    out, cur = [], ""
    for b in blocks:
        if cur and len(cur) + len(b) + 1 > limit:
            out.append(cur); cur = ""
        cur = f"{cur}\n{b}" if cur else b
    return out + [cur]
