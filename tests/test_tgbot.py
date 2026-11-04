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
bot.buttons['p_apl'] = {'enabled':True,'items':[{'title':'ربات','url':'https://t.me/StlandAppleBot'}]}
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
assert 'ربات اصلی استوک‌لند' in text and urls == ['https://t.me/StlandAppleBot'], (text, urls)
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
