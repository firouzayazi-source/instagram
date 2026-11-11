"""دستیار محتوا: ایده‌ی ریلز با قلاب، صحنه‌ها، کپشن و کلمه‌ی کامنت، از روی آمار واقعی پیج و لحن ثبت‌شده.

فقط پیش‌نویس می‌دهد؛ چیزی منتشر نمی‌کند. قیمت، تخفیف، موجودی و هر حقیقت تجاری که در اطلاعات کسب‌وکار
نیامده نباید ساخته شود. هزینه در همان لاگ و بودجه‌ی ماهانه‌ی هوش مصنوعی حساب می‌شود.
"""
import json
from pathlib import Path

from . import ai, config, insights

SCHEMA = {
    "type": "object",
    "properties": {"ideas": {"type": "array", "items": {
        "type": "object",
        "properties": {k: {"type": "string"} for k in ("title", "why", "hook", "caption", "keyword", "dm_text", "public_reply")}
        | {"scenes": {"type": "array", "items": {"type": "string"}}},
        "required": ["title", "why", "hook", "scenes", "caption", "keyword", "dm_text", "public_reply"],
        "additionalProperties": False}}},
    "required": ["ideas"],
    "additionalProperties": False,
}
HINT = ('\n\nخروجی را فقط به صورت یک شیء JSON بده، بدون متن دیگر: {"ideas": [{"title": "", "why": "", "hook": "", '
        '"scenes": ["", ""], "caption": "", "keyword": "", "dm_text": "", "public_reply": ""}]}')
RULES = """تو برنامه‌ریز محتوای پیج اینستاگرام «استوک لند» هستی: فروشگاه آیفون (خرید، فروش، معاوضه، اقساط) که آموزش و ترفند آیفون هم منتشر می‌کند.
سه ایده‌ی ریلز بده. برای هر ایده:
- title: موضوع در یک خط.
- why: یک جمله که چرا با توجه به آمار همین پیج احتمال دیده شدن دارد (فقط به عددهایی که پایین داده شده استناد کن).
- hook: متنی که در ۲ ثانیه‌ی اول روی تصویر می‌آید؛ کوتاه، درباره‌ی یک مشکل یا نتیجه‌ی مشخص.
- scenes: ۳ تا ۵ صحنه‌ی کوتاه، هر کدام یک کار مشخص روی گوشی یا جلوی دوربین.
- caption: کپشن محاوره‌ای و کوتاه که از بیننده می‌خواهد کلمه‌ی keyword را کامنت کند؛ حداکثر ۴ هشتگ.
- keyword: یک کلمه‌ی فارسی ساده برای کامنت.
- dm_text: متن دایرکتی که به کامنت‌گذار می‌رود؛ بدون لینک (لینک را سیستم اضافه می‌کند).
- public_reply: جواب کوتاه زیر کامنت.
قاعده‌ها:
- فارسی محاوره‌ای و محترمانه، بدون اغراق و بدون وعده.
- هیچ قیمت، تخفیف، موجودی، گارانتی یا شرطی که در «اطلاعات کسب‌وکار» نیامده ننویس.
- ترفند آیفون فقط اگر از درستی‌اش مطمئنی؛ مسیر تنظیمات را دقیق بنویس. اگر مطمئن نیستی آن ایده را نده.
- قرعه‌کشی، «فالو کن و برنده شو» و محتوای احساسی بی‌ربط به آیفون پیشنهاد نده.
- اگر «لحن پیج» داده شده، کپشن و متن‌ها را با همان لحن بنویس."""


def _voice() -> str:
    p = Path(config.ROOT) / "docs" / "voice" / "voice.md"
    try:
        return p.read_text(encoding="utf-8")[:3000]
    except OSError:
        return ""


def bot_link() -> str:
    try:
        u = json.loads((Path(config.TG_DATA_DIR) / "status.json").read_text(encoding="utf-8")).get("username", "")
    except (OSError, ValueError):
        u = ""
    return f"https://t.me/{u}?start=insta" if u else ""


def page_facts(c) -> str:
    """آمار واقعی ۴۵ روز اخیر از جدول تحلیل محتوا؛ خالی اگر هنوز آماری ذخیره نشده."""
    s = insights.summary(c, 45)
    if not s["media"]:
        return ""
    line = lambda m: (f"- «{m['caption'] or '—'}» · ریچ {m.get('reach') or 0} · ذخیره {m.get('saved') or 0} · اشتراک "  # noqa: E731
                      f"{m.get('shares') or 0} · کامنت {m.get('comments') or 0}"
                      + (f" · رد شدن در ۳ ثانیه‌ی اول {m['reels_skip_rate']}٪" if m.get("reels_skip_rate") is not None else ""))
    weak = sorted([m for m in s["media"] if m["kind"] == "REEL"], key=lambda m: m.get("reach") or 0)[:4]
    return "\n".join(["پربازدیدترین‌های ۴۵ روز اخیر:", *map(line, s["top"]),
                      "بیشترین ذخیره و اشتراک به نسبت دیده‌شدن:", *map(line, s["valuable"]),
                      "ضعیف‌ترین ریلزها:", *map(line, weak)])


async def ideas(c, topic: str = "") -> dict:
    s = ai.settings(c)
    if s["monthly_budget_usd"] and ai.month_cost(c) >= s["monthly_budget_usd"]:
        raise RuntimeError("بودجه‌ی ماهانه‌ی هوش مصنوعی تمام شده است")
    facts = page_facts(c)
    parts = [RULES]
    if s.get("business_info"):
        parts.append("اطلاعات کسب‌وکار:\n" + str(s["business_info"])[:3000])
    if _voice():
        parts.append("لحن پیج:\n" + _voice())
    parts.append("آمار پیج:\n" + (facts or "هنوز آماری ذخیره نشده؛ فقط ایده‌های «حل یک مشکل مشخص کاربر آیفون در ایران» بده."))
    system = [{"type": "text", "text": "\n\n".join(parts)}]
    messages = [{"role": "user", "content": (f"موضوع یا خواسته‌ی من: {topic.strip()[:500]}" if topic.strip()
                                             else "سه ایده برای ریلزهای این هفته بده.")}]
    attempts = [(s["provider"], s["model"])] + ([(s["fallback_provider"], s["fallback_model"])] if s["fallback_provider"] else [])
    errors = []
    for prov, mdl in attempts:
        if not ai._usable(prov):
            errors.append(f"{ai.PROVIDERS[prov]['label']}: کلید تنظیم نشده")
            continue
        try:
            raw, usage, _ = await ai.get_client(prov).complete(mdl, system, messages, s["effort"], schema=SCHEMA, hint=HINT)
            out = ai.parse_output(raw)
            items = [x for x in out.get("ideas") or [] if isinstance(x, dict) and x.get("title")][:5]
            if not items:
                raise ValueError("ایده‌ای برنگشت")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{ai.PROVIDERS[prov]['label']}: {str(e)[:200]}")
            continue
        model = ai._label(prov, mdl)
        cost = ai.cost_usd(model, usage, s)
        ai._log(c, ai.Decision("ignore", usage=usage), event_id=None, channel="content", user_id="owner", username=None,
                text=topic[:200], model=model, cost=cost, is_test=True)
        link = bot_link()
        for x in items:
            x["scenes"] = [str(v) for v in (x.get("scenes") or [])][:6]
            x["dm_text"] = (str(x.get("dm_text") or "").strip() + (f"\n{link}" if link else "")).strip()
        return {"ideas": items, "model": model, "cost": cost, "has_stats": bool(facts)}
    raise RuntimeError(" | ".join(errors) or "سرویس هوش مصنوعی در دسترس نیست")
