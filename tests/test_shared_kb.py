"""دانش مشترک: یک بار در پنل وب، همان جواب در تلگرام و اینستاگرام."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import ai, auth, brain_engine, config, db, knowledge, shared_kb
from app.main import create_app
from tests.test_webhook import FakeIG

TG = Path(__file__).resolve().parent.parent / "tgbot"

# ربات تلگرام واقعی (tgbot/bot.py) یک دور صف پنل را اعمال می‌کند، در پوشه‌ی داده‌ی خودش
APPLY = ("import os,sys,json,asyncio; os.environ.setdefault('BOT_TOKEN','0:x'); os.environ.setdefault('ADMIN_ID','1');"
         f"sys.path.insert(0,{str(TG)!r}); import logging; logging.disable(logging.CRITICAL); import bot as B\n"
         "async def main():\n"
         "    await B.load_data(); await B.load_settings(); await B.load_faq()\n"
         "    n = await B.process_panel_inbox()\n"
         "    print(n)\n"
         "asyncio.run(main())")


def tg_apply(d: Path) -> int:
    r = subprocess.run([sys.executable, "-u", "-c", APPLY], cwd=d, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return int(r.stdout.strip().splitlines()[-1])


@pytest.fixture
def env(tmp_path, monkeypatch):
    tg = tmp_path / "tg"
    tg.mkdir()
    (tg / "faq.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(config, "TG_DATA_DIR", str(tg))
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "PANEL_PASSWORD", "pw")
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    monkeypatch.setattr(config, "WEB_DIST", str(tmp_path / "nodist"))
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    auth._fails.clear()
    db.init()
    ai.set_client(None)
    yield tg
    ai.set_client(None)


def test_feed_once_answer_on_both(env):
    tg = env
    tg_apply(tg)        # ربات تلگرام نیت‌های پیش‌فرضش را می‌کارد (مثل اولین اجرا)
    before = {x["id"] for x in shared_kb.intents()}
    assert "i_price" in before

    shared_kb.save_intent({"keys": "تعمیر، تعمیرات", "examples": "گوشیمو تعمیر میکنید؟",
                           "answer": "بله، تعمیرات تخصصی آیفون داریم 🔧 گوشی رو بیارید فروشگاه."})
    shared_kb.save_section("3", "💰 اقساط با چک: پیش‌پرداخت ۴۰٪")
    assert shared_kb.pending()["count"] == 2
    assert tg_apply(tg) == 2
    assert shared_kb.pending()["count"] == 0

    new = [x for x in shared_kb.intents() if x["id"] not in before]
    assert len(new) == 1 and new[0]["id"].startswith("p_") and not new[0]["builtin"]
    assert json.loads((tg / "data.json").read_text(encoding="utf-8"))["3"].startswith("💰 اقساط با چک")

    # اینستاگرام همان را جواب می‌دهد
    act, reply, *_ = brain_engine.decide("گوشیمو تعمیر میکنید؟")
    assert act == "reply" and "تعمیرات تخصصی" in reply
    assert "پیش‌پرداخت ۴۰٪" in shared_kb.prompt_text()

    # ویرایش و حذف هم از همان راه
    shared_kb.save_intent({**new[0], "answer": "تعمیرات داریم، با گارانتی ۳ ماهه 🔧"})
    tg_apply(tg)
    assert "گارانتی ۳ ماهه" in brain_engine.decide("گوشیمو تعمیر میکنید؟")[1]
    shared_kb.delete_intent(new[0]["id"])
    tg_apply(tg)
    assert new[0]["id"] not in {x["id"] for x in shared_kb.intents()}


def test_validation_and_unready(env, monkeypatch):
    for bad in ({"keys": "", "examples": "", "answer": "x"}, {"keys": "a", "answer": "", "action": ""},
                {"keys": "a", "answer": "x", "action": "rm -rf"}, {"id": "../x", "keys": "a", "answer": "x"}):
        with pytest.raises(ValueError):
            shared_kb.save_intent(bad)
    with pytest.raises(ValueError):
        shared_kb.save_section("nope", "x")
    monkeypatch.setattr(config, "TG_DATA_DIR", str(env / "missing"))
    with pytest.raises(ValueError):
        shared_kb.save_intent({"keys": "a", "answer": "x"})


def test_api_and_migrate_old_faq(env):
    with TestClient(create_app(FakeIG())) as cl:
        cl.post("/api/login", json={"password": "pw"})
        with db.connect() as c:
            knowledge.save_faq(c, {"question": "ارسال دارید؟", "keywords": "ارسال، پست", "answer": "به همه‌ی شهرها"})
        kb = cl.get("/api/ai/kb").json()
        assert kb["ready"] and kb["old_faq"] == 1 and "prices" in kb["actions"]
        assert cl.post("/api/ai/kb/intents", json={"keys": "", "answer": "x"}).status_code == 422
        assert cl.post("/api/ai/kb/intents", json={"keys": "سلام", "answer": "درود"}).json()["queued"]
        assert cl.post("/api/ai/kb/migrate-faq").json()["moved"] == 1
        assert cl.get("/api/ai/kb").json()["old_faq"] == 0
        assert cl.get("/api/ai/kb").json()["pending"]["count"] == 2
    assert tg_apply(env) == 2
    moved = [x for x in shared_kb.intents() if x["answer"] == "به همه‌ی شهرها"]
    assert moved and moved[0]["examples"] == ["ارسال دارید؟"] and "پست" in moved[0]["keys"]
