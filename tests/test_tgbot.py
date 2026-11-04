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
