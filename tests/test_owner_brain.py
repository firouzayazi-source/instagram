"""چهار قابلیت «مغز صاحب فروشگاه» (۷ آذر ۱۴۰۵): تخمین معاوضه با جدول صاحب فروشگاه، خواندن اسکرین‌شات گوشی،
گزارش تقاضای سه پلتفرم، خبر افت قیمت؛ و فهم ویس که پیش‌فرض خاموش است."""
import asyncio
import json
import subprocess
import sys
from pathlib import Path

import httpx

TG = Path(__file__).resolve().parent.parent / "tgbot"
sys.path.insert(0, str(TG))
import tradein  # noqa: E402

CFG = {"prices": {"13 pro|256": 100_000_000}, "battery": [[90, 0], [85, 3], [0, 10]], "cond": [0, 5, 20]}


def model_of(t):
    return ("13 pro", "256") if "13" in t else (None, None)


def test_estimate_only_with_owner_table():
    assert tradein.estimate(None, "13 pro", "256", 92, 0) is None                 # بی جدول: هیچ عددی
    assert tradein.estimate(CFG, "14", "128", 92, 0) is None                       # مدلی که قیمت ندارد
    assert tradein.estimate(CFG, "13 pro", "256", None, 0) is None                 # باتری نامعلوم
    assert tradein.estimate(CFG, "13 pro", "256", 92, 0) == (95_000_000, 100_000_000)
    lo, hi = tradein.estimate(CFG, "13 pro", "256", 86, 1)                         # ۳٪ + ۵٪
    assert hi == 92_000_000 and lo < hi
    assert tradein.estimate({**CFG, "on": False}, "13 pro", "256", 92, 0) is None


def test_tradein_command():
    cfg, note = tradein.apply_cmd({}, ["13", "pro", "256", "95"], model_of)
    assert note.startswith("✅") and cfg["prices"]["13 pro|256"] == 95_000_000
    cfg, note = tradein.apply_cmd(cfg, ["battery", "90:0", "85:4"], model_of)
    assert note.startswith("❌")                                                   # بازه‌ی ۰ لازم است
    cfg, note = tradein.apply_cmd(cfg, ["battery", "۹۰:0", "85:4", "0:12"], model_of)
    assert note.startswith("✅") and cfg["battery"][0] == [90, 0.0]
    cfg, note = tradein.apply_cmd(cfg, ["cond", "0", "5", "20"], model_of)
    assert tradein.ready(cfg)
    cfg, note = tradein.apply_cmd(cfg, ["del", "13", "pro", "256"], model_of)
    assert "13 pro|256" not in cfg["prices"]
    assert tradein.battery_of("سلامت باتری ۸۷ درصد") == 87 and tradein.battery_of("نمی‌دونم") is None


def test_phone_screenshot_with_anthropic_key(monkeypatch):
    """خواندن اسکرین‌شات با کلید Anthropic (همان کلیدی که صاحب پیج دارد)."""
    from app import config, vision
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "x")
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text":
                              '{"model":"iPhone 13 Pro","storage_gb":256,"battery":87,"parts":["Unknown Part"]}'}]})
    assert vision.available() == "anthropic"
    info = asyncio.run(vision.phone_info(b"\xff\xd8img", transport=httpx.MockTransport(handler)))
    assert info == {"model": "iPhone 13 Pro", "storage_gb": 256, "battery": 87, "parts": ["Unknown Part"]}
    assert "api.anthropic.com" in seen["url"] and seen["body"]["messages"][0]["content"][0]["type"] == "image"


def test_instagram_search_feeds_demand(tmp_path, monkeypatch):
    from app import brain_engine, config
    (tmp_path / "faq.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(config, "TG_DATA_DIR", str(tmp_path))
    brain_engine.log_search("آیفون XS", False, "ig:42")
    brain_engine.log_search("آیفون XS", False, None)              # آزمون پنل: ثبت نمی‌شود
    ops = [json.loads(f.read_text(encoding="utf-8")) for f in (tmp_path / "inbox").glob("*.json")]
    assert ops == [{"op": "search_log", "q": "آیفون XS", "found": False, "who": "ig:42"}]


def test_bot_owner_features(tmp_path):
    """ربات: تخمین در پایان کارشناسی، گزارش تقاضای اینستاگرام، خبر افت قیمت یک‌باره، ویس پیش‌فرض خاموش، شناسنامه‌ی سلامت."""
    code = r"""
import asyncio, os, sys, types, json
os.environ.setdefault('BOT_TOKEN','0:x'); os.environ.setdefault('ADMIN_ID','1')
sys.path.insert(0, %r)
import bot, catalog
cards = []; said = []; sent = []
async def fake_handoff(b, user, why='', icon='', extra=''): cards.append(extra)
async def fake_note(*a, **k): pass
bot.notify_handoff = fake_handoff; bot.topic_note = fake_note
bot.set_human = lambda *a, **k: None
class Msg:
    async def reply_text(self, t, **k): said.append(t)
class Bot:
    async def send_message(self, uid, t, **k): sent.append((uid, t))
async def run():
    await bot.init_db(); await bot.load_faq(); await bot.load_settings()
    assert bot.get_setting('voice') is False                                   # فهم ویس پیش‌فرض خاموش
    bot.settings['tradein'] = {"prices": {"13 pro|256": 100000000}, "battery": [[90,0],[0,10]], "cond": [0,5,20]}
    u = types.SimpleNamespace(id=31, username=None, first_name='R')
    st = bot.ti_state[31] = {'ts': bot.time.time(), 'step': 0, 'a': []}
    await bot.ti_typed(Msg(), u, None, st, '۱۳ پرو ۲۵۶')
    await bot.ti_typed(Msg(), u, None, st, '۹۲')
    await bot.ti_answer(Msg(), u, None, st, bot.TI_COND[0])
    assert any('۹۵ میلیون تا ۱۰۰ میلیون' in x and 'کارشناسی حضوری' in x for x in said), said
    assert 'تخمین ربات' in cards[-1]
    # گزارش تقاضا: جستجوی بی‌نتیجه‌ی اینستاگرام از صف
    bot.SHARED_INBOX = None
    for who in ('ig:1', 'ig:2'):
        await bot.db.execute("INSERT INTO searches(ts,user_id,q,found) VALUES(?,?,?,0)", (bot.gregorian_now(), -int(who[-1]), 'آیفون XS'))
    await bot.db.commit()
    t = await bot.demand_text(7)
    assert 'آیفون XS' in t and 'پیشنهاد خرید' in t
    # خبر افت قیمت: یک بار
    catalog.set_items([catalog.normalize({"id": 7, "name": "آیفون 13 پرو", "permalink": "https://stland.ir/p/7", "is_in_stock": True,
                       "prices": {"price": "90000000", "currency_minor_unit": 0}, "categories": [{"name": "آیفون کارکرده"}],
                       "attributes": [{"name": "مدل", "terms": [{"name": "iPhone 13 Pro"}]}, {"name": "وضعیت", "terms": [{"name": "کارکرده"}]}]})])
    catalog.updated = bot.time.time()
    x = catalog.by_id(7)
    await bot.watch_add(55, {**x, "price": 100000000})
    await bot.price_drop_auto(Bot()); await bot.price_drop_auto(Bot())
    assert len(sent) == 1 and '۹۰' in sent[0][1]
    assert 'شناسنامه‌ی سلامت' in catalog.card_html({**x, "used": True})
    await bot.db.close()
try:
    asyncio.run(run())
    print('OK', flush=True)
except BaseException:
    import traceback; traceback.print_exc(); sys.stderr.flush()
os._exit(0)
""" % str(TG)
    r = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "OK" in r.stdout, r.stdout[-2000:] + r.stderr[-2000:]
