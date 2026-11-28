"""تخمین اولیه‌ی قیمت خرید گوشی کارکرده‌ی مشتری (کارشناسی معاوضه؛ ۷ آذر ۱۴۰۵).

هیچ عددی اینجا از خود ربات نیست: قیمت پایه‌ی هر مدل و حافظه، کسر هر بازه‌ی سلامت باتری و کسر هر وضعیت ظاهری را
صاحب فروشگاه با /tradein در ربات تلگرام وارد می‌کند (در settings.json ذخیره و با بکاپ همراه است). تا جدول کامل
نباشد (قیمت همان مدل، بازه‌های باتری و کسرهای وضعیت)، تخمین None است و ربات مثل قبل فقط اطلاعات را به همکار می‌دهد.
قیمت قطعی همیشه بعد از کارشناسی حضوری است و جواب ربات همین را می‌گوید.

ساختار: {"on": true, "prices": {"13 pro|256": 95000000}, "battery": [[90, 0], [85, 3], [0, 12]],
         "cond": [0, 5, 20], "spread": 5}
"""
import re

STEP = 500_000
_DIG = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def key(model: str, storage) -> str:
    return f"{(model or '').strip().lower()}|{str(storage or '').strip()}"


def battery_of(text) -> int | None:
    m = re.search(r"(?<!\d)(\d{2,3})(?!\d)", str(text or "").translate(_DIG))
    if not m:
        return None
    v = int(m.group(1))
    return v if 40 <= v <= 100 else None


def ready(cfg: dict | None) -> bool:
    return bool(cfg and cfg.get("on", True) and cfg.get("prices") and cfg.get("battery") and
                isinstance(cfg.get("cond"), list) and len(cfg["cond"]) >= 3)


def _battery_pct(cfg: dict, battery: int) -> float | None:
    for lo, pct in sorted(cfg["battery"], key=lambda x: -x[0]):
        if battery >= lo:
            return float(pct)
    return None


def estimate(cfg: dict | None, model: str, storage, battery: int | None, cond: int | None) -> tuple[int, int] | None:
    """(کمینه، بیشینه) به تومان، گرد به ۵۰۰ هزار؛ یا None وقتی داده‌ی صاحب فروشگاه برای این گوشی کامل نیست."""
    if not ready(cfg) or battery is None or cond is None or not 0 <= cond < len(cfg["cond"]):
        return None
    base = (cfg.get("prices") or {}).get(key(model, storage))
    bp = _battery_pct(cfg, battery)
    if not base or bp is None:
        return None
    est = base * (1 - (bp + float(cfg["cond"][cond])) / 100)
    if est <= 0:
        return None
    spread = float(cfg.get("spread", 5))
    hi = int(round(est / STEP) * STEP)
    lo = int((est * (1 - spread / 100)) // STEP * STEP)
    return (min(lo, hi), hi)


def fmt_m(v: int) -> str:
    m = v / 1_000_000
    s = f"{m:.1f}".rstrip("0").rstrip(".")
    return s.translate(str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫")) + " میلیون"


def table_text(cfg: dict | None) -> str:
    cfg = cfg or {}
    out = ["<b>🔄 جدول کارشناسی معاوضه</b>",
           "وضعیت: " + ("🟢 روشن" if cfg.get("on", True) else "⚫️ خاموش") +
           ("" if ready(cfg) else " (ناقص: تا کامل نشود ربات تخمین نمی‌دهد)")]
    prices = cfg.get("prices") or {}
    if prices:
        out.append("\n💰 قیمت پایه (باتری سالم، بدون خط و خش):")
        out += [f"• {k.replace('|', ' ')} گیگ: {fmt_m(v)}" for k, v in sorted(prices.items())]
    else:
        out.append("\n💰 هنوز قیمتی ثبت نشده.")
    if cfg.get("battery"):
        out.append("🔋 کسر باتری: " + "، ".join(f"از {lo}٪: {pct}٪" for lo, pct in sorted(cfg["battery"], key=lambda x: -x[0])))
    if cfg.get("cond"):
        out.append("✨ کسر وضعیت (سالم، خط و خش، شکستگی/تعمیری): " + "، ".join(f"{x}٪" for x in cfg["cond"][:3]))
    out += ["", "<b>دستورها</b>",
            "<code>/tradein 13 pro 256 95</code> قیمت پایه به میلیون",
            "<code>/tradein del 13 pro 256</code> حذف",
            "<code>/tradein battery 90:0 85:3 80:6 0:12</code> کسر هر بازه‌ی باتری",
            "<code>/tradein cond 0 5 20</code> کسر سه وضعیت ظاهری",
            "<code>/tradein spread 5</code> پهنای بازه‌ی تخمین (٪)",
            "<code>/tradein off</code> یا <code>on</code>"]
    return "\n".join(out)


def apply_cmd(cfg: dict | None, args: list[str], model_of) -> tuple[dict, str]:
    """دستور /tradein روی جدول. model_of(متن) ← (کلید مدل، حافظه) یا (None, None). خروجی: (جدول تازه، پیام)."""
    cfg = dict(cfg or {})
    cfg.setdefault("prices", {})
    a = [x.translate(_DIG) for x in args]
    if not a:
        return cfg, ""
    cmd = a[0].lower()
    if cmd in ("on", "off"):
        cfg["on"] = cmd == "on"
        return cfg, "✅ کارشناسی خودکار " + ("روشن شد" if cfg["on"] else "خاموش شد")
    if cmd == "battery":
        tiers = []
        for t in a[1:]:
            m = re.fullmatch(r"(\d{1,3}):(\d{1,2}(?:\.\d+)?)", t)
            if not m:
                return cfg, f"❌ «{t}» درست نیست؛ مثال: 90:0 85:3 0:12"
            tiers.append([int(m.group(1)), float(m.group(2))])
        if not tiers or not any(lo == 0 for lo, _ in tiers):
            return cfg, "❌ یک بازه باید از ۰ شروع شود (مثلاً 0:12) تا هر باتری‌ای کسر داشته باشد"
        cfg["battery"] = sorted(tiers, key=lambda x: -x[0])
        return cfg, "✅ کسر باتری ثبت شد"
    if cmd == "cond":
        try:
            vals = [float(x) for x in a[1:4]]
        except ValueError:
            vals = []
        if len(vals) != 3 or any(not 0 <= v < 100 for v in vals):
            return cfg, "❌ سه عدد درصد لازم است: سالم، خط و خش، شکستگی/تعمیری (مثلاً 0 5 20)"
        cfg["cond"] = vals
        return cfg, "✅ کسر وضعیت ثبت شد"
    if cmd == "spread":
        try:
            v = float(a[1])
        except (IndexError, ValueError):
            return cfg, "❌ یک عدد درصد لازم است (مثلاً 5)"
        cfg["spread"] = max(0.0, min(v, 20.0))
        return cfg, "✅ پهنای بازه ثبت شد"
    delete = cmd == "del"
    rest = a[1:] if delete else a
    price = None
    if not delete:
        try:
            price = float(rest[-1]); rest = rest[:-1]
        except (IndexError, ValueError):
            return cfg, "❌ آخرش قیمت به میلیون بیاید؛ مثال: /tradein 13 pro 256 95"
    model, storage = model_of(" ".join(rest))
    if not model or not storage:
        return cfg, "❌ مدل و حافظه را نفهمیدم؛ مثال: /tradein 13 pro 256 95"
    k = key(model, storage)
    if delete:
        cfg["prices"].pop(k, None)
        return cfg, f"🗑 {k.replace('|', ' ')} حذف شد"
    if not 0 < price < 1000:
        return cfg, "❌ قیمت به میلیون تومان است (مثلاً 95 یعنی ۹۵ میلیون)"
    cfg["prices"][k] = int(price * 1_000_000)
    return cfg, f"✅ {k.replace('|', ' ')} گیگ: {fmt_m(cfg['prices'][k])}"
