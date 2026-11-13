"""وارد کردن قانون‌ها از فایل JSON.

فرمت ما (rules.json):
[
  {
    "name": "تقویم",
    "channels": ["comment"],
    "post_scope": "all",
    "triggers": [{"match": "contains", "value": "تقویم"}, {"match": "exact", "value": "لینک"}],
    "actions": {
      "public_replies": ["چک کن دایرکت رو ✅", "فرستادم برات 📥"],
      "private_replies": ["📅 تقویم فارسی آیفون: https://..."],
      "dm_replies": []
    },
    "advanced": {"cooldown_seconds": 3600}
  }
]

نگاشت از خروجی نوین‌هاب بعد از دیدن فرمت واقعی فایل اضافه می‌شود.
"""
import json
import sys

from . import db
from .rules import MATCHES

CHANNELS = {"comment", "dm", "story_reply", "mention"}


def validate(rule: dict) -> list[str]:
    errs = []
    if not rule.get("name"):
        errs.append("name لازم است")
    if not set(rule.get("channels", [])) <= CHANNELS or not rule.get("channels"):
        errs.append("channels باید زیرمجموعه‌ی comment/dm/story_reply/mention باشد")
    for t in rule.get("triggers", []):
        if t.get("match", "any") not in MATCHES:
            errs.append(f"match نامعتبر: {t.get('match')}")
    acts = rule.get("actions", {})
    adv = rule.get("advanced", {}) or {}
    if not any(acts.get(k) for k in ("public_replies", "private_replies", "dm_replies", "form_id")) \
            and not (adv.get("handoff") or adv.get("pause_ai_minutes")):
        errs.append("حداقل یک پیام پاسخ، یک فرم، یا «سپردن به همکار» یا «توقف هوش مصنوعی» لازم است")
    if acts.get("form_id") not in (None, "", 0) and not isinstance(acts.get("form_id"), int):
        errs.append("فرم نامعتبر است")
    pause = adv.get("pause_ai_minutes")
    if pause not in (None, "", 0) and (not isinstance(pause, (int, float)) or not 0 < pause <= 7 * 24 * 60):
        errs.append("توقف هوش مصنوعی باید بین ۱ دقیقه و ۷ روز باشد")
    mx = adv.get("max_uses")
    if mx not in (None, "", 0) and (not isinstance(mx, int) or not 0 < mx <= 1_000_000):
        errs.append("محدودیت تعداد پاسخ باید عددی مثبت باشد")
    qr = acts.get("quick_replies", [])
    if not isinstance(qr, list) or len(qr) > 13 or any(not isinstance(x, str) or len(x) > 20 for x in qr):
        errs.append("quick_replies: حداکثر ۱۳ دکمه، هر کدام تا ۲۰ نویسه")
    return errs


def import_file(path: str) -> int:
    rules = json.load(open(path, encoding="utf-8"))
    bad = {r.get("name", f"#{i}"): validate(r) for i, r in enumerate(rules)}
    bad = {k: v for k, v in bad.items() if v}
    if bad:
        raise ValueError(json.dumps(bad, ensure_ascii=False, indent=1))
    db.init()
    with db.connect() as c:
        for r in rules:
            db.upsert_rule(c, r)
    return len(rules)


if __name__ == "__main__":
    print("imported", import_file(sys.argv[1]))
