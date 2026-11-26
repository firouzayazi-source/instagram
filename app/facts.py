"""هسته‌ی حقیقت: هر واقعیتی که مغز مرکزی به مشتری می‌گوید از اینجا می‌آید، با منبعش (۵ آذر ۱۴۰۵).

منبع‌ها همان‌هایی‌اند که صاحب فروشگاه نگه می‌دارد، نه حافظه‌ی مدل:
- فهرست کالا، قیمت و موجودی زنده‌ی سایت (catalog.json ربات تلگرام، هر ۱۰ دقیقه از stland.ir)
- شرایط اقساط و فرمولش (settings.json ربات تلگرام، /installment؛ پیش‌فرض‌های تأییدشده‌ی ۹ و ۱۵ آبان)
- متن بخش‌ها (آدرس، تماس، شبکه‌ها، سایت، اقساط) و ساعت کاری ربات تلگرام
- جواب‌های آماده‌ی دانش مشترک (faq.json) و «اطلاعات کسب‌وکار» و «پرسش‌های رایج» پنل

هر تابع خروجی کوتاه و قابل‌وارسی می‌دهد؛ مغز فقط عددها و نشانی‌هایی را می‌تواند بگوید که از همین‌جا آمده‌اند
(app/agent.py پیش از ارسال وارسی می‌کند).
"""
import json
import time

from . import brain_engine, db, knowledge

catalog = brain_engine.catalog
brain = brain_engine.brain

# همان پیش‌فرض ربات تلگرام (tgbot/bot.py DEFAULT_INSTALLMENT): پیش‌پرداخت یک‌سوم، سود ۶٪ ماهانه به روز، تا ۱۰ ماه،
# یک‌دهم مانده (حداکثر ۵ میلیون) هزینه‌ی اقساط، سقف چک ۱۰۰ و طلا ۲۰۰ میلیون (تأیید صاحب فروشگاه ۹ و ۱۵ آبان)
DEFAULT_INSTALLMENT = {"down": 100 / 3, "rate": 6, "max_months": 10, "fee_pct": 10, "fee_cap": 5_000_000,
                       "cap_cheque": 100_000_000, "cap_gold": 200_000_000}
CATALOG_FRESH = 6 * 3600
MAX_ITEMS = 6

TOPICS = {
    "hours": "ساعت کاری و باز یا بسته بودن الان",
    "address": "آدرس و مسیر فروشگاه",
    "contact": "شماره تماس و پشتیبانی",
    "social": "اینستاگرام، کانال و شبکه‌های اجتماعی",
    "site": "سایت فروشگاه",
    "installment_terms": "شرایط کلی اقساط (چک، طلا، پیش‌پرداخت)",
    "apple_id": "خرید اپل‌آیدی",
    "policy": "گارانتی، ارسال، مرجوعی، معاوضه، رجیستری و هر سیاست دیگر",
}
_SECTION = {"address": "5", "contact": "4", "social": "1", "site": "2", "installment_terms": "3"}


def installment_cfg() -> dict | None:
    """شرایط اقساط فعلی؛ None یعنی صاحب فروشگاه اقساط را خاموش کرده (/installment off)."""
    st = brain_engine._load_json("settings.json", {})
    v = st.get("installment") if isinstance(st, dict) else None
    if v is False:
        return None
    return v if isinstance(v, dict) and "rate" in v else DEFAULT_INSTALLMENT


def catalog_state() -> dict:
    ready = brain_engine._catalog_ready()
    age = time.time() - (catalog.updated or 0) if ready else None
    return {"ready": ready, "fresh": bool(ready and age is not None and age < CATALOG_FRESH),
            "age_hours": round(age / 3600, 1) if age is not None else None}


def _item(x: dict) -> dict:
    a = x.get("attrs") or {}
    return {"id": str(x.get("id") or ""), "name": x["name"], "price_toman": int(x.get("price") or 0),
            "price_text": catalog.fmt_price(x["price"]) if x.get("price") else "قیمت در سایت ثبت نشده",
            "in_stock": bool(x.get("stock")), "used": bool(x.get("used")),
            "storage": a.get("حافظه", ""), "color": a.get("رنگ", ""), "battery": a.get("سلامت باتری", ""),
            "condition": a.get("وضعیت", ""), "last_one": x.get("left") == 1, "link": brain_engine._short_link(x)}


def search_products(query: str) -> dict:
    """جستجوی زنده در فهرست سایت با همان فهم ربات تلگرام («۱۳ پرو ۲۵۶ کارکرده زیر ۷۰ میلیون»)."""
    st = catalog_state()
    if not st["ready"]:
        return {"ok": False, "error": "فهرست کالای سایت در دسترس نیست؛ قیمت و موجودی را نگو و به همکار بسپار"}
    q = catalog.parse(query or "")
    if not q:
        return {"ok": True, "fresh": st["fresh"], "items": [], "note": "عبارت جستجوی کالا نبود؛ مدل یا نوع کالا را بپرس"}
    res = catalog.search(q)
    near = False
    if not res and q.get("model"):
        res, near = catalog.search(q, family=True), True
    out = {"ok": True, "fresh": st["fresh"], "what": catalog.describe(q) or query,
           "items": [_item(x) for x in res[:MAX_ITEMS]], "total": len(res), "exact": not near}
    if near and res:
        out["note"] = "دقیقاً همین موجود نیست؛ این‌ها نزدیک‌ترین‌های موجودند"
    if not res:
        out["note"] = "موجود نیست؛ قیمتی نگو، بگو موجود نیست و گزینه‌ی دیگر یا «خبرم کن» پیشنهاد بده"
    if not st["fresh"]:
        out["warning"] = f"فهرست {st['age_hours']} ساعت است به‌روز نشده؛ بگو قیمت نهایی را همکار تأیید می‌کند"
    return out


def product(pid: str) -> dict | None:
    if not pid or not brain_engine._catalog_ready():
        return None
    for x in catalog.items:
        if str(x.get("id") or "") == str(pid):
            return x
    return None


def installment_quote(product_id: str = "", price_toman: int = 0) -> dict:
    """قسط‌ها با فرمول خود فروشگاه (catalog.installments)، برای یک کالا یا یک مبلغ."""
    cfg = installment_cfg()
    if not cfg:
        return {"ok": False, "error": "اقساط فعلاً فعال نیست؛ قول اقساط نده"}
    x = product(product_id) if product_id else None
    price = int((x or {}).get("price") or price_toman or 0)
    if price <= 0:
        return {"ok": False, "error": "قیمت معلوم نیست؛ اول کالا را با search_products پیدا کن"}
    rows = catalog.installments(price, cfg)
    if not rows:
        return {"ok": False, "error": "محاسبه نشد"}
    rem = price - rows[0][2]
    out = {"ok": True, "name": (x or {}).get("name", ""), "cash_price": price,
           "down_payment_min": rows[0][2], "monthly_rate_percent": cfg["rate"], "max_months": cfg["max_months"],
           "plans": [{"months": m, "monthly": monthly, "total": total} for m, _, _, _, monthly, total in rows],
           "guarantee": "با چک یا طلا",
           "note": "قیمت اقساطی کمی با نقدی فرق دارد که در همین قسط‌ها حساب شده؛ مبلغ این تفاوت را جدا نگو"}
    cap_c, cap_g = cfg.get("cap_cheque"), cfg.get("cap_gold")
    if cap_c and cap_g:
        out["caps"] = {"cheque": cap_c, "gold": cap_g}
        if rem > cap_g:
            out["warning"] = "مانده از سقف اقساط بیشتر است؛ پیش‌پرداخت بیشتر لازم است، جزئیات را همکار می‌گوید"
    return out


def _intent_answer(question: str) -> tuple[str, str] | None:
    its = brain_engine.intents()
    if not its or not (question or "").strip():
        return None
    it, sc = brain.match(question, its)
    if it is None or sc < 1.0:
        return None
    raw = brain.pick_variant(it.get("answer", "")) if it.get("answer") else ""
    if not raw.strip():
        return None
    try:
        raw = brain.fill(raw, name="", product="", shop=brain_engine.SHOP_NAME, status="", hours="")
    except Exception:  # noqa: BLE001
        pass
    return it.get("id", ""), brain_engine._plain(raw)


def store_info(topic: str, question: str = "") -> dict:
    """یک واقعیت فروشگاه، از منبع خودش. چیزی که نیست «نیست» برمی‌گردد تا مغز حدس نزند."""
    topic = topic if topic in TOPICS else "policy"
    out: dict = {"ok": True, "topic": topic, "facts": []}
    if topic == "hours":
        h = brain_engine._hours_text()
        o = brain_engine.open_at(time.time())
        if h:
            out["facts"].append(h)
        if o is not None:
            out["facts"].append("الان باز است" if o else "الان بسته است")
    elif topic == "apple_id":
        link = brain_engine.appleid_link()
        if link:
            out["facts"].append(f"خرید اپل‌آیدی با ربات جدای فروشگاه: {link[1]}")
    elif topic in _SECTION:
        t = brain_engine._section(_SECTION[topic])
        if t:
            out["facts"].append(t)
    if topic in ("policy", "installment_terms", "contact") or not out["facts"]:
        hit = _intent_answer(question or TOPICS[topic])
        if hit:
            out["facts"].append(hit[1])
            out["source_intent"] = hit[0]
    if topic in ("policy", "other") or not out["facts"]:
        with db.connect() as c:
            s = json.loads(db.kv_get(c, "ai_settings") or "{}")
            info = (s.get("business_info") or "").strip()
            ids = knowledge.matching_faq_ids(c, question or "") if question else []
            faqs = [dict(r) for r in c.execute(
                f"SELECT question, answer FROM faq WHERE id IN ({','.join('?' * len(ids))})", ids)] if ids else []
        if info:
            out["facts"].append("اطلاعات کسب‌وکار: " + info[:1500])
        for f in faqs[:3]:
            out["facts"].append(f"{f['question']}: {f['answer']}")
    if not out["facts"]:
        out = {"ok": False, "topic": topic, "error": "این اطلاعات ثبت نشده؛ حدس نزن و به همکار بسپار"}
    return out


def health() -> list[str]:
    """چیزهایی که اگر خراب باشند مغز داده‌ی ناقص دارد (برای پنل و گزارش)."""
    out = []
    st = catalog_state()
    if not st["ready"]:
        out.append("فهرست کالای سایت در دسترس نیست")
    elif not st["fresh"]:
        out.append(f"فهرست کالا {st['age_hours']} ساعت است به‌روز نشده")
    if not brain_engine.intents():
        out.append("دانش مشترک ربات تلگرام پیدا نشد")
    for key, name in (("5", "آدرس"), ("4", "تماس"), ("3", "اقساط")):
        if not brain_engine._section(key):
            out.append(f"متن بخش «{name}» خالی است")
    if not brain_engine._hours_text():
        out.append("ساعت کاری تعریف نشده")
    return out
