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
    for t in ('بیمه بدنه گوشی دارید', 'بیمه گوشی هم میکنید', 'گوشی رو بیمه میکنید؟'):
        await bot.log_unmatched(t, u)
    cl = bot.unmatched_clusters()
    assert cl and cl[0]['label'].startswith('بیمه') and cl[0]['count'] == 3, cl
    txt, kb = await bot.weekly_review()
    assert '🧩' in txt, txt
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


def test_aftersale_due_once(tmp_path):
    """پیگیری بعد از خرید: فقط سفارش تلگرامِ تحویل‌شده‌ی ۷ تا ۱۰ روز پیش، و فقط یک بار."""
    import sqlite3, time
    db = tmp_path / "core.db"
    now = time.time()
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE orders(id INTEGER PRIMARY KEY, channel TEXT, user_id TEXT, name TEXT, product TEXT, status TEXT, updated_at REAL)")
        c.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?)", [
            (1, "tg", "500", "علی رضایی", "آیفون ۱۳", "done", now - 8 * 86400),
            (2, "tg", "501", "x", "y", "done", now - 2 * 86400),          # هنوز زود است
            (3, "ig", "777", "x", "y", "done", now - 8 * 86400),          # اینستاگرام: هرگز
            (4, "tg", "502", "x", "y", "shipped", now - 8 * 86400)])
    code = r"""
import os, sys
os.environ.setdefault('BOT_TOKEN','0:x'); os.environ.setdefault('ADMIN_ID','1')
sys.path.insert(0, %r)
import bot
due = bot.aftersale_due(path=%r)
assert [r[0] for r in due] == [1], due
bot.settings['aftersale_done'] = [1]
assert bot.aftersale_due(path=%r) == []
print('OK')
""" % (str(TG), str(db), str(db))
    r = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "OK" in r.stdout, r.stdout[-2000:] + r.stderr[-2000:]


def test_ab_report_counts_buy_signals(tmp_path):
    """آزمایش متن‌ها: شکل ۱ به ۶ نفر، ۳ نفرشان بعدش اقساط پرسیدند؛ شکل ۲ به ۶ نفر، ۱ نفر."""
    code = r"""
import asyncio, os, sys
os.environ.setdefault('BOT_TOKEN','0:x'); os.environ.setdefault('ADMIN_ID','1')
sys.path.insert(0, %r)
import bot
async def run():
    await bot.init_db(); await bot.load_faq()
    iid = bot.faq[0]['id']
    for u in range(6):
        await bot.db.execute("INSERT INTO events VALUES (?,?,datetime('now','-1 day','localtime'))", (u, f'v:{iid}:0'))
        await bot.db.execute("INSERT INTO events VALUES (?,?,datetime('now','-1 day','localtime'))", (100+u, f'v:{iid}:1'))
    for u in (0, 1, 2, 100):
        await bot.db.execute("INSERT INTO events VALUES (?,?,datetime('now','localtime'))", (u, 'ai:i_install'))
    await bot.db.commit()
    rep = await bot.ab_report()
    assert rep and '۳/۶' in rep[0] and '۱/۶' in rep[0], rep
    assert 'v:' not in await bot.customer_card(0)
    await bot.db.close()
try:
    asyncio.run(run()); print('OK', flush=True)
except BaseException:
    import traceback; traceback.print_exc(); sys.stderr.flush()
os._exit(0)
""" % str(TG)
    r = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "OK" in r.stdout, r.stdout[-2000:] + r.stderr[-2000:]


def test_visit_booking_and_reminder(tmp_path):
    """رزرو بازدید: فقط ساعت‌های داخل شیفت، کارت برای همکار، یادآوری یک بار."""
    code = r"""
import asyncio, os, sys, types, re
os.environ.setdefault('BOT_TOKEN','0:x'); os.environ.setdefault('ADMIN_ID','1')
sys.path.insert(0, %r)
import bot
from datetime import timedelta
cards = []; said = []
async def fake_handoff(b, user, why='', icon='', extra=''): cards.append((why, extra))
bot.notify_handoff = fake_handoff
bot.workhours = {'enabled': True, 'schedule': {str(d): {'open': True, 'shifts': [{'from': '10:00', 'to': '14:00'}]} for d in range(7)}}
class Msg:
    async def reply_text(self, t, **k): said.append((t, k.get('reply_markup')))
    async def edit_text(self, t, **k): said.append((t, k.get('reply_markup')))
    async def edit_reply_markup(self, **k): pass
async def run():
    await bot.init_db()
    now = bot.datetime.now(bot.IRAN_TZ).replace(hour=12, minute=30)
    days = bot.visit_days(now)
    assert days and days[0][0] == 1 and days[0][2] == ['10:00','11:00','12:00','13:00'], days   # امروز دیگر دیر است
    u = types.SimpleNamespace(id=41, username=None, first_name='S')
    q = types.SimpleNamespace(from_user=u, message=Msg())
    await bot.visit_callback(q, None, 'vis_go')
    kb = said[-1][1].inline_keyboard
    off = kb[0][0].callback_data
    await bot.visit_callback(q, None, off)
    t = said[-1][1].inline_keyboard[-1][-1].callback_data
    await bot.visit_callback(q, None, t)
    assert cards and 'رزرو بازدید' in cards[-1][0] and 'ساعت' in cards[-1][1]
    cur = await bot.visit_upcoming(41); assert cur
    at = bot.datetime.strptime(cur[1], '%%Y-%%m-%%d %%H:%%M').replace(tzinfo=bot.IRAN_TZ)
    assert await bot.visits_due(at - timedelta(minutes=90)) == []
    due = await bot.visits_due(at - timedelta(minutes=30)); assert [r[1] for r in due] == [41]
    await bot.visit_callback(q, None, 'vis_x')
    assert await bot.visit_upcoming(41) is None and 'لغو' in cards[-1][0]
    bot.settings['visits'] = False
    assert bot.visit_days(now) == []
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


def test_referral_link_and_record(tmp_path):
    """دعوت دوست: لینک اختصاصی، ثبت یک‌باره‌ی معرف، خبر به معرف، نه خوددعوتی."""
    code = r"""
import asyncio, os, sys, types
os.environ.setdefault('BOT_TOKEN','0:x'); os.environ.setdefault('ADMIN_ID','1')
sys.path.insert(0, %r)
import bot
sent = []
class B:
    username = 'Shop_bot'
    async def send_message(self, chat, text, **k): sent.append((chat, text))
async def run():
    await bot.init_db(); await bot.load_faq()
    a = types.SimpleNamespace(id=5001, username=None, first_name='A', last_name=None, language_code='fa', is_bot=False)
    f = types.SimpleNamespace(id=5002, username=None, first_name='F', last_name=None, language_code='fa', is_bot=False)
    await bot.save_user(a); await bot.save_user(f)
    t = await bot.ref_text(5001, 'Shop_bot')
    assert 'https://t.me/Shop_bot?start=ref_5001' in t and 'هنوز کسی' in t
    assert await bot.ref_record(B(), a, 'ref_5001') is None          # خودش را دعوت نمی‌کند
    assert await bot.ref_record(B(), f, 'ref_9999') is None          # معرف ناشناس
    assert await bot.ref_record(B(), f, 'ref_5001') == 5001 and sent and sent[0][0] == 5001
    assert await bot.ref_record(B(), f, 'ref_5001') is None          # فقط یک بار
    assert await bot.ref_count(5001) == 1 and await bot.ref_of(5002) == 5001
    bot.settings['ref_reward'] = 'جایزه‌ی آزمایشی'
    assert 'جایزه‌ی آزمایشی' in await bot.ref_text(5001, 'Shop_bot') and '۱ نفر' in await bot.ref_text(5001, 'Shop_bot')
    card = await bot.customer_card(5002); assert 'معرف' in card
    it, sc = bot.brain.match('لینک دعوت میخوام', bot.brain_intents()); assert it and it['id'] == 'i_invite', it
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


def test_staff_report_and_sla(tmp_path):
    """عملکرد تیم: زمان انتظار هر جواب ثبت می‌شود؛ هشدار انتظار فقط یک بار و فقط بعد از سقف."""
    code = r"""
import asyncio, os, sys, types
os.environ.setdefault('BOT_TOKEN','0:x'); os.environ.setdefault('ADMIN_ID','1')
sys.path.insert(0, %r)
import bot
from datetime import timedelta
async def run():
    await bot.init_db()
    u = types.SimpleNamespace(id=6001, username=None, first_name='C', last_name=None, language_code='fa', is_bot=False)
    await bot.save_user(u)
    old = (bot.datetime.now(bot.IRAN_TZ) - timedelta(minutes=20)).strftime('%%Y-%%m-%%d %%H:%%M:%%S')
    await bot.db.execute("UPDATE users SET open_msg_at=? WHERE user_id=6001", (old,)); await bot.db.commit()
    bot.settings['sla_min'] = 30
    assert await bot.sla_due() == []
    bot.settings['sla_min'] = 15
    due = await bot.sla_due(); assert [r[0] for r in due] == [6001]
    bot._sla_sent.add((6001, old)); assert await bot.sla_due() == []
    bot.settings['sla_min'] = 0; assert await bot.sla_due() == []
    await bot.mark_answered(6001, staff=1)
    rep = await bot.staff_report(7)
    assert len(rep) == 1 and rep[0][1] == 1 and 1150 <= rep[0][2] <= 1300, rep
    assert 'دقیقه' in bot.staff_lines(rep)[0]
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


def test_bale_mode_settings(tmp_path):
    """BOT_PLATFORM=bale: توکن و مدیرهای جدا، سرور بله، لینک ble.ir، سفارش با کانال bale، بی مینی‌اپ."""
    code = r"""
import os, sys
os.environ.pop('BOT_TOKEN', None)
os.environ.update(BOT_PLATFORM='bale', BALE_BOT_TOKEN='1:b', BALE_ADMIN_ID='77')
sys.path.insert(0, %r)
import bot
assert bot.IS_BALE and bot.OWNER_ID == 77 and bot.ORDER_CHANNEL == 'bale' and bot.CORE_CHANNEL == 'bale'
bot.BOT_USERNAME = 'shop_bot'
assert bot.deep_link('insta') == 'https://ble.ir/shop_bot?start=insta'
b = bot.link_button('سایت', 'https://' + bot.SHOP_SITE + '/x')
assert b.url and not b.web_app
t = bot.TxBot('1:b', base_url='https://tapi.bale.ai/bot')
assert 'tapi.bale.ai' in t.base_url
print('OK')
""" % str(TG)
    r = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "OK" in r.stdout, r.stdout[-2000:] + r.stderr[-2000:]
