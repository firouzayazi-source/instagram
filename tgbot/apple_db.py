"""دانشنامه‌ی محصولات اپل (۶ آذر ۱۴۰۵): آیفون، آیپد، مک، اپل‌واچ، ایرپاد و چند لوازم، از اولین مدل تا امروز.

داده در پوشه‌ی apple/ کنار همین فایل است (یک JSON برای هر دسته). مشخصات رسمی لحظه‌ی عرضه است: سال، تراشه،
رم، صفحه، دوربین، حافظه‌ها، رنگ‌ها، درگاه، وزن و ویژگی‌ها. مدل‌های ۲۰۲۴ به بعد از صفحه‌های اپل و رسانه‌های معتبر
وارسی شده‌اند (منبع‌ها در خود داده). هر چیزی که مطمئن نبوده null است و در جواب نمی‌آید.

قیمت و موجودی اینجا نیست: آن‌ها فقط از فهرست زنده‌ی سایت می‌آیند.
مقایسه‌ی آیفون‌های ۱۱ به بعد همچنان با specs.py است (امتیاز تراشه و «چه چیزی بیشتر دارد»)؛ این‌جا برای بقیه.
"""
import json
import re
from pathlib import Path

import brain

DIR = Path(__file__).resolve().parent / "apple"
FILES = {"iphone": "iphone.json", "ipad": "ipad.json", "mac": "mac.json", "other": "watch_airpods.json"}
CAT_FA = {"iphone": "آیفون", "ipad": "آیپد", "mac": "مک", "watch": "اپل‌واچ", "airpods": "ایرپاد",
          "accessory": "لوازم اپل"}
CAT_ICON = {"iphone": "📱", "ipad": "📲", "mac": "💻", "watch": "⌚️", "airpods": "🎧", "accessory": "🍏"}

_FA = str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫")
_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# شکل یکدست کلمه‌ها برای جور کردن نوشته‌ی مشتری با نام مدل
_WORDS = [
    (r"مک ?بوک", "macbook"), (r"macbook", "macbook"), (r"ا?ی ?مک|imac", "imac"), (r"\bمک\b", "mac"),
    (r"ا?ی ?پد|ipad", "ipad"), (r"ا?ی ?فون|iphone", "iphone"), (r"اپل ?واچ|apple ?watch|ساعت اپل", "watch"),
    (r"ا?یر ?پادز?|airpods?", "airpods"), (r"ایر ?تگ|airtag", "airtag"), (r"ویژن ?پرو|vision ?pro", "vision pro"),
    (r"پنسیل|pencil|قلم اپل", "pencil"), (r"استودیو", "studio"), (r"مینی", "mini"), (r"\bایر\b", "air"),
    (r"پرو", "pro"), (r"مکس", "max"), (r"پلاس", "plus"), (r"اولترا", "ultra"), (r"سری", "series"),
    (r"نسل", "gen"), (r"اینچ", "inch"), (r"\bام ?(\d)", r"m\1"), (r"اس ?ای", "se"), (r"ده\b", "10"),
]


def fa(x) -> str:
    return str(x).translate(_FA)


def canon(text: str) -> str:
    """«مکبوک ایر ام ۲» ≈ «MacBook Air (M2)» → «macbook air m2»."""
    t = brain.norm(text or "").translate(_TO_EN).lower()
    t = re.sub(r"[()\[\],\-–/]+", " ", t)
    for rx, rep in _WORDS:
        t = re.sub(rx, rep, t)
    t = re.sub(r"(?<=[a-z]{2})(?=\d)|(?<=\d)(?=[a-z]{2,})", " ", t)    # «m3» و «a17» یک‌تکه می‌مانند    # «m2pro»، «iphone15» → جدا
    t = re.sub(r"(\d+)(?:th|nd|rd|st)\b", r"\1", t)
    return " ".join(t.split())


_items: list | None = None
_index: list | None = None


def items() -> list:
    global _items
    if _items is None:
        out = []
        for cat, fn in FILES.items():
            try:
                rows = json.loads((DIR / fn).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for r in rows if isinstance(rows, list) else []:
                if isinstance(r, dict) and r.get("name"):
                    r = dict(r)
                    r["category"] = r.get("category") or cat
                    out.append(r)
        _items = out
    return _items


def _names(r: dict) -> list[str]:
    cat = r["category"]
    ns = [r.get("name", ""), r.get("name_fa", "")] + list(r.get("aliases") or [])
    k = r.get("key") or ""
    if cat == "iphone" and k:
        ns.append("iphone " + ("" if k == "iphone" else k))
    elif cat in ("ipad", "mac", "watch", "airpods") and k:
        ns.append(k if k.split()[0] in ("ipad", "macbook", "imac", "mac", "watch", "airpods") else f"{cat} {k}")
    return [n for n in ns if n]


def index() -> list:
    """[(توکن‌های نام, رکورد)]، بلندترین اول."""
    global _index
    if _index is None:
        idx, seen = [], set()
        for r in items():
            for n in _names(r):
                toks = tuple(canon(n).split())
                if len(toks) < 2 or (toks, r["name"]) in seen:      # «pro» تنها یا «air» تنها نامی نیست
                    continue
                if set(toks) <= _FAMILY:
                    continue        # «آیپد ایر» خالی نام نسل اول نیست؛ تازه‌ترین را _loose پیدا می‌کند
                seen.add((toks, r["name"]))
                idx.append((toks, r))
        idx.sort(key=lambda x: -len(x[0]))
        _index = idx
    return _index


def _at(toks: list, sub: tuple) -> int:
    n = len(sub)
    for i in range(len(toks) - n + 1):
        if tuple(toks[i:i + n]) == sub:
            return i
    return -1


def find(text: str, limit: int = 3) -> list[dict]:
    """مدل‌های نام‌برده در جمله، به ترتیب آمدن. نام بلندتر برنده است («۱۵ پرو مکس» نه «۱۵ پرو»)."""
    toks = canon(text).split()
    used, hits = set(), []
    for sub, r in index():
        i = _at(toks, sub)
        if i < 0 or any(j in used for j in range(i, i + len(sub))):
            continue
        # «iphone 15» نباید داخل «iphone 15 pro» دوباره بخورد؛ عدد بعدی هم نام دیگری است («air m2» ≠ «air m2 15»؟ مجاز)
        nxt = toks[i + len(sub)] if i + len(sub) < len(toks) else ""
        if sub[-1].isdigit() and nxt in ("pro", "max", "plus", "mini", "e"):
            continue
        if _MODELISH.match(nxt) and not _MODELISH.match(sub[-1]):   # «ipad air» در «ipad air m4»: نام ادامه دارد
            continue
        if any(h is r for _, h in hits):
            continue
        used.update(range(i, i + len(sub)))
        hits.append((i, r))
    hits.sort(key=lambda x: x[0])
    out = [r for _, r in hits]
    if not out:
        out = _loose(toks)
    # «فرق ایفون ۷ با ۸»، «۱۵ پرو یا ۱۶ پرو»: طرف دوم نام دسته را تکرار نمی‌کند
    if out and len(out) < limit:
        cat = out[0]["category"]
        # نام خانواده‌ی طرف اول: «macbook air»، «ipad air»، «iphone»، «watch series»
        fam = []
        for t in canon(out[0]["name"]).split():
            if t not in _FAMILY and t != "series":
                break
            fam.append(t)
        word = " ".join(fam) if fam else None
        for i, tk in enumerate(toks):
            if tk not in ("با", "یا", "و", "vs", "or") or i + 1 >= len(toks):
                continue
            rest = toks[i + 1:i + 6]
            if rest[0] in _CAT_WORDS:                 # «… با ایپد پرو m4»: نام کامل طرف دوم
                more = find(" ".join(rest), 1)
            elif word:                               # «… با ۸»: نام دسته‌ی طرف اول
                more = [r for r in find(word + " " + " ".join(rest[:3]), 1) if r["category"] == cat]
            else:
                more = []
            for r in more:
                if r not in out:
                    out.append(r)
    return out[:limit]


_MODELISH = re.compile(r"^(?:m\d+|a\d+|\d+(?:\.\d+)?|pro|max|plus|mini|ultra|air|se|e|gen|series|inch)$")
_FAMILY = {"apple", "iphone", "ipad", "macbook", "imac", "mac", "watch", "airpods", "pro", "max", "plus", "mini",
           "air", "ultra", "se", "studio"}
_CAT_WORDS = ("iphone", "ipad", "macbook", "imac", "mac", "watch", "airpods")


def _loose(toks: list) -> list[dict]:
    """نام ناقص: «آیپد پرو m4» (بی‌اندازه)، «مک‌بوک ایر m3». مدل‌هایی که همه‌ی کلمه‌های نام مشتری را دارند؛
    تازه‌ترین و کوچک‌تر اول."""
    for i, tk in enumerate(toks):
        if tk not in _CAT_WORDS:
            continue
        vocab = {t for sub, _ in index() for t in sub}
        phrase = [tk]
        for t in toks[i + 1:i + 5]:
            if t not in vocab or t in _CAT_WORDS or t in ("با", "یا", "و", "vs", "or"):
                break
            phrase.append(t)
        if len(phrase) < 2 and tk != "imac":        # «آیفون» یا «آیپد» تنها مدل نیست (می‌پرسیم کدام)؛ «آی‌مک» تنها یعنی تازه‌ترین
            continue
        want = set(phrase)
        exact, cands = [], []
        for sub, r in index():
            if _at(list(sub), tuple(phrase)) >= 0 and r not in exact:     # «ipad pro» پشت سر هم، نه «ipad mini a20 pro»
                exact.append(r)
            elif want <= set(sub) and r not in cands:
                cands.append(r)
        cands = exact or cands
        if cands:
            inch = lambda r: (r.get("display") or {}).get("inch", 0) if isinstance(r.get("display"), dict) else 0
            cands.sort(key=lambda r: (-(r.get("year") or 0), inch(r)))
            return cands[:1]
    return []


def search(query: str, limit: int = 4) -> list[dict]:
    """برای ابزار فروشنده‌ی هوشمند: اول نام دقیق، بعد هر مدلی که همه‌ی کلمه‌های پرسش در نامش هست."""
    got = find(query, limit)
    if got:
        return got
    q = set(canon(query).split()) - {"specs", "مشخصات"}
    if not q:
        return []
    scored = []
    for r in items():
        toks = set(canon(" ".join(_names(r))).split())
        if q <= toks:
            scored.append((r.get("year") or 0, r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:limit]]


def public(r: dict) -> dict:
    """رکورد بی منبع‌ها و نام‌های جایگزین (لینک بیرونی به مشتری نمی‌رود)."""
    return {k: v for k, v in r.items() if k not in ("sources", "aliases") and v not in (None, [], "")}


# ---------- متن جواب ----------

_CAM = [(r"(\d+)\s*MP", r"\1 مگاپیکسل"), (r"ultra[- ]wide", "فوق‌عریض"), (r"telephoto", "تله‌فوتو"),
        (r"\bmain\b", "اصلی"), (r"\bwide\b", "عریض"), (r"\bfront\b", "جلو"), (r"\bdual\b", "دوگانه"),
        (r"\bnone\b", "ندارد")]


def _cam(t: str) -> str:
    t = str(t or "")
    for rx, rep in _CAM:
        t = re.sub(rx, rep, t, flags=re.I)
    return fa(t)


def _gb(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return fa(n)
    return f"{fa(n // 1024)} ترابایت" if n >= 1024 and n % 1024 == 0 else f"{fa(n)} گیگ"


def _list(v, f=str) -> str:
    if isinstance(v, list):
        return "، ".join(f(x) for x in v if x not in (None, ""))
    return f(v) if v not in (None, "") else ""


def _display(d) -> str:
    if not isinstance(d, dict):
        return fa(d) if d else ""
    parts = []
    if d.get("inch"):
        parts.append(f"{fa(d['inch'])} اینچ")
    if d.get("type") and d["type"] != "none":
        parts.append(str(d["type"]))
    if d.get("hz"):
        parts.append(f"{fa(d['hz'])} هرتز")
    return " · ".join(parts)


def _colors(v) -> str:
    out = []
    for c in v or []:
        if isinstance(c, dict):
            out.append(c.get("fa") or c.get("en") or "")
        elif c:
            out.append(str(c))
    return "، ".join(x for x in out if x)


def _support(r: dict) -> str:
    for k, name in (("max_ios", "iOS"), ("max_ipados", "iPadOS"), ("max_macos", "macOS")):
        if k in r:
            v = r.get(k)
            return f"تا {name} {fa(v)}" if v else "آخرین نسخه را می‌گیرد"
    return ""


def card(r: dict, html: bool = True) -> str:
    b = (lambda s: f"<b>{s}</b>") if html else (lambda s: s)
    cat = r.get("category", "")
    lines = [f"{CAT_ICON.get(cat, '🍏')} {b(r.get('name_fa') or r['name'])}  ·  {r['name']}", "━━━━━━━━━━━━━━━"]
    rows = [
        ("📅 سال عرضه", fa(r["year"]) if r.get("year") else ""),
        ("⚙️ تراشه", r.get("chip") or _list(r.get("chips"))),
        ("🧠 رم", _list(r.get("ram_gb"), _gb) if r.get("ram_gb") else ""),
        ("📐 صفحه", _display(r.get("display"))),
        ("📸 دوربین پشت", _cam(r.get("rear_cameras"))),
        ("🤳 دوربین جلو", _cam(r.get("front_camera") or r.get("camera"))),
        ("💾 حافظه", _list(r.get("storage_gb"), _gb)),
        ("🎨 رنگ‌ها", _colors(r.get("colors"))),
        ("📏 اندازه", _list(r.get("sizes"), lambda x: f"{fa(x)} میلی‌متر")),
        ("🔌 درگاه", r.get("port") or _list(r.get("ports"))),
        ("🔐 قفل", {"Face ID": "فیس‌آیدی", "Touch ID": "تاچ‌آیدی", "none": ""}.get(r.get("biometrics"), r.get("biometrics") or "")),
        ("📶 شبکه", r.get("network") or r.get("cellular") or r.get("connectivity") or ""),
        ("💧 ضدآب", r.get("water") or ""),
        ("🔋 باتری", (f"{fa(r['battery_mah'])} میلی‌آمپر" if r.get("battery_mah") else
                     (f"تا {fa(r['battery_hours'])} ساعت" if r.get("battery_hours") else _cam(r.get("battery") or "")))),
        ("⚖️ وزن", f"{fa(r['weight_g'])} گرم" if r.get("weight_g") else
                    (f"{fa(r['weight_kg'])} کیلوگرم" if r.get("weight_kg") else "")),
        ("✏️ قلم", _list(r.get("pencil"))),
        ("🛠 نرم‌افزار", _support(r)),
    ]
    lines += [f"{k}: {v}" for k, v in rows if v]
    feats = [f for f in (r.get("features") or []) if f and f not in ("5G",)]
    if feats:
        lines.append("✨ " + "، ".join(feats[:8]))
    return "\n".join(lines)


def compare(rs: list[dict], html: bool = True) -> str:
    rs = rs[:3]
    b = (lambda s: f"<b>{s}</b>") if html else (lambda s: s)
    sep = "  ·  "
    out = ["⚖️ " + " در برابر ".join(b(r.get("name_fa") or r["name"]) for r in rs), "━━━━━━━━━━━━━━━"]
    fields = [("📅 سال", lambda r: fa(r["year"]) if r.get("year") else "—"),
              ("⚙️ تراشه", lambda r: r.get("chip") or _list(r.get("chips")) or "—"),
              ("🧠 رم", lambda r: _list(r.get("ram_gb"), _gb) or "—"),
              ("📐 صفحه", lambda r: _display(r.get("display")) or "—"),
              ("📸 دوربین", lambda r: _cam(r.get("rear_cameras")) or "—"),
              ("💾 حافظه", lambda r: _list(r.get("storage_gb"), _gb) or "—"),
              ("🔌 درگاه", lambda r: r.get("port") or _list(r.get("ports")) or "—"),
              ("⚖️ وزن", lambda r: (f"{fa(r['weight_g'])} گرم" if r.get("weight_g") else
                                    f"{fa(r['weight_kg'])} کیلوگرم" if r.get("weight_kg") else "—"))]
    for name, f in fields:
        vals = [f(r) for r in rs]
        if any(v != "—" for v in vals):
            out.append(f"{name}: " + sep.join(vals))
    return "\n".join(out)


# ---------- آیا پیام سؤال مشخصات است؟ ----------

SPEC_WORDS = re.compile(
    r"مشخصات|سخت ?افزار|تراشه|چیپ|پردازنده|\bرم\b|رمش|حافظه|صفحه|نمایشگر|اینچ|دوربین|باتری|وزن|رنگ|"
    r"چه سالی|کی اومد|کی اومده|سال ساخت|فرق|تفاوت|مقایسه|بهتره|قوی ?تر|پورت|درگاه|شارژ|ضد ?اب|ای ?او ?اس|ios|"
    r"اپدیت|آپدیت|چند گیگ|چند ترا|specs?|chip|ram|camera|battery|colou?rs?", re.I)
PRICE_WORDS = re.compile(r"قیمت|چند[هه]?\b|چنده|چقدر|تومن|تومان|موجود|دارید|دارین|بخرم|خرید|قسط|اقساط", re.I)


# «رمش چنده»، «باتریش چقدره»، «چند اینچه»: عدد مشخصه را می‌پرسد، نه قیمت
SPEC_ASK = re.compile(r"(?:\bرم\S*|باتری\S*|حافظ\S*|وزن\S*|صفحه\S*|اینچ\S*|دوربین\S*|مگاپیکسل\S*|هرتز\S*)\s*"
                      r"(?:چند|چنده|چقدر\S*|چقد\S*)|چند\s*(?:اینچ|گرم|هرتز|مگاپیکسل|گیگ رم)\S*")


def spec_question(text: str) -> list[dict]:
    """مدل‌های یک سؤال مشخصات (نه قیمت و موجودی)، یا [] اگر سؤال مشخصات نیست."""
    t = brain.norm(text or "")
    if not (SPEC_ASK.search(t) or (SPEC_WORDS.search(t) and not PRICE_WORDS.search(t))):
        return []
    return find(text)
