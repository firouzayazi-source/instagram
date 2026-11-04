"""حافظه‌ی کوتاه گفتگو: آخرین مدل و بودجه‌ای که هر مشتری گفته.

«۱۲۰ تومن دارم» و چند پیام بعد «دوربینش خوب باشه» — ربات بودجه را یادش است و دوباره نمی‌پرسد؛
«۱۳ پرو مکس چنده؟» و بعد «ثبت سفارش» — سفارش برای همان مدل شروع می‌شود. بعد از MAX_AGE فراموش می‌شود.
"""
import re
import time

from . import brain_engine

MAX_AGE = 6 * 3600
_BUDGET_WORD = re.compile(r"بودجه|بودجم|دستمه|دارم|پول|تا\s*\d|حداکثر|نهایتا|زیر\s*\d")
_AMOUNT = re.compile(r"(?<![\d.])(\d{2,3}(?:\.\d)?|[1-9](?:\.\d)?)\s*(میلیون|میلیونی|تومن|تومان|م|ملیون)?(?![\d])")


def budget_of(text: str) -> int:
    """«بودجه‌ام ۱۵۰ میلیونه»، «۱۲۰ تومن دارم»، «تا ۸۰» → تومان. عدد بی‌واحد بازار یعنی میلیون. ۰ اگر نبود."""
    n = brain_engine.brain.norm(text or "").replace("٫", ".")
    if not _BUDGET_WORD.search(n):
        return 0
    for m in _AMOUNT.finditer(n):
        v = float(m.group(1))
        if m.group(2) or 20 <= v <= 900:
            return int(v * 1_000_000) if v < 1000 else 0
    return 0


def remember(c, uid: str, text: str) -> None:
    """مدل و بودجه‌ی این پیام (اگر داشت) جای قبلی‌ها را می‌گیرد؛ بقیه دست نمی‌خورد."""
    t = text or ""
    product = ""
    if brain_engine._catalog_ready():   # همان فهم فهرست کالا: «۱۳ ۱۲۸» آیفون ۱۳ است، نه ۱۲
        model = brain_engine.catalog.parse(t).get("model") or ""
        product = brain_engine.catalog.model_name(model) if model else ""
    budget = budget_of(t)
    if not budget and brain_engine._catalog_ready():
        budget = int(brain_engine.catalog.parse(t).get("max") or 0)
    if not product and not budget:
        return
    old = recall(c, uid, max_age=MAX_AGE)
    c.execute("INSERT INTO conv_memo(user_id,product,budget,updated_at) VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE "
              "SET product=excluded.product, budget=excluded.budget, updated_at=excluded.updated_at",
              (uid, product or old.get("product", ""), budget or old.get("budget", 0), time.time()))


def recall(c, uid: str, max_age: float = MAX_AGE) -> dict:
    r = c.execute("SELECT product, budget, updated_at FROM conv_memo WHERE user_id=?", (uid,)).fetchone()
    if not r or time.time() - r["updated_at"] > max_age:
        return {}
    return {"product": r["product"], "budget": r["budget"]}


def note(m: dict) -> str:
    """برای پرامپت هوش مصنوعی."""
    bits = []
    if m.get("product"):
        bits.append(f"دنبال {m['product']} بود")
    if m.get("budget"):
        bits.append(f"بودجه‌اش حدود {brain_engine.catalog.fa(m['budget'] // 1_000_000)} میلیون تومان است")
    return ("از پیام‌های قبلی همین مشتری: " + " و ".join(bits) + ". دوباره نپرس، مگر چیز تازه‌ای گفته باشد.") if bits else ""
