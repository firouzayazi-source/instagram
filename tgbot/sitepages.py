"""صفحه‌ها و نوشته‌های سایت استوک لند (وردپرس، REST عمومی wp/v2) برای جواب آفلاین ربات.

به‌جز کالا (catalog.py)، سایت متن‌های دیگری هم دارد: درباره‌ی ما، شرایط گارانتی و مرجوعی، ارسال، اقساط،
راهنماها و مقاله‌ها. این‌ها هر ۱۲ ساعت خوانده و کنار ربات (site_pages.json) نگه داشته می‌شوند؛ وقتی ربات
نیتی برای سؤال پیدا نکرد، اگر یکی از این صفحه‌ها روشن به سؤال می‌خورد، خلاصه‌ی همان بخش و لینکش را می‌فرستد.
فقط متن منتشرشده‌ی عمومی؛ هیچ رمز یا دسترسی‌ای لازم نیست. متن جواب عیناً از خود سایت است (چیزی ساخته نمی‌شود).
"""
import html, json, re, time
import brain

SITE = "https://stland.ir"
KINDS = ("pages", "posts")
SKIP_SLUGS = {"cart", "checkout", "my-account", "shop", "wishlist", "compare", "sample-page", "login", "register"}
MAX_TEXT = 8000

items: list = []          # [{"id","kind","title","link","text"}]
updated = 0.0
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t‌]+")


def _clean(h):
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", h or "")
    t = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</div>", "\n", t)
    t = html.unescape(_TAG.sub(" ", t))
    lines = [_WS.sub(" ", x).strip() for x in t.splitlines()]
    return "\n".join(x for x in lines if x)[:MAX_TEXT]


async def fetch(client):
    out = []
    for kind in KINDS:
        page = 1
        while page <= 5:
            r = await client.get(f"{SITE}/wp-json/wp/v2/{kind}",
                                 params={"per_page": 100, "page": page, "_fields": "id,slug,title,link,content"})
            if r.status_code == 400 and page > 1:
                break
            r.raise_for_status()
            for p in r.json():
                if (p.get("slug") or "") in SKIP_SLUGS:
                    continue
                title = html.unescape(_TAG.sub("", (p.get("title") or {}).get("rendered", ""))).strip()
                text = _clean((p.get("content") or {}).get("rendered", ""))
                if title and len(text) >= 40:
                    out.append({"id": p.get("id"), "kind": kind, "title": title, "link": p.get("link", ""), "text": text})
            if page >= int(r.headers.get("x-wp-totalpages") or 1):
                break
            page += 1
    return out


def set_items(new, path=None):
    global items, updated
    items, updated = new, time.time()
    _index.clear()
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


_index: dict = {}


def _words(text):
    """کلمه‌های محتوایی (ریشه و هم‌معنی)."""
    out = set()
    for t in brain.tokens(text):
        if t in brain.STOPWORDS or len(t) < 2 or t.isdigit():
            continue
        out.add(brain.SYNONYMS.get(t, t))
        s = brain.stem(t)
        if len(s) >= 3:
            out.add(brain.SYNONYMS.get(s, s))
    return out


def _idx(i, x):
    if i not in _index:
        _index[i] = (_words(x["title"]), _words(x["text"]))
    return _index[i]


def search(text, min_cover=0.6):
    """بهترین صفحه برای این سؤال، یا None. خروجی: {"title","link","snippet","score"}.
    شرط: یا کلمه‌ای از عنوان صفحه در سؤال هست و بیشتر کلمه‌های سؤال در متن صفحه، یا تقریباً همه‌ی کلمه‌ها."""
    q = _words(text)
    if not q or not items:
        return None
    best = None
    for i, x in enumerate(items):
        tw, bw = _idx(i, x)
        title_hit = len(q & tw)
        cover = len(q & (bw | tw)) / len(q)
        if cover < min_cover or (not title_hit and (cover < 0.85 or len(q) < 2)):
            continue
        score = title_hit * 2 + cover
        if not best or score > best[0]:
            best = (score, x)
    if not best:
        return None
    x = best[1]
    # کوتاه‌ترین بخش متن که بیشترین کلمه‌ی سؤال را دارد (تا ۲ خط پشت سر هم)
    lines = x["text"].splitlines()
    scored = sorted(((len(q & _words(ln + " " + (lines[k + 1] if k + 1 < len(lines) else ""))), k)
                     for k, ln in enumerate(lines)), reverse=True)
    k = scored[0][1] if scored and scored[0][0] else 0
    snippet = "\n".join(lines[k:k + 2])
    if len(snippet) > 420:
        snippet = snippet[:420].rsplit(" ", 1)[0] + " …"
    return {"title": x["title"], "link": x["link"], "snippet": snippet, "score": best[0]}
