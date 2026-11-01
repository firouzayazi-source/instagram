"""همگام‌سازی محصول، قیمت و موجودی از فروشگاه ووکامرس (وردپرس).

اول Store API عمومی ووکامرس (بدون کلید، همان داده‌ای که هر بازدیدکننده می‌بیند)؛ اگر بسته بود و
WC_CONSUMER_KEY / WC_CONSUMER_SECRET در .env بود، REST API نسخه‌ی ۳ با کلید فقط‌خواندنی.
محصولات همگام‌شده با source='site' ذخیره می‌شوند و هر بار کامل جایگزین می‌شوند؛ محصولات دستی دست نمی‌خورند.
"""
import asyncio
import html
import ipaddress
import json
import re
import socket
import time
from urllib.parse import urlparse

import httpx

from . import config, db
from .normalize import normalize

DEFAULTS = {
    "url": "",
    "enabled": False,
    "interval_hours": 3,
    "currency": "auto",      # auto | IRT (تومان) | IRR (ریال)
    "last_at": 0,
    "last_count": 0,
    "last_error": "",
    "last_api": "",
}
MAX_PAGES = 40
MAX_VARIATIONS = 3000
_TAG = re.compile(r"<[^>]+>")
# ضریب تبدیل به تومان
_TO_TOMAN = {"IRT": 1, "IRR": 0.1, "IRHT": 1000, "IRHR": 100}


# ---------- تنظیمات ----------

def get_settings(c) -> dict:
    saved = json.loads(db.kv_get(c, "site_sync") or "{}")
    return {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS}}


def _store(c, s: dict) -> None:
    db.kv_set(c, "site_sync", json.dumps(s, ensure_ascii=False))


def save_settings(c, patch: dict) -> dict:
    s = get_settings(c)
    for k in ("url", "enabled", "interval_hours", "currency"):
        if k not in patch:
            continue
        v = patch[k]
        if k == "url":
            v = (v or "").strip().rstrip("/")
            if v:
                check_url(v)
        if k == "enabled":
            v = bool(v)
        if k == "interval_hours":
            v = min(48, max(1, int(v)))
        if k == "currency" and v not in ("auto", "IRT", "IRR"):
            raise ValueError("واحد پول باید auto، IRT یا IRR باشد")
        s[k] = v
    if s["enabled"] and not s["url"]:
        raise ValueError("اول آدرس سایت را وارد کنید")
    _store(c, s)
    return s


def check_url(url: str) -> None:
    """فقط سایت عمومی؛ آدرس داخلی یا محلی سرور پذیرفته نمی‌شود."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("آدرس سایت باید با https:// شروع شود")
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError(f"دامنه‌ی {u.hostname} پیدا نشد")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValueError("آدرس سایت به یک نشانی داخلی می‌رسد و پذیرفته نمی‌شود")


# ---------- تبدیل داده ----------

def _text(v) -> str:
    return " ".join(html.unescape(_TAG.sub(" ", str(v or ""))).split())


def _toman(amount: float | None, currency: str) -> int | None:
    if amount is None or amount <= 0:
        return None
    return int(round(amount * _TO_TOMAN.get(currency.upper(), 1)))


# کلیدهای رایج در توضیح کوتاه محصول، مثل «حافظه ۲۵۶ گیگابایت · رنگ Midnight · وضعیت کارکرده»
_DESC_KEYS = ("سلامت باتری", "پارت نامبر", "حافظه", "ظرفیت", "رنگ", "وضعیت", "رجیستر", "ریجستر", "گارانتی")
_LI = re.compile(r"<li[^>]*>(.*?)</li>", re.S | re.I)


def desc_attrs(short_desc: str, desc: str) -> list[tuple[str, str]]:
    """ویژگی‌ها از متن محصول: بخش‌های جداشده با «·» در توضیح کوتاه، و سطرهای «کلید: مقدار» در فهرست توضیح."""
    out = []
    for seg in re.split(r"\s*[·•|]\s*", _text(short_desc)):
        key = next((k for k in _DESC_KEYS if seg.startswith(k)), None)
        if key:
            out.append((key, seg[len(key):].strip(" :：")))
        elif ":" in seg:
            k, v = seg.split(":", 1)
            out.append((k.strip(), v.strip()))
    for li in _LI.findall(desc or "")[:12]:
        t = _text(li)
        if ":" in t:
            k, v = t.split(":", 1)
            if len(k) <= 30:
                out.append((k.strip(), v.strip()))
    return out


def _store_attrs(p: dict) -> list[tuple[str, str]]:
    return [(a.get("name", ""), "، ".join(t.get("name", "") for t in a.get("terms") or []))
            for a in p.get("attributes") or [] if not a.get("has_variations")]


_FA_EN = {"آیفون": "iphone", "ایفون": "iphone", "پرو": "pro", "مکس": "max", "مینی": "mini", "پلاس": "plus",
          "اپل": "apple", "واچ": "watch", "سری": "series", "ایرپاد": "airpods", "ایرپادز": "airpods",
          "آیپد": "ipad", "ایپد": "ipad", "مک": "mac", "بوک": "book", "اولترا": "ultra", "ایر": "air"}


def _tokens(text: str) -> set:
    return {_FA_EN.get(w, w) for w in re.findall(r"[\w]+", normalize(text).lower())}


def _classify(attrs: list[tuple[str, str]], extra: str) -> dict:
    """ویژگی‌ها را به حافظه، رنگ و وضعیت نگاشت می‌کند؛ بقیه در توضیح (هر کلید یک بار)."""
    out = {"storage": "", "color": "", "condition": "", "notes": []}
    seen = set()
    for name, value in attrs:
        n, v = normalize(name), _text(value)
        if not v:
            continue
        if any(w in n for w in ("حافظه", "ظرفیت", "storage", "memory", "capacity", "gb")):
            out["storage"] = v
        elif any(w in n for w in ("رنگ", "color", "colour")):
            out["color"] = v
        elif any(w in n for w in ("وضعیت", "condition", "نوع کالا", "کیفیت")):
            out["condition"] = out["condition"] or v
        elif any(w in n for w in ("برند", "brand", "مدل", "model")) and _tokens(v) <= _tokens(extra):
            continue   # تکرار نام محصول (مثلاً «مدل: iPhone 11 Pro» برای «آیفون 11 پرو»)
        elif n not in seen:
            seen.add(n)
            out["notes"].append(f"{_text(name)}: {v}")
    hay = normalize(f"{out['condition']} {extra}")
    if any(w in hay for w in ("کارکرده", "دست دوم", "used")):
        out["condition"] = "used"
    elif any(w in hay for w in ("استوک", "stock", "ریفربیش", "refurb", "اوپن باکس", "open box")):
        out["condition"] = "stock"
    else:
        out["condition"] = "new"
    out["notes"] = "، ".join(out["notes"])
    return out


def _row(name, attrs, extra, price, in_stock, url) -> dict:
    return {"name": _text(name)[:200], **_classify(attrs, extra), "price": price, "in_stock": int(bool(in_stock)),
            "url": url or ""}


def _short(base: str, p: dict) -> str:
    """لینک کوتاه وردپرس (‎?p=شناسه) که به صفحه‌ی محصول می‌رود؛ لینک اصلی با نامک فارسی در دایرکت خیلی بلند می‌شود."""
    return f"{base}/?p={p['id']}" if p.get("id") else (p.get("permalink") or "")


# ---------- Store API (عمومی) ----------

def _store_price(p: dict, currency: str) -> int | None:
    pr = p.get("prices") or {}
    raw = pr.get("price") or ""
    if not str(raw).isdigit():
        return None
    cur = (pr.get("currency_code") or "IRT") if currency == "auto" else currency
    return _toman(int(raw) / 10 ** int(pr.get("currency_minor_unit") or 0), cur)


async def _get(http, url, **kw):
    r = await http.get(url, **kw)
    r.raise_for_status()
    return r.json()


async def fetch_store_api(http, base: str, currency: str) -> list[dict]:
    rows, var_jobs = [], []
    for page in range(1, MAX_PAGES + 1):
        items = await _get(http, f"{base}/wp-json/wc/store/v1/products", params={"per_page": 100, "page": page})
        if not isinstance(items, list):
            raise ValueError("پاسخ Store API فهرست محصول نیست")
        for p in items:
            extra = " ".join(x.get("name", "") for x in p.get("categories") or []) + " " + p.get("name", "")
            common = _store_attrs(p) + desc_attrs(p.get("short_description", ""), p.get("description", ""))
            if p.get("type") == "variable" and p.get("variations"):
                for v in p["variations"]:
                    attrs = [(a.get("name", ""), a.get("value", "")) for a in v.get("attributes") or []]
                    var_jobs.append((p, v["id"], attrs + common, extra))
            else:
                rows.append(_row(p.get("name"), common, extra, _store_price(p, currency), p.get("is_in_stock"),
                                 _short(base, p)))
        if len(items) < 100:
            break
    if len(var_jobs) > MAX_VARIATIONS:
        var_jobs = var_jobs[:MAX_VARIATIONS]
    sem = asyncio.Semaphore(5)

    async def one(job):
        parent, vid, attrs, extra = job
        async with sem:
            v = await _get(http, f"{base}/wp-json/wc/store/v1/products/{vid}")
        return _row(parent.get("name"), attrs, extra, _store_price(v, currency), v.get("is_in_stock"),
                    _short(base, parent))
    rows += await asyncio.gather(*(one(j) for j in var_jobs))
    return rows


# ---------- REST v3 (با کلید فقط‌خواندنی) ----------

async def fetch_rest_v3(http, base: str, currency: str) -> list[dict]:
    auth = (config.WC_CONSUMER_KEY, config.WC_CONSUMER_SECRET)
    if currency == "auto":
        currency = (await _get(http, f"{base}/wp-json/wc/v3/data/currencies/current", auth=auth)).get("code") or "IRT"

    def price(x):
        try:
            return _toman(float(x.get("price") or 0), currency)
        except ValueError:
            return None
    rows = []
    for page in range(1, MAX_PAGES + 1):
        items = await _get(http, f"{base}/wp-json/wc/v3/products", auth=auth,
                           params={"per_page": 100, "page": page, "status": "publish"})
        for p in items:
            extra = " ".join(x.get("name", "") for x in p.get("categories") or []) + " " + p.get("name", "")
            common = [(a.get("name", ""), "، ".join(a.get("options") or [])) for a in p.get("attributes") or []
                      if not a.get("variation")] + desc_attrs(p.get("short_description", ""), p.get("description", ""))
            if p.get("type") == "variable":
                vs = await _get(http, f"{base}/wp-json/wc/v3/products/{p['id']}/variations", auth=auth,
                                params={"per_page": 100})
                for v in vs:
                    attrs = [(a.get("name", ""), a.get("option", "")) for a in v.get("attributes") or []]
                    rows.append(_row(p.get("name"), attrs + common, extra, price(v), v.get("stock_status") == "instock",
                                     _short(base, p)))
            else:
                rows.append(_row(p.get("name"), common, extra, price(p), p.get("stock_status") == "instock",
                                 _short(base, p)))
        if len(items) < 100:
            break
    return rows


# ---------- اجرا ----------

async def sync(c, transport=None) -> dict:
    """همه‌ی محصولات سایت را می‌خواند و جایگزین محصولات همگام‌شده‌ی قبلی می‌کند. وضعیت را برمی‌گرداند."""
    s = get_settings(c)
    if not s["url"]:
        raise ValueError("آدرس سایت تنظیم نشده")
    if transport is None:
        check_url(s["url"])
    rows, api, err = None, "", ""
    async with httpx.AsyncClient(timeout=30, transport=transport, follow_redirects=False,
                                 headers={"User-Agent": "igbot-sync/1.0"}) as http:
        try:
            rows, api = await fetch_store_api(http, s["url"], s["currency"]), "store"
        except Exception as e:  # noqa: BLE001
            err = f"Store API: {str(e)[:200]}"
            if config.WC_CONSUMER_KEY and config.WC_CONSUMER_SECRET:
                try:
                    rows, api, err = await fetch_rest_v3(http, s["url"], s["currency"]), "v3", ""
                except Exception as e2:  # noqa: BLE001
                    err += f" | REST v3: {str(e2)[:200]}"
    if rows is not None and not rows:
        rows, err = None, "سایت هیچ محصولی برنگرداند؛ فهرست قبلی نگه داشته شد"
    if rows is not None:
        now = time.time()
        c.execute("DELETE FROM products WHERE source='site'")
        c.executemany(
            "INSERT INTO products(name,storage,color,condition,price,in_stock,notes,enabled,updated_at,source,url) "
            "VALUES (?,?,?,?,?,?,?,1,?, 'site', ?)",
            [(r["name"], r["storage"], r["color"], r["condition"], r["price"], r["in_stock"], r["notes"][:500], now,
              r["url"][:500]) for r in rows])
    s.update(last_at=time.time(), last_error=err, last_api=api or s["last_api"],
             last_count=len(rows) if rows is not None else s["last_count"])
    _store(c, s)
    return s


async def sync_loop(stop: asyncio.Event) -> None:
    """هر ۵ دقیقه نگاه می‌کند؛ اگر زمان همگام‌سازی رسیده بود اجرا می‌کند."""
    while not stop.is_set():
        try:
            with db.connect() as c:
                s = get_settings(c)
                if s["enabled"] and s["url"] and time.time() - s["last_at"] >= s["interval_hours"] * 3600:
                    await sync(c)
        except Exception as e:  # noqa: BLE001
            print("site sync failed:", e)
        try:
            await asyncio.wait_for(stop.wait(), timeout=300)
        except asyncio.TimeoutError:
            pass
