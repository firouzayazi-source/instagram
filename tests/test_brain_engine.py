"""مغز مشترک: موتور فهم ربات تلگرام برای اینستاگرام، با نیت‌های پیش‌فرض واقعی ربات تلگرام."""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app import ai, brain_engine, config, db

TG = Path(__file__).resolve().parent.parent / "tgbot"
SAMPLE = [  # (نام، مدل، حافظه، رنگ، وضعیت، قیمت، دسته)
    ("آیفون 13 پرو 256", "iPhone 13 Pro", "256 گیگابایت", "Gold", "کارکرده", 190_000_000, "آیفون کارکرده"),
    ("آیفون 13 128 گیگ", "iPhone 13", "128 گیگابایت", "Midnight", "کارکرده", 125_000_000, "آیفون کارکرده"),
    ("شارژر 20 وات اپل", None, None, None, None, 2_500_000, "شارژر"),
]


@pytest.fixture(scope="session")
def tg_data(tmp_path_factory):
    d = tmp_path_factory.mktemp("tg")
    # نیت‌های پیش‌فرض خود ربات تلگرام
    code = ("import os,sys,json; os.environ.setdefault('BOT_TOKEN','0:x'); os.environ.setdefault('ADMIN_ID','1');"
            f"sys.path.insert(0,{str(TG)!r}); import bot;"
            "json.dump(bot.DEFAULT_INTENTS, open('faq.json','w',encoding='utf-8'), ensure_ascii=False)")
    subprocess.run([sys.executable, "-c", code], cwd=d, check=True, timeout=120)
    sys.path.insert(0, str(TG))
    import catalog
    items = [catalog.normalize({"id": i + 100, "name": n, "permalink": f"https://stland.ir/p/{i}", "is_in_stock": True,
                                "prices": {"price": str(p), "currency_minor_unit": 0}, "categories": [{"name": cat}],
                                "attributes": [{"name": k, "terms": [{"name": v}]} for k, v in
                                               (("مدل", m), ("حافظه", g), ("رنگ", c), ("وضعیت", s)) if v]})
             for i, (n, m, g, c, s, p, cat) in enumerate(SAMPLE)]
    (d / "catalog.json").write_text(json.dumps({"updated": time.time(), "items": items}, ensure_ascii=False), encoding="utf-8")
    (d / "data.json").write_text(json.dumps({"3": "💰 اقساط: پیش‌پرداخت <b>۳۰٪</b> و ۶ قسط",
                                             "5": "📍 آدرس: تهران، خیابان نمونه"}, ensure_ascii=False), encoding="utf-8")
    (d / "workhours.json").write_text(json.dumps({"enabled": True, "schedule": {
        str(k): {"open": k != 6, "shifts": [{"from": "10:00", "to": "22:00"}]} for k in range(7)}}), encoding="utf-8")
    return d


@pytest.fixture
def env(tg_data, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TG_DATA_DIR", str(tg_data))
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    db.init()
    ai.set_client(None)
    yield
    ai.set_client(None)


def test_engine_answers_from_shared_knowledge(env):
    assert brain_engine.available()
    act, reply, intent, *_ = brain_engine.decide("سلام")
    assert act == "reply" and intent == "greeting" and reply

    act, reply, intent, *_ = brain_engine.decide("قیمت آیفون ۱۳ پرو چنده؟")
    assert act == "reply" and "آیفون 13 پرو 256" in reply and "۱۹۰" in reply and "stland.ir/?p=100" in reply

    act, reply, *_ , reason = brain_engine.decide("خیلی بد بود، گوشی که ازتون خریدم خراب شد")
    assert act == "handoff" and reason

    assert brain_engine.decide("زکخحج قثفغ") is None

    # بخش‌ها و ساعت کاری از همان فایل‌های ربات تلگرام
    act, reply, *_ = brain_engine.decide("شرایط اقساط چیه؟")
    assert act == "reply" and "پیش‌پرداخت ۳۰٪" in reply and "<b>" not in reply
    act, reply, *_ = brain_engine.decide("آدرستون کجاست")
    assert "خیابان نمونه" in reply
    act, reply, *_ = brain_engine.decide("ساعت کاری")
    assert "جمعه: تعطیل" in reply and "۱۰:۰۰ تا ۲۲:۰۰" in reply


@pytest.mark.asyncio
async def test_brain_layer_in_decide_without_ai(env):
    with db.connect() as c:
        ai.save_settings(c, {"brain_enabled": True})        # هوش مصنوعی خاموش، فقط موتور فهم
        d = await ai.decide(c, channel="dm", text="قیمت آیفون ۱۳ پرو چنده؟", user_id="u1")
        assert d.action == "reply" and "۱۹۰" in d.reply
        row = c.execute("SELECT model, cost, status FROM ai_log WHERE id=?", (d.log_id,)).fetchone()
        assert row["model"] == "brain" and row["cost"] == 0 and row["status"] == "pending"

        d = await ai.decide(c, channel="comment", text="قیمت آیفون ۱۳ پرو چنده؟", user_id="u2")
        assert d.reply and d.public_reply in ai.DEFAULTS["public_ack"]

        d = await ai.decide(c, channel="dm", text="زکخحج قثفغ", user_id="u3")
        assert d.action == "handoff" and d.reply in brain_engine.brain.UNKNOWN_LEADS
        d = await ai.decide(c, channel="comment", text="زکخحج قثفغ", user_id="u4")
        assert d.action == "ignore" and not d.reply

        ai.save_settings(c, {"brain_enabled": False})
        d = await ai.decide(c, channel="dm", text="سلام", user_id="u5")
        assert d.action == "skip" and d.skip_reason == "disabled"


@pytest.mark.asyncio
async def test_panel_test_uses_brain_without_key(env):
    with db.connect() as c:
        d = await ai.decide(c, channel="dm", text="سلام وقت بخیر", user_id="test", is_test=True)
        assert d.action == "reply" and d.reply


def test_short_max_means_pro_max_and_neighbor_hint(env):
    import catalog
    import specs
    assert specs.find_models("قیمت ۱۳ مکس") == ["13 pro max"] and specs.find_models("13max") == ["13 pro max"]
    assert catalog.parse("۱۴ پلاس")["model"] == "14 plus" and catalog.parse("۱۳ معمولی")["model"] == "13"
    act, reply, intent, *_ = brain_engine.decide("قیمت ۱۳ مکس")
    assert intent == "price" and reply.startswith("الان آیفون ۱۳ پرو مکس موجود نداریم")   # پرو مکس، نه ۱۳ معمولی
    # کسی که ۱۳ پرو می‌خواهد: اشاره‌ی کوتاه به مدل پایین‌تر موجود (۱۳ معمولی)، در یک خط
    hint = catalog.neighbor_line(catalog.parse("۱۳ پرو"))
    assert hint.startswith("💡") and "آیفون ۱۳ از ۱۲۵ میلیون" in hint and hint.count("\n") == 0
    assert hint in brain_engine.decide("قیمت ۱۳ پرو")[1]
    assert catalog.neighbor_line(catalog.parse("شارژر")) == ""
