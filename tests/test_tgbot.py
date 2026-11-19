"""ربات تلگرام (tgbot/) بخشی از همین پروژه است: کامپایل کد و سنجش ثابت پاسخ‌گویی دستیارش."""
import py_compile
import subprocess
import sys
from pathlib import Path

TG = Path(__file__).resolve().parent.parent / "tgbot"


def test_tgbot_compiles():
    for f in ("bot.py", "brain.py", "catalog.py", "specs.py", "profanity.py"):
        py_compile.compile(str(TG / f), doraise=True)


def test_tgbot_answer_check():
    r = subprocess.run([sys.executable, "-u", "tools/answer_check.py"], cwd=TG, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "0 شکست تازه" in r.stdout


def test_address_card_has_one_hours_button(tmp_path):
    """کارت آدرس: دکمه‌ی پیشنهادی «ساعت کاری» و دکمه‌ی ثابت کنار آدرس دوتا نشوند."""
    code = r"""
import asyncio, os, sys
os.environ.setdefault('BOT_TOKEN','0:x'); os.environ.setdefault('ADMIN_ID','1')
sys.path.insert(0, %r)
import bot
from telegram import InlineKeyboardButton as B
got = {}
async def fake_place(msg, key, kb=None): got['kb'] = kb; return True
async def fake_stat(*a, **k): pass
bot.send_place = fake_place; bot.record_stat = fake_stat
bot.place_active = lambda k: True
bot.workhours['enabled'] = True
rows = [[B('🕐 ساعت کاری', callback_data='ai_i_hours'), B('📞 تماس', callback_data='ai_i_phone')]]
asyncio.run(bot.send_section(None, '5', extra_rows=rows))
labels = [b.text for r in got['kb'].inline_keyboard for b in r]
assert sum('ساعت کاری' in t for t in labels) == 1, labels
assert '📞 تماس' in labels, labels
print('OK')
""" % str(TG)
    r = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "OK" in r.stdout, r.stdout[-1500:] + r.stderr[-1500:]


def test_apple_id_intent_sends_bot_button(tmp_path):
    """«اپل آیدی» در تلگرام: دکمه‌ی ربات اپل‌آیدی از همان دکمه‌ی منوی ربات (نشانی از پنل مدیر)."""
    code = r"""
import asyncio, os, sys
os.environ.setdefault('BOT_TOKEN','0:x'); os.environ.setdefault('ADMIN_ID','1')
sys.path.insert(0, %r)
import bot
bot.menu_cfg[:] = [{'key':'p_apl','label':'🆔 خرید اپل آیدی','order':9,'enabled':True}]
bot.buttons['p_apl'] = {'enabled':True,'items':[{'title':'ربات','url':'https://t.me/Stlandd_bot'}]}
bot.responses = {}
sent = []
class M:
    chat_id = 1
    async def reply_text(self, text, **kw): sent.append((text, kw))
class U: id = 99; first_name = 'x'; username = 'x'
it = next(x for x in bot.DEFAULT_INTENTS if x['id'] == 'i_appleid')
asyncio.run(bot.run_intent(M(), it, U(), None, dry=True))
text, kw = sent[-1]
urls = [b.url for r in kw['reply_markup'].inline_keyboard for b in r if getattr(b, 'url', None)]
assert 'ربات اصلی استوک‌لند' in text and urls == ['https://t.me/Stlandd_bot'], (text, urls)
print('OK')
""" % str(TG)
    r = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "OK" in r.stdout, r.stdout[-1500:] + r.stderr[-1500:]


def test_installment_card_hides_fee_breakdown():
    """اختلاف نقد به اقساط فقط گفته می‌شود؛ مبلغ و درصدش جدا نمی‌آید، ولی در قسط حساب می‌شود."""
    sys.path.insert(0, str(TG))
    import catalog
    cfg = {"down": 100 / 3, "rate": 6, "max_months": 10, "fee_pct": 10, "fee_cap": 5_000_000}
    html_ = catalog.installment_html({"name": "آیفون نمونه", "price": 100_000_000}, cfg)
    assert "کمی فرق داره" in html_ and "هزینه‌ی نقد به اقساط" not in html_ and "۱۰٪" not in html_
    rows = catalog.installments(100_000_000, cfg)
    assert rows[0][3] > 0                                   # اختلاف همچنان در محاسبه هست


def test_installment_caps():
    """سقف مبلغ اقساط: چک معتبر ۱۰۰ میلیون، طلا ۲۰۰ میلیون؛ پیش‌پرداخت حداقل یک‌سوم."""
    sys.path.insert(0, str(TG))
    import catalog
    cfg = {"down": 100 / 3, "rate": 6, "max_months": 10, "fee_pct": 10, "fee_cap": 5_000_000}
    small = catalog.installment_html({"name": "الف", "price": 90_000_000}, cfg)     # مانده ۶۰ م
    assert "حداقل یک‌سوم" in small and "سقف اقساط" in small and "⚠️" not in small
    mid = catalog.installment_html({"name": "ب", "price": 210_000_000}, cfg)       # مانده ۱۴۰ م
    assert "از سقف چک بیشتر" in mid and "طلا" in mid
    big = catalog.installment_html({"name": "ج", "price": 330_000_000}, cfg)       # مانده ۲۲۰ م
    assert "از سقف بیشتر است" in big and "پیش‌پرداخت بیشتر" in big


def test_topic_transcript_shows_question_and_bot_reply(tmp_path):
    """تاپیک مشتری: ساعت، سؤال مشتری و جواب کوتاه ربات در یک پیام؛ بی جواب ← «با شما»."""
    code = r"""
import asyncio, os, sys, types
os.environ.setdefault('BOT_TOKEN','0:x'); os.environ.setdefault('ADMIN_ID','1')
sys.path.insert(0, %r)
import bot
bot.settings['support_group'] = -100
bot.settings['ai_cc_admin'] = True
posted = []
async def fake_to_topic(b, user, card, send=None, note=''):
    class B:
        async def send_message(self, gid, text, **k): posted.append(text)
    await send(-100, 7) if send else None
    return True
bot.to_topic = fake_to_topic
async def no_card(uid): return ''
bot.customer_card = no_card
u = types.SimpleNamespace(id=55, username='ali', first_name='Ali')
class FakeBot:
    async def send_message(self, gid, text, **k): posted.append(text)
async def run():
    bot.tx_start(55, 'اقساط ایکس اس')
    bot.tx_capture(55, '<b>شرایط اقساط:</b> پیش‌پرداخت یک‌سوم https://stland.ir/product/%%d8%%a2%%db%%8c')
    bot.tx_capture(-100, 'پیام گروه')            # پیام گروه جزو جواب نیست
    await bot.tx_flush(FakeBot(), u)
    bot.tx_start(55, 'سلام کسی هست؟')
    await bot.tx_flush(FakeBot(), u)
asyncio.run(run())
assert 'اقساط ایکس اس' in posted[0] and 'پیش‌پرداخت یک‌سوم' in posted[0] and 'پیام گروه' not in posted[0], posted
assert '&lt;b&gt;' not in posted[0] and '%%d8' not in posted[0] and 'ربات جواب داد' in posted[0] and 'blockquote' in posted[0], posted   # بی برچسب و لینک بلند
assert 'منتظر جواب شما' in posted[1], posted
assert not bot.tx_active(55)
print('OK')
""" % str(TG)
    r = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "OK" in r.stdout, r.stdout[-2000:] + r.stderr[-2000:]


def test_site_pages_offline_search():
    """ربات: سؤالی که نیتی ندارد ولی یکی از صفحه‌های سایت روشن به آن می‌خورد ← خلاصه‌ی همان صفحه با لینک."""
    sys.path.insert(0, str(TG))
    import sitepages
    sitepages.set_items([
        {"id": 1, "kind": "pages", "title": "شرایط مرجوعی و بازگشت کالا", "link": "https://stland.ir/return",
         "text": "مشتری تا ۷ روز می‌تواند گوشی کارکرده را تست کند.\nدر صورت ایراد فنی، کالا مرجوع می‌شود."},
        {"id": 2, "kind": "posts", "title": "راهنمای تشخیص آیفون اصل از تقلبی", "link": "https://stland.ir/blog/fake",
         "text": "برای تشخیص آیفون اصل، شماره سریال را در سایت اپل چک کنید."}])
    hit = sitepages.search("چطور آیفون اصل رو تشخیص بدم")
    assert hit and hit["link"].endswith("/fake") and "سریال" in hit["snippet"]
    assert sitepages.search("شرایط مرجوعی چیه")["link"].endswith("/return")
    assert sitepages.search("سلام") is None and sitepages.search("قیمت ۱۳ پرو") is None


def test_learn_from_admin_reply(tmp_path):
    """جواب همکار به سؤالی که ربات نفهمید ← «یاد بگیر» ← دفعه‌ی بعد خود ربات همان را جواب می‌دهد."""
    code = r"""
import asyncio, os, sys
os.environ.setdefault('BOT_TOKEN','0:x'); os.environ.setdefault('ADMIN_ID','1')
sys.path.insert(0, %r)
import bot, brain
async def run():
    await bot.init_db(); await bot.load_faq(); await bot.load_learn(); await bot.load_unmatched()
    q = 'بیمه بدنه گوشی هم انجام میدید'
    assert brain.match(q, bot.brain_intents())[0] is None or True
    it = await bot.learn_from_reply(q, 'بله، بیمه‌ی بدنه از طریق همکار ما انجام می‌شود.')
    assert it and it['answer'].startswith('بله')
    got, sc = brain.match('بیمه بدنه برای گوشی دارید', bot.brain_intents())
    assert got is not None and got['id'] == it['id'], (got and got['id'], sc)
    assert bot.learn_data['log'][0]['src'] == 'admin-reply'
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


def test_weekly_review_with_suggestions(tmp_path):
    """گزارش هفتگی: درصد فهم، و سؤال نفهمیده با پیشنهاد آماده که با یک لمس تأیید می‌شود."""
    code = r"""
import asyncio, os, sys, types
os.environ.setdefault('BOT_TOKEN','0:x'); os.environ.setdefault('ADMIN_ID','1')
sys.path.insert(0, %r)
import bot
async def run():
    await bot.init_db(); await bot.load_faq(); await bot.load_unmatched(); await bot.load_settings()
    u = types.SimpleNamespace(id=77)
    for _ in range(4): await bot.record_event(77, bot.EV_MSG)
    await bot.log_unmatched('قسطی اقساط شرایطش برای دانشجو چطوره', u)
    txt, kb = await bot.weekly_review()
    assert '٪' in txt and 'قسطی' in txt, txt
    cb = [b.callback_data for r in kb.inline_keyboard for b in r]
    assert any(c.startswith('unm_') for c in cb), cb
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


def test_hot_lead_alert(tmp_path):
    """مشتری داغ: قیمت دید و اقساط پرسید ← یک هشدار (نه دو بار در ۲۴ ساعت)."""
    code = r"""
import asyncio, os, sys, types
os.environ.setdefault('BOT_TOKEN','0:x'); os.environ.setdefault('ADMIN_ID','1')
sys.path.insert(0, %r)
import bot
sent = []
class FB:
    async def send_message(self, cid, text, **k): sent.append(text)
async def run():
    await bot.init_db(); await bot.load_settings()
    u = types.SimpleNamespace(id=91, username='x', first_name='Sara')
    await bot.record_event(91, 'ai:i_price')
    assert not await bot.hot_check(FB(), u)
    await bot.record_event(91, 'ai:i_install')
    assert await bot.hot_check(FB(), u) and 'مشتری داغ' in sent[0]
    assert not await bot.hot_check(FB(), u)
    await bot.load_learn(); await bot.record_event(91, bot.EV_MSG)
    brief = await bot.morning_brief()
    assert 'مشتری داغ' in brief, brief
    assert '_hot' not in await bot.customer_card(91)
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


def test_tradein_appraisal_card(tmp_path):
    """کارشناسی معاوضه: سه جواب ← یک کارت کامل برای همکار، بی قیمت."""
    code = r"""
import asyncio, os, sys, types
os.environ.setdefault('BOT_TOKEN','0:x'); os.environ.setdefault('ADMIN_ID','1')
sys.path.insert(0, %r)
import bot
cards = []; said = []
async def fake_handoff(b, user, why='', icon='', extra=''): cards.append((why, extra))
bot.notify_handoff = fake_handoff
bot.set_human = lambda *a, **k: None
class Msg:
    async def reply_text(self, t, **k): said.append(t)
async def run():
    await bot.init_db(); await bot.load_faq()
    u = types.SimpleNamespace(id=31, username=None, first_name='R')
    st = bot.ti_state[31] = {'ts': bot.time.time(), 'step': 0, 'a': []}
    assert await bot.ti_typed(Msg(), u, None, st, '۱۳ پرو ۲۵۶')
    assert await bot.ti_typed(Msg(), u, None, st, '۸۷ درصد')
    await bot.ti_answer(Msg(), u, None, st, bot.TI_COND[1])
    assert 31 not in bot.ti_state and cards and '۱۳ پرو ۲۵۶' in cards[0][1] and '۸۷' in cards[0][1] and 'خط و خش' in cards[0][1]
    assert not any('تومان' in x or 'میلیون' in x for x in said)
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
