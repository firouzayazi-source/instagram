"""لیست کالای زنده از سایت استوک لند (ووکامرس، خروجی عمومی Store API).

سایت با نوو (هسته‌ی مرکزی) هم‌گام است؛ ربات فقط همان داده‌ی عمومیِ منتشرشده
برای مشتری را می‌خواند — بی‌رمز، بی‌دسترسی به سیستم مرکزی. یک نسخه کنار ربات
(catalog.json) نگه داشته می‌شود تا اگر سایت موقتاً در دسترس نبود، ربات با آخرین
لیست جواب بدهد.

برای هزار کالا هم مرتب می‌ماند: لیست یک‌جا ریخته نمی‌شود — اول دسته‌ها (آیفون نو،
آیفون کارکرده، شارژر، کابل…)، بعد مدل‌ها، بعد کالاها صفحه‌به‌صفحه. جستجوی مشتری
(«۱۳ پرو مشکی زیر ۲۰۰ میلیون») مستقیم به نتیجه می‌رسد.
"""
import hashlib, html, json, re, time
import jdatetime
import brain, specs

SITE = "https://stland.ir"
API = SITE + "/wp-json/wc/store/v1/products"
SKIP_CATS = {"پرفروش‌ها"}        # دسته‌ی تبلیغی، نه نوع کالا
PAGE = 8                          # کالا در هر صفحه

items: list = []
updated = 0.0                     # زمان آخرین دریافت موفق (epoch)

_FA = str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫")


def fa(x):
    return str(x).translate(_FA)


# ════════════════════════════════════════════════
#  دریافت و نگه‌داری
# ════════════════════════════════════════════════
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
    x = {"id": p.get("id"), "name": html.unescape(p.get("name", "")), "price": price,
         "stock": bool(p.get("is_in_stock")), "left": p.get("low_stock_remaining"),
         "cats": cats, "cat": cats[0] if cats else "سایر", "link": p.get("permalink", ""),
         "model": _model_key(attrs.get("مدل")), "attrs": attrs, "sku": p.get("sku") or "",
         "image": ((p.get("images") or [{}])[0] or {}).get("src", "")}
    x["used"] = "کارکرده" in attrs.get("وضعیت", "") or any("کارکرده" in c for c in cats)
    return x


async def fetch(client):
    """همه‌ی صفحه‌های لیست (هر صفحه ۱۰۰ کالا)."""
    out, page = [], 1
    while True:
        r = await client.get(API, params={"per_page": 100, "page": page})
        r.raise_for_status()
        out += [normalize(p) for p in r.json()]
        if page >= int(r.headers.get("x-wp-totalpages") or 1) or page >= 30:
            return out
        page += 1


def set_items(new, path=None):
    global items, updated
    for x in new:                 # کش قدیمی (پیش از فیلد used) هم درست کار کند
        x.setdefault("used", "کارکرده" in x["attrs"].get("وضعیت", ""))
        x.setdefault("sku", ""); x.setdefault("image", "")
    items, updated = new, time.time()
    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"updated": updated, "items": items}, f, ensure_ascii=False)


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        set_items(d.get("items") or [])
        globals()["updated"] = float(d.get("updated") or 0)
    except (OSError, ValueError):
        pass


def fresh(max_age=6 * 3600):
    return bool(items) and time.time() - updated < max_age


def in_stock():
    return [x for x in items if x["stock"]]


def by_id(i):
    return next((x for x in items if str(x["id"]) == str(i)), None)


# ════════════════════════════════════════════════
#  دسته‌ها: آیفون نو، آیفون کارکرده، بعد بقیه بر اساس دسته‌ی سایت
# ════════════════════════════════════════════════
ICONS = {"شارژر": "🔌", "کابل": "🔗", "محافظ": "🛡", "قاب": "📦", "هندزفری": "🎧",
         "پاوربانک": "🔋", "دیجیتال": "💾", "جانبی": "🧩"}


def _gid(x):
    if x["model"]:
        return "used" if x["used"] else "new"
    return "c" + hashlib.md5(x["cat"].encode()).hexdigest()[:6]


def groups():
    """[(gid, عنوان, آیکون, کالاها)] — آیفون‌ها اول، بقیه پرتعدادتر اول."""
    gs = {}
    for x in in_stock():
        gs.setdefault(_gid(x), []).append(x)
    out = []
    for gid, xs in gs.items():
        if gid == "new":
            out.append((gid, "آیفون نو (آک)", "✨", xs))
        elif gid == "used":
            out.append((gid, "آیفون کارکرده", "📱", xs))
        else:
            cat = xs[0]["cat"]
            icon = next((i for w, i in ICONS.items() if w in cat), "🧩")
            out.append((gid, cat, icon, xs))
    order = {"new": 0, "used": 1}
    return sorted(out, key=lambda g: (order.get(g[0], 2), -len(g[3])))


def group(gid):
    return next((g for g in groups() if g[0] == gid), None)


def model_order(m):
    """جدیدترها اول: «16 pro max» قبل از «16» و «15 pro max»."""
    num = re.match(r"\d+", m or "")
    var = {"pro max": 0, "pro": 1, "plus": 2, "": 3, "mini": 4}.get(" ".join((m or "").split()[1:]), 5)
    return (-(int(num.group()) if num else 0), var, m or "")


def model_name(m):
    try:
        return specs.name_of(m)
    except Exception:
        return "آیفون " + m


# ════════════════════════════════════════════════
#  فهم جستجوی مشتری
# ════════════════════════════════════════════════
# رنگ فارسی → کلمه‌هایی که در نام رنگ انگلیسی سایت می‌آیند
COLORS = {
    "مشکی": ("black", "midnight", "graphite", "space", "jet"),
    "سیاه": ("black", "midnight", "graphite", "space", "jet"),
    "سفید": ("white", "starlight", "silver"), "نقره": ("silver", "white"),
    "طلایی": ("gold",), "رزگلد": ("rose",), "گلد": ("gold",),
    "ابی": ("blue", "sierra", "pacific", "ultramarine", "teal"),
    "سرمه": ("blue", "midnight"), "سبز": ("green", "alpine"), "قرمز": ("red",),
    "صورتی": ("pink",), "بنفش": ("purple", "lavender"), "زرد": ("yellow",),
    "نارنجی": ("orange",), "کرم": ("desert", "starlight", "natural"),
    "نچرال": ("natural",), "تیتانیوم": ("titanium", "natural"),
    "طوسی": ("gray", "grey", "graphite", "space"), "خاکستری": ("gray", "grey", "graphite", "space"),
    "دودی": ("gray", "graphite", "space"),
}
for _en in ("black", "white", "silver", "gold", "blue", "green", "red", "pink", "purple",
            "yellow", "orange", "natural", "midnight", "starlight", "graphite", "titanium"):
    COLORS[_en] = (_en,)

NEW_WORDS = {"نو", "اکبند", "اک", "پلمب", "پلمپ", "اکبندی", "new", "صفر", "اوریجینال"}
USED_WORDS = {"کارکرده", "کارکرد", "استوک", "used", "دستدوم"}
CHEAP = {"ارزون", "ارزان", "ارزونتر", "ارزانتر", "ارزونترین", "ارزانترین", "اقتصادی", "مقرون", "کمترین"}
DEAR = {"گرون", "گران", "گرونترین", "گرانترین", "بهترین", "بالاترین", "پرچمدار", "لوکس"}
# مدل بدون عدد («پرومکس سفید») — با غلط‌های رایج تایپی
VARIANTS = {"pro max": ("پرومکس", "پرمکس", "پروماکس", "پرماکس", "promax", "پرومکث"),
            "pro": ("پرو", "pro", "پروو"), "plus": ("پلاس", "plus", "پلس"), "mini": ("مینی", "mini")}
PHONE_WORDS = {"گوشی", "موبایل", "ایفون", "ایفن", "ایفونا", "iphone", "گوشیا", "گوشیها", "تلفن"}

# لوازم جانبی: کلمه‌ی مشتری → کلمه‌هایی که در دسته یا نام کالای سایت دنبالشان می‌گردیم
ACCESSORY = {
    "شارژر": ("شارژر", "اداپتور", "ادابتور", "کلگی", "شارژ", "adapter", "charger"),
    "کابل": ("کابل", "سیم", "cable"),
    "محافظ صفحه": ("محافظ", "گلس", "گلاس", "glass", "برچسب"),
    "قاب": ("قاب", "کاور", "case", "کیس"),
    "هندزفری": ("هندزفری", "هدفون", "هدست", "headphone"),
    "پاوربانک": ("پاوربانک", "powerbank"),
    "لوازم جانبی": ("جانبی", "اکسسوری", "لوازم"),
}

# کلمه‌هایی که در جستجو معنای فیلتر ندارند (پرسش، احوال‌پرسی، «لیست»…)
FILLER = brain.STOPWORDS | {
    "لیست", "لیستتون", "لیستو", "لیستش", "قیمت", "قیمتا", "قیمتش", "چند", "چنده", "چقدر", "چقد",
    "دارید", "دارین", "داری", "داره", "موجود", "موجوده", "موجودی", "موجودیا", "موجودیاتون",
    "هست", "هستش", "میخوام", "میخواستم", "میخام", "بفرستید", "بفرست", "بدید", "بده", "نشون",
    "بدین", "ببینم", "چیا", "کدوم", "کدوما", "چی", "چه", "محصولات", "محصولاتتون", "کالا", "کالاها",
    "کالاهاتون", "مدل", "مدلا", "مدلهای", "رنگ", "رنگی", "حافظه", "گیگ", "گیگابایت", "gb",
    "تومن", "تومان", "میلیون", "م", "زیر", "تا", "کمتر", "بیشتر", "بالای", "بالا", "حدود",
    "حدودا", "حد", "حداکثر", "حداقل", "ترین", "تر", "باتری", "سلامت", "درصد", "ممنون", "مرسی",
    "سلام", "وقت", "بخیر", "لطفا", "دستتون", "درد", "نکنه", "امروز", "الان", "فعلا", "خرید",
    "بخرم", "واسم", "برام", "یکی", "یه", "دونه", "عدد", "تومنی", "میلیونی", "ای", "بهم",
    "نرمال", "معمولی", "ساده", "بیس", "base", "normal",   # «۱۳ نرمال» = خودِ مدل پایه، نه پرو
} | PHONE_WORDS | NEW_WORDS | USED_WORDS | CHEAP | DEAR


def _num_toman(s, unit=""):
    """«۱۵۰» / «150 میلیون» / «2.5» → تومان. عدد کوچک بدون واحد یعنی میلیون (عرف بازار)."""
    n = float(s)
    if "هزار" in unit:
        return int(n * 1000) if n < 1_000_000 else int(n)
    return int(n * 1_000_000) if n < 10_000 else int(n)


_PRICE_MAX = re.compile(r"(?:زیر|کمتر از|کمتر|تا|حداکثر|ارزونتر از|ارزانتر از|نهایتا|ماکزیمم)\s*"
                        r"(\d+(?:\.\d+)?)\s*(میلیون|م|هزار|تومن|تومان)?")
_PRICE_MIN = re.compile(r"(?:بالای|بالاتر از|بیشتر از|حداقل|از)\s*(\d+(?:\.\d+)?)\s*(میلیون|م|هزار)")
_PRICE_ABOUT = re.compile(r"(?:حدود|حدودا|در حد|تقریبا|حول و حوش|دور و بر)?\s*"
                          r"(\d+(?:\.\d+)?)\s*(میلیون|م|میلیونی|تومنی)(?!\S)")
_BATTERY = re.compile(r"باتری\S*\s*(?:سلامت\s*)?(?:بالای|بالا|حداقل|بیشتر از|بالاتر از)?\s*(\d{2})")


def _has(t, words):
    """کلمه (با پسوند محاوره‌ای مثل «مشکیش»، «ارزوناش»)؛ کلمه‌ی کوتاه فقط دقیق — «نو» نباید «نوبت» را بگیرد."""
    return any(re.search(rf"(?<!\S){re.escape(w)}" + (r"\S{0,4}" if len(w) > 2 else "") + r"(?!\S)", t)
               for w in words)


_UNIT = r"\s*(?:میلیون|م(?!\S)|هزار|تومن|تومان|گیگ|گیگابایت|gb|درصد|٪)"


def _num_ok(num, t):
    """عددِ مدل واقعاً مدل است؟ اگر فقط داخل عدد بزرگ‌تر یا کنار واحد آمده، نه.
    اگر اصلاً در متن نیست (مدلِ پیام قبلی گفتگو)، می‌پذیریم."""
    if not num:
        return True
    alone = [m for m in re.finditer(rf"(?<!\d){num}(?!\d)", t) if not re.match(_UNIT, t[m.end():])]
    return bool(alone) or not re.search(num, t)


def parse(text, product="", alias=None):
    """جستجوی مشتری → فیلترها. alias(کلمه‌های ناشناخته) → فیلتر یادگرفته یا None."""
    t = " " + brain.norm(text).replace("ارزون ترین", "ارزونترین").replace("گرون ترین", "گرونترین") \
        .replace("ارزان ترین", "ارزانترین").replace("دست دوم", "دستدوم").replace("دسته دوم", "دستدوم") \
        .replace("پرو مکس", "پرومکس") + " "
    q = {}
    # مدلِ خودِ پیام اول («16e» را find_models درست می‌فهمد)، بعد مدلِ گفتگو
    cands = brain.products_all(text) + [product]
    key = next(iter(specs.find_models(text)), None) or \
        next((k for p in cands if p for k in
              [specs.key_of(p if p.startswith("آیفون") else "آیفون " + p)] if k), None)
    if key and not _num_ok(re.match(r"\d*", key).group(), t):
        key = None                # «۱۵۰ میلیون» آیفون ۱۵ نیست، «۱۲۸ گیگ» آیفون ۱۲ نیست
    if key:
        q["model"] = key
    else:
        for var, words in VARIANTS.items():
            if _has(t, words):
                q["variant"] = var; break
    m = re.search(r"(?<!\d)(64|128|256|512)(?!\d)", t)
    if m:
        q["storage"] = m.group(1)
    elif re.search(r"(?<!\d)1\s*(?:ترا|tb|ترابایت)", t):
        q["storage"] = "ترا"
    for w, ens in COLORS.items():
        if _has(t, [w]):
            q["color"] = (w, ens); break
    if _has(t, NEW_WORDS) and not _has(t, USED_WORDS):
        q["new"] = True
    elif _has(t, USED_WORDS):
        q["new"] = False
    m = _PRICE_MAX.search(t)
    if m:
        q["max"] = _num_toman(m.group(1), m.group(2) or "")
    m = _PRICE_MIN.search(t)
    if m and "max" not in q:
        q["min"] = _num_toman(m.group(1), m.group(2) or "")
    if "max" not in q and "min" not in q:
        m = _PRICE_ABOUT.search(t)
        if m and not (key and m.group(1) in key.split()):
            v = _num_toman(m.group(1))
            q["min"], q["max"] = int(v * 0.85), int(v * 1.15)
    m = _BATTERY.search(t)
    if m:
        q["battery"] = int(m.group(1))
    if _has(t, CHEAP):
        q["sort"] = "cheap"
    elif _has(t, DEAR):
        q["sort"] = "dear"
    for canon, words in ACCESSORY.items():
        if _has(t, words):
            q["acc"] = canon; break
    if "acc" not in q and (_has(t, PHONE_WORDS) or key or "new" in q or "battery" in q or "variant" in q):
        q["phone"] = True
    # کلمه‌های ناشناخته — برای یادگیری و «منظورتون چی بود؟»
    known = set(FILLER) | {w for w in COLORS} | {w for ws in ACCESSORY.values() for w in ws}
    rest = [w for w in t.split() if w not in known and not w.isdigit()
            and brain.stem(w) not in known and not any(w.startswith(k) for k in known if len(k) >= 4)
            and w not in {v for ws in VARIANTS.values() for v in ws} | {"مکس", "max", "ماکس"}
            and not (key and (w == key.replace(" ", "") or re.fullmatch(r"\d{1,2}[^\d\s]+", w)))]
    if rest:
        q["rest"] = rest
        learned = alias(rest) if alias else None
        if learned:
            q.update(learned); q.pop("rest")
    return q


FILTER_KEYS = ("variant", "model", "storage", "color", "new", "max", "min", "battery", "sort", "acc", "phone", "gid")


def is_search(q):
    return any(k in q for k in FILTER_KEYS)


def _battery(x):
    m = re.search(r"\d+", brain.norm(x["attrs"].get("سلامت باتری", "")))
    return int(m.group()) if m else None


def _acc_match(x, canon):
    if canon == "لوازم جانبی":
        return not x["model"]
    words = ACCESSORY[canon]
    hay = brain.norm(" ".join(x["cats"]) + " " + x["name"])
    return any(w in hay for w in words + (canon,))


def search(q, family=False):
    """کالاهای موجودِ مطابق فیلتر. family=True یعنی هم‌خانواده‌های مدل (۱۳ → ۱۳ پرو…)."""
    out = []
    for x in in_stock():
        if "gid" in q and _gid(x) != q["gid"]: continue
        if q.get("phone") and not x["model"]: continue
        if "acc" in q and not _acc_match(x, q["acc"]): continue
        if "variant" in q and (not x["model"] or " ".join(x["model"].split()[1:]) != q["variant"]):
            continue
        if "model" in q and "acc" not in q:
            if family:
                if not x["model"] or x["model"].split()[0] != q["model"].split()[0]: continue
            elif x["model"] != q["model"]: continue
        if "storage" in q and q["storage"] not in brain.norm(x["attrs"].get("حافظه", "") + " " + x["name"]):
            continue
        if "color" in q and not any(e in x["attrs"].get("رنگ", "").lower() for e in q["color"][1]):
            continue
        if "new" in q and x["model"] and x["used"] == q["new"]: continue
        if "max" in q and not (0 < x["price"] <= q["max"]): continue
        if "min" in q and x["price"] < q["min"]: continue
        if "battery" in q and (_battery(x) or 0) < q["battery"]: continue
        out.append(x)
    if "acc" in q and "model" in q:   # «گلس ۱۳» — اول آن‌هایی که نامشان مدل را دارد
        num = q["model"].split()[0]
        out = [x for x in out if re.search(rf"(?<!\d){num}(?!\d)", brain.norm(x["name"]))] or out
    if q.get("sort") == "dear":
        out.sort(key=lambda x: -x["price"])
    elif q.get("sort") == "cheap" or not q.get("model"):
        out.sort(key=lambda x: (x["price"] or 10**12))
    else:
        out.sort(key=lambda x: x["price"])
    return out


# معاوضه یا فروش گوشی خود مشتری («۱۳ دارم ۵۰ روش بذارم»، «چند برمی‌دارید؟») — جستجوی کالا نیست
TRADE_RX = re.compile(r"بر ?می ?دار(?:ید|ین|ی)\b|میخرید|می ?خرین|میخری\b|خرید (?:هم )?(?:دارید|دارین)|"
                      r"روش (?:ب[ذز]ارم|می[ذز]ارم)|ب[ذز]ارم رو(?:ی|ش)|قیمت ?گذاری|امانی|عوض کنم|معاوضه|تعویض با|"
                      r"بفروشم|ارتقا (?:بدم|بدید|بدین)|رو بردارین|رو بردارید")
# کلمه‌هایی که کنار «فقط اسم مدل» معنا عوض نمی‌کنند («من ۱۳ می‌خوام»، «مدل ۱۳ پرومکس»، «رییس ۱۷ پرو»)
_BARE_OK = {"می", "خوام", "میخوام", "میخواستم", "من", "مدل", "رییس", "داداش", "ببخشید", "یه", "یک", "سلام", "لطفا",
            "اقا", "اک", "آک", "کارکرده", "نو", "عزیز", "بزرگوار"}
# نیت‌هایی که اگر محکم خوردند، مدلِ داخل پیام دلیل جستجوی کالا نیست («اقساط ۱۳ پرو»، «۱۳ با ۱۴ چه فرقی داره»)
STRONG_OTHER = {"i_install", "i_tradein", "i_compare", "i_specs", "i_appleid", "i_other", "i_android", "i_human",
                "i_address", "i_hours", "i_return", "i_warranty", "i_shipping", "i_owner", "i_software"}


def wants_catalog(text, q, intent_id, have_rx, list_rx):
    """آیا این پیام جستجوی کالاست؟ (قاعده‌ی مشترک تلگرام و اینستاگرام)
    - معاوضه/فروش گوشی خود مشتری: نه
    - «لیست»، «چی دارید»: بله
    - رنگ، حافظه، بودجه، باتری، «ارزون‌ترین»: بله، مگر اقساط یا معاوضه یا مقایسه باشد
    - مدل + «قیمت/دارید/می‌خوام…» یا فقط اسم مدل («۱۷ پرو مکس»): بله، مگر نیت محکم دیگری خورده باشد
    - «پرو مکس» یا لوازم جانبی بی‌مدل: فقط وقتی نیت دیگری نخورده"""
    n = brain.norm(text)
    if TRADE_RX.search(n):
        return False
    if list_rx.search(n):
        return True
    if any(k in q for k in ("color", "max", "min", "sort", "storage", "battery")):
        return intent_id not in ("i_install", "i_tradein", "i_compare")
    if q.get("model"):
        rest = [w for w in q.get("rest", []) if w not in _BARE_OK]
        bare = not rest and len(n.split()) <= 6
        if (have_rx.search(n) or bare) and intent_id not in STRONG_OTHER:
            return True
    if any(k in q for k in ("variant", "acc")):
        return not intent_id or intent_id in ("i_price", "i_stock", "i_accessory")
    return False


_TIERS = ["mini", "", "plus", "pro", "pro max"]


def _key(num, tier):
    return f"{num} {tier}".strip()


def neighbors(q):
    """یک مدل بالاتر و یک مدل پایین‌تر که الان موجودند، برای یک اشاره‌ی کوتاه زیر نتیجه.
    «۱۳ پرو مکس» → بالا: ۱۴ پرو مکس، ۱۴ پرو یا ۱۵ پرو مکس؛ پایین: ۱۲ پرو مکس، ۱۳ پرو یا ۱۲ پرو.
    خروجی: [(کلید مدل، ارزان‌ترین کالای موجود)] — حداکثر دو مورد. وضعیت (آک/کارکرده) خواسته‌شده رعایت می‌شود."""
    k = q.get("model") or ""
    m = re.fullmatch(r"(\d{1,2})(?: (.+))?", k)
    if not m or "acc" in q:
        return []
    num, tier = int(m.group(1)), m.group(2) or ""
    if tier not in _TIERS:
        return []
    i = _TIERS.index(tier)
    lowers = _TIERS[i - 1:0:-1] if i > 1 else []      # «پرو» → پلاس، معمولی (مینی پایین‌ترِ معمولی حساب نمی‌شود)
    upper = _TIERS[i + 1] if 0 < i < len(_TIERS) - 1 else None
    up = [_key(num + 1, tier)] + [_key(num + 1, t) for t in lowers[:1]] + [_key(num + 2, tier)]
    down = [_key(num - 1, tier)] + [_key(num, t) for t in lowers] + ([_key(num - 1, upper)] if upper else [])
    stock = {}
    for x in in_stock():
        if not x["model"] or x["model"] == k or not x["price"]:
            continue
        if "new" in q and x["used"] == q["new"]:
            continue
        if x["model"] not in stock or x["price"] < stock[x["model"]]["price"]:
            stock[x["model"]] = x
    out = []
    for cands in (up, down):
        hit = next((c for c in cands if c in stock), None)
        if hit:
            out.append((hit, stock[hit]))
    return out


def neighbor_line(q):
    """«💡 شاید اینا هم به کارتون بیاد: ۱۴ پرو مکس از ۲۴۰ میلیون · ۱۲ پرو مکس از ۱۴۵ میلیون» یا «»."""
    nb = neighbors(q)
    if not nb:
        return ""
    bits = [f"{model_name(k)} از {short_price(x['price'])}" for k, x in nb]
    return "💡 شاید اینا هم به کارتون بیاد: " + " · ".join(bits)


def short_price(n):
    if n >= 1_000_000:
        v = n / 1_000_000
        return fa(f"{v:.1f}".rstrip("0").rstrip(".") if v < 100 else f"{v:.0f}") + " میلیون"
    return fa(f"{n // 1000}") + " هزار" if n else "—"


def describe(q):
    bits = []
    if q.get("model") and not q.get("acc"): bits.append(model_name(q["model"]))
    elif q.get("variant"): bits.append("آیفون " + {"pro max": "پرو مکس", "pro": "پرو", "plus": "پلاس",
                                                    "mini": "مینی"}[q["variant"]])
    elif q.get("acc"): bits.append(q["acc"])
    elif q.get("phone"): bits.append("آیفون")
    if q.get("storage"): bits.append("۱ ترابایت" if q["storage"] == "ترا" else fa(q["storage"]) + " گیگ")
    if q.get("color"): bits.append(q["color"][0])
    if "new" in q: bits.append("نو" if q["new"] else "کارکرده")
    if q.get("battery"): bits.append(f"باتری {fa(q['battery'])}٪+")
    if q.get("min") and q.get("max"): bits.append(f"{short_price(q['min'])} تا {short_price(q['max'])}")
    elif q.get("max"): bits.append(f"تا {short_price(q['max'])}")
    elif q.get("min"): bits.append(f"از {short_price(q['min'])}")
    if q.get("gid"):
        g = group(q["gid"])
        if g: bits.append(g[1])
    return " · ".join(bits)


# ════════════════════════════════════════════════
#  پیشنهاد مشاور خرید
# ════════════════════════════════════════════════
def _budget(b):
    m = re.search(r"(\d+(?:\.\d+)?)", brain.norm(b or ""))
    return _num_toman(m.group(1)) if m else None


def suggest(st, limit=3):
    phones = [x for x in in_stock() if x["model"] and x["price"]]
    if st.get("n") == "آک":
        phones = [x for x in phones if not x["used"]]
    elif st.get("n") == "کارکرده":
        phones = [x for x in phones if x["used"]]
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


# ════════════════════════════════════════════════
#  نمایش — هر نما: (متن HTML، ردیف‌های دکمه [(برچسب، داده)])
# ════════════════════════════════════════════════
def fmt_price(n):
    return f"{n:,}".replace(",", "٬").translate(_FA) + " تومان" if n else "قیمت: تماس بگیرید"


def line(x, n=None):
    a = x["attrs"]
    bits = [a.get("رنگ", ""), a.get("وضعیت", "") if x["model"] else "",
            f"باتری {a['سلامت باتری']}" if a.get("سلامت باتری") else ""]
    bits = " · ".join(html.escape(b) for b in bits if b)
    last = " · 🔥 آخرین عدد" if x.get("left") == 1 else ""
    num = f"{fa(n)}. " if n else "• "
    return (f"{num}<a href=\"{html.escape(x['link'])}\">{html.escape(x['name'])}</a>"
            + (f" · {bits}" if bits else "") + f"\n   💰 {fmt_price(x['price'])}{last}")


def _pager(n, page, data):
    """ردیف «◀️ قبلی · ۲/۵ · بعدی ▶️»؛ data(صفحه) داده‌ی دکمه است."""
    pages = (n + PAGE - 1) // PAGE
    if pages <= 1:
        return []
    row = []
    if page > 0: row.append(("◀️ قبلی", data(page - 1)))
    row.append((f"{fa(page + 1)}/{fa(pages)}", "cat_noop"))
    if page < pages - 1: row.append(("بعدی ▶️", data(page + 1)))
    return [row]


def view_items(xs, page, title, data, back=None, foot=""):
    page = max(0, min(page, (len(xs) - 1) // PAGE)) if xs else 0
    chunk = xs[page * PAGE:(page + 1) * PAGE]
    lines = [f"<b>{html.escape(title)}</b>"]
    if len(xs) > PAGE:
        lines.append(f"{fa(len(xs))} مورد — صفحه‌ی {fa(page + 1)}")
    lines.append("برای عکس، جزئیات و رزرو، شماره‌ی کالا را بزنید 👇")
    lines += [line(x, page * PAGE + i + 1) for i, x in enumerate(chunk)]
    if foot: lines.append("\n" + foot)
    nums = [(fa(page * PAGE + i + 1), f"cat_p_{x['id']}") for i, x in enumerate(chunk)]
    rows = [nums[i:i + 4] for i in range(0, len(nums), 4)] + _pager(len(xs), page, data)
    if back: rows.append([("🔙 بازگشت", back), ("📦 همه‌ی دسته‌ها", "cat_home")] if back != "cat_home"
                         else [("📦 همه‌ی دسته‌ها", "cat_home")])
    return "\n".join(lines), rows


def view_home(foot=""):
    gs = groups()
    lines = [f"<b>📦 کالاهای موجود امروز — {fa(sum(len(g[3]) for g in gs))} مورد</b>",
             "یک دسته را انتخاب کنید 👇"]
    for gid, title, icon, xs in gs:
        low = min((x["price"] for x in xs if x["price"]), default=0)
        lines.append(f"{icon} {html.escape(title)} — {fa(len(xs))} مورد"
                     + (f" · از {short_price(low)}" if low else ""))
    if foot: lines.append("\n" + foot)
    btns = [(f"{icon} {title} ({fa(len(xs))})", f"cat_g_{gid}_0") for gid, title, icon, xs in gs]
    return "\n".join(lines), [btns[i:i + 2] for i in range(0, len(btns), 2)]


def view_group(gid, page=0, foot=""):
    g = group(gid)
    if not g:
        return None
    _, title, icon, xs = g
    models = {}
    for x in xs:
        if x["model"]: models.setdefault(x["model"], []).append(x)
    if len(models) <= 1 or len(xs) <= PAGE:
        return view_items(sorted(xs, key=lambda x: x["price"]), page, f"{icon} {title}",
                          lambda p: f"cat_a_{gid}_{p}", "cat_home", foot)
    lines = [f"<b>{icon} {html.escape(title)} — {fa(len(xs))} مورد</b>", "کدام مدل؟ 👇"]
    order = sorted(models, key=model_order)
    for m in order:
        low = min(x["price"] for x in models[m])
        lines.append(f"• {model_name(m)} — {fa(len(models[m]))} عدد · از {short_price(low)}")
    if foot: lines.append("\n" + foot)
    btns = [(f"{model_name(m)} ({fa(len(models[m]))})", f"cat_m_{gid}_0_{m}") for m in order]
    rows = [btns[i:i + 2] for i in range(0, len(btns), 2)]
    rows.append([("📋 همه، ارزان‌ترین اول", f"cat_a_{gid}_0")])
    rows.append([("📦 همه‌ی دسته‌ها", "cat_home")])
    return "\n".join(lines), rows


def view_model(gid, model, page=0, foot=""):
    g = group(gid)
    xs = sorted([x for x in (g[3] if g else []) if x["model"] == model], key=lambda x: x["price"])
    if not xs:
        return None
    return view_items(xs, page, f"{g[2]} {model_name(model)} — {g[1]}",
                      lambda p: f"cat_m_{gid}_{p}_{model}", f"cat_g_{gid}_0", foot)


def view_all(gid, page=0, foot=""):
    g = group(gid)
    if not g:
        return None
    return view_items(sorted(g[3], key=lambda x: x["price"]), page, f"{g[2]} {g[1]}",
                      lambda p: f"cat_a_{gid}_{p}", f"cat_g_{gid}_0" if gid in ("new", "used") else "cat_home",
                      foot)


def results_title(q, n):
    d = describe(q)
    title = f"🔎 {d} — {fa(n)} مورد موجود" if d else f"🔎 {fa(n)} مورد موجود"
    if q.get("sort") == "dear": title += " (گران‌ترین اول)"
    elif q.get("sort") == "cheap": title += " (ارزان‌ترین اول)"
    return title


def view_results(xs, q, page=0, foot="", title=None):
    """نتیجه‌ی جستجو؛ صفحه‌بندی با cat_r_<صفحه> (نتیجه را ربات برای هر مشتری نگه می‌دارد)."""
    title = title or results_title(q, len(xs))
    return view_items(xs, page, title, lambda p: f"cat_r_{p}", "cat_home", foot)


def list_html(xs, title, foot=""):
    """لیست ساده‌ی کوتاه (پیشنهاد مشاور خرید)."""
    return "\n".join([f"<b>{html.escape(title)}</b>"] + [line(x) for x in xs] + (["\n" + foot] if foot else []))


# ════════════════════════════════════════════════
#  کارت محصول و اقساط
# ════════════════════════════════════════════════
ATTR_ICONS = {"مدل": "📱", "حافظه": "💾", "رنگ": "🎨", "وضعیت": "✅", "سلامت باتری": "🔋",
              "پارت نامبر": "🏷", "رجیستر": "📝"}


def card_html(x):
    a = x["attrs"]
    lines = [f"<b>{html.escape(x['name'])}</b>", ""]
    for k, v in a.items():
        if k == "برند" or not v: continue
        lines.append(f"{ATTR_ICONS.get(k, '▫️')} {html.escape(k)}: {html.escape(v)}")
    lines += ["", f"💰 <b>{fmt_price(x['price'])}</b>"]
    if x.get("left") == 1: lines.append("🔥 آخرین عدد")
    elif x.get("left"): lines.append(f"📦 {fa(x['left'])} عدد موجود")
    if x.get("sku"): lines.append(f"🔖 کد کالا: <code>{html.escape(x['sku'])}</code>")
    return "\n".join(lines)


def _up(n, step=1000):
    return -(-int(n) // step) * step


def add_months(d, n):
    """تاریخ شمسی + n ماه، همان روزِ ماه (۳۱ شهریور → ۳۰ مهر)."""
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year; m += 1
    ml = 31 if m <= 6 else 30 if m <= 11 else (30 if jdatetime.date(y, 1, 1).isleap() else 29)
    return jdatetime.date(y, m, min(d.day, ml))


def installments(price, cfg, start=None):
    """[(ماه, روز, پیش‌پرداخت, هزینه‌ی اقساط, قسط ماهانه, جمع)] — فرمول فروشگاه (بدون راس):
    مانده = قیمت − پیش‌پرداخت (حداقل down٪)؛ مانده‌ی مؤثر = مانده + fee_pct٪ مانده (حداکثر fee_cap)؛
    سود = مانده‌ی مؤثر × rate × روز ÷ ۳۰۰۰ (روز = از امروز تا آخرین قسط، تقویم شمسی)؛
    قسط = (مانده‌ی مؤثر + سود) ÷ ماه. مثال کاربر: ۱۰۰م، ۶٪، ۶ قسط از ۱۴۰۵/۰۶/۱۹ → ۱۸۱ روز، قسط ۲۲٬۷۰۰٬۰۰۰."""
    if not price or not cfg: return []
    start = start or jdatetime.date.today()
    down = _up(price * cfg["down"] / 100)
    rem = price - down
    fee = min(int(rem * cfg.get("fee_pct", 0) / 100), cfg.get("fee_cap") or 10**15)
    eff = rem + fee
    mx = cfg["max_months"]
    out = []
    for m in sorted({x for x in (3, 6, mx) if 0 < x <= mx}):
        days = (add_months(start, m).togregorian() - start.togregorian()).days
        interest = eff * cfg["rate"] * days / 3000
        monthly = _up((eff + interest) / m)
        out.append((m, days, down, fee, monthly, down + monthly * m))
    return out


def installment_html(x, cfg):
    rows = installments(x["price"], cfg)
    if not rows: return ""
    pct = lambda v: fa(f"{v:g}")
    down_txt = "یک‌سوم" if abs(cfg["down"] - 100 / 3) < 0.5 else f"{pct(cfg['down'])}٪"
    lines = [f"<b>💳 اقساط {html.escape(x['name'])}</b>", f"قیمت نقدی: {fmt_price(x['price'])}",
             f"پیش‌پرداخت (حداقل {down_txt}): {fmt_price(rows[0][2])}"]
    if rows[0][3]:
        # به دستور صاحب فروشگاه (۱۴ آبان): فقط گفته شود که اختلاف هست؛ مبلغ و درصدش جدا نمایش داده نشود
        lines.append("قیمت اقساطی با قیمت نقدی کمی فرق داره که در قسط‌های زیر حساب شده.")
    lines += [f"سود {pct(cfg['rate'])}٪ ماهانه به روز · با چک یا طلا · تا {fa(cfg['max_months'])} ماه", ""]
    for m, days, _, _, monthly, total in rows:
        lines.append(f"🗓 {fa(m)} ماهه ({fa(days)} روز): ماهی <b>{fmt_price(monthly)}</b>  (جمع {short_price(total)})")
    lines += ["", "اقساط از امروز ماهانه است. پیش‌پرداخت بیشتر = قسط کمتر.",
              "محاسبه تقریبی است؛ دقیقش را همکارم می‌گوید."]
    return "\n".join(lines)
