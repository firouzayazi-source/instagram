"""تنظیم ربات با حرف زدن: صاحب پیج در پنل می‌نویسد «شرایط اقساط رو ۶ ماهه کن» یا «به کسی که گارانتی
پرسید بگو ۱۸ ماه» و هوش مصنوعی تغییرهای لازم در دانش مرکزی و تنظیمات را پیشنهاد می‌کند.

هیچ تغییری خودکار اعمال نمی‌شود: پیشنهاد اول در پنل نشان داده می‌شود و فقط با تأیید صاحب پیج،
از همان مسیرهای عادی (با همان اعتبارسنجی) ذخیره می‌شود. فقط تنظیمات فهرست ALLOWED در دسترس است؛
کلید API، رمز و تنظیمات سرویس هوش مصنوعی هرگز.
"""
import json

from . import ai, shared_kb

ALLOWED = {
    "welcome_text": "پیام خوش‌آمد اولین دایرکت (متن)",
    "handoff_message": "پیامی که هنگام سپردن به همکار به مشتری می‌رود (متن)",
    "cta": "راه خرید، مثلاً «خرید آنلاین از سایت یا حضوری» (متن)",
    "order_payment_text": "روش پرداخت سفارش دایرکت، مثلاً شماره‌کارت و نام صاحب حساب (متن)",
    "tone": "لحن: formal | friendly | casual",
    "length": "طول جواب: short | medium",
    "human_pause_minutes": "سکوت ربات بعد از جواب همکار، دقیقه (عدد)",
    "batch_wait_seconds": "انتظار برای پیام‌های پشت‌سرهم، ثانیه (عدد)",
    "dm_quick_replies": "دکمه‌های پاسخ سریع دایرکت (فهرست متن، هر کدام تا ۲۰ نویسه)",
    "sales_mode": "حالت فروشنده (true/false)",
    "upsell": "پیشنهاد لوازم جانبی (true/false)",
    "send_links": "فرستادن لینک محصول (true/false)",
    "ask_contact": "درخواست شماره‌ی تماس (true/false)",
    "showcase_cards": "کارت ویترین محصول (true/false)",
    "order_enabled": "گرفتن سفارش در دایرکت (true/false)",
    "mention_reply_enabled": "تشکر خودکار از منشن (true/false)",
}

SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "ops": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": ["intent_upsert", "intent_delete", "section_set", "setting"]},
                "id": {"type": "string"}, "keys": {"type": "array", "items": {"type": "string"}},
                "examples": {"type": "array", "items": {"type": "string"}}, "answer": {"type": "string"},
                "action": {"type": "string"}, "key": {"type": "string"}, "text": {"type": "string"},
                "value_json": {"type": "string"},
            },
            "required": ["op", "id", "keys", "examples", "answer", "action", "key", "text", "value_json"],
            "additionalProperties": False}},
    },
    "required": ["reply", "ops"],
    "additionalProperties": False,
}
HINT = ('\n\nخروجی فقط یک شیء JSON با کلیدهای reply (متن) و ops (فهرست) باشد؛ هر عضو ops همه‌ی کلیدهای '
        'op, id, keys, examples, answer, action, key, text, value_json را دارد (خالی اگر لازم نیست).')


def _system(s: dict) -> list:
    kb = shared_kb.intents() if shared_kb.ready() else []
    intents = "\n".join(f"- id={x['id']} | کلیدواژه‌ها: {'، '.join(x['keys'][:8])} | کار: {x['action'] or '-'} | "
                        f"جواب: {x['answer'][:300].replace(chr(10), ' ')}" for x in kb[:120])
    sections = "\n".join(f"- key={x['key']} ({x['title']}): {x['text'][:400].replace(chr(10), ' ')}"
                         for x in (shared_kb.sections() if shared_kb.ready() else []))
    settings = "\n".join(f"- {k}: {ALLOWED[k]} · مقدار فعلی: {json.dumps(s.get(k), ensure_ascii=False)}" for k in ALLOWED)
    actions = "\n".join(f"- «{k}»: {v}" for k, v in shared_kb.ACTIONS.items())
    text = f"""تو دستیار تنظیم ربات پاسخ‌گوی فروشگاه موبایل «استوک لند» هستی. صاحب فروشگاه به فارسی می‌گوید چه
چیزی در جواب‌های ربات عوض شود و تو تغییرهای لازم را به شکل ops پیشنهاد می‌دهی. ربات در اینستاگرام و تلگرام
از یک دانش مشترک جواب می‌دهد.

انواع op:
- intent_upsert: افزودن یا ویرایش یک نیت. برای ویرایش، id نیت موجود را بگذار؛ برای نیت تازه id خالی. keys
  کلیدواژه‌ها، examples جمله‌های نمونه‌ی مشتری، answer متن جواب (چند نسخه را با خطی شامل --- جدا کن)، action
  یکی از کارهای مجاز یا خالی. نیت موجود را با همان کلیدواژه‌ها و نمونه‌ها نگه دار و فقط آنچه خواسته شده را عوض کن.
- intent_delete: حذف نیت تازه‌ای که صاحب پیج ساخته (id با p_ شروع می‌شود).
- section_set: متن کامل تازه‌ی یک بخش (key و text). متن قبلی را حفظ کن و فقط بخش خواسته‌شده را عوض کن.
- setting: یکی از تنظیمات مجاز (key) با مقدار تازه به شکل JSON در value_json، مثلاً "\\"friendly\\"" یا "30" یا "true".

قواعد: فقط همان چیزی را عوض کن که خواسته شده. چیزی از خودت نساز (قیمت، شماره‌کارت، آدرس)؛ اگر اطلاعات کم
است، ops خالی بگذار و در reply کوتاه بپرس. reply یک یا دو جمله‌ی فارسی است که می‌گوید چه چیزی عوض می‌شود.

کارهای مجاز نیت:
{actions}

تنظیمات مجاز:
{settings}

بخش‌ها:
{sections or '(در دسترس نیست)'}

نیت‌های فعلی:
{intents or '(در دسترس نیست)'}"""
    return [{"type": "text", "text": text}]


async def propose(c, text: str, history: list | None = None) -> dict:
    """پیشنهاد تغییر؛ خروجی {"reply": str, "ops": [...]}. خطا: ValueError با پیام فارسی."""
    text = (text or "").strip()[:2000]
    if not text:
        raise ValueError("متن خالی است")
    s = ai.settings(c)
    attempts = [(s["provider"], s["model"])] + ([(s["fallback_provider"], s["fallback_model"])] if s["fallback_provider"] else [])
    msgs = [{"role": m["role"], "content": str(m["content"])[:2000]} for m in (history or [])[-6:]
            if m.get("role") in ("user", "assistant")] + [{"role": "user", "content": text}]
    errors = []
    for prov, mdl in attempts:
        if not ai._usable(prov):
            errors.append(f"{ai.PROVIDERS[prov]['label']}: کلید تنظیم نشده")
            continue
        try:
            raw, usage, _ = await ai.get_client(prov).complete(mdl, _system(s), msgs, "medium", schema=SCHEMA, hint=HINT)
            out = ai.parse_output(raw)
            ops = [clean(o) for o in out.get("ops") or []]
            return {"reply": str(out.get("reply") or "").strip(), "ops": [o for o in ops if o],
                    "cost": ai.cost_usd(ai._label(prov, mdl), usage, s)}
        except ValueError as e:
            errors.append(f"خروجی نامعتبر: {e}")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{ai.PROVIDERS[prov]['label']}: {str(e)[:200]}")
    raise ValueError("هوش مصنوعی در دسترس نیست: " + " | ".join(errors))


def clean(o: dict) -> dict | None:
    """فقط فیلدهای لازم هر op؛ op ناشناخته یا تنظیم غیرمجاز حذف می‌شود."""
    if not isinstance(o, dict):
        return None
    op = o.get("op")
    if op == "intent_upsert":
        return {"op": op, "id": str(o.get("id") or ""), "keys": list(o.get("keys") or []),
                "examples": list(o.get("examples") or []), "answer": str(o.get("answer") or ""),
                "action": str(o.get("action") or "")}
    if op == "intent_delete":
        return {"op": op, "id": str(o.get("id") or "")}
    if op == "section_set":
        return {"op": op, "key": str(o.get("key") or ""), "text": str(o.get("text") or "")}
    if op == "setting" and o.get("key") in ALLOWED:
        try:
            value = json.loads(o.get("value_json") or "null") if "value_json" in o else o.get("value")
        except ValueError:
            return None
        return {"op": op, "key": o["key"], "value": value}
    return None


def apply(c, ops: list[dict]) -> list[str]:
    """تغییرهای تأییدشده را با همان اعتبارسنجی پنل اعمال می‌کند. خروجی: فهرست نتیجه‌ی هر op."""
    results = []
    for raw in ops[:30]:
        o = clean(raw)
        if not o:
            results.append("❌ تغییر نامعتبر رد شد")
            continue
        try:
            if o["op"] == "intent_upsert":
                if o["id"] and o["id"] not in {x["id"] for x in shared_kb.intents()}:
                    o["id"] = ""
                shared_kb.save_intent({**o, "enabled": True})
                results.append(f"✅ نیت «{'، '.join((o['keys'] or o['examples'])[:3])}» ذخیره شد")
            elif o["op"] == "intent_delete":
                if not o["id"].startswith("p_"):
                    raise ValueError("نیت‌های اصلی حذف نمی‌شوند؛ می‌شود خاموششان کرد")
                shared_kb.delete_intent(o["id"])
                results.append(f"✅ نیت {o['id']} حذف شد")
            elif o["op"] == "section_set":
                shared_kb.save_section(o["key"], o["text"])
                results.append(f"✅ بخش «{shared_kb.SECTIONS.get(o['key'], o['key'])}» به‌روز شد")
            else:
                ai.save_settings(c, {o["key"]: o["value"]})
                results.append(f"✅ تنظیم «{ALLOWED[o['key']].split(' (')[0]}» عوض شد")
        except (ValueError, TypeError) as e:
            results.append(f"❌ {e}")
    return results
