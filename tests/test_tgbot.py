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
