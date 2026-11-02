"""کانال‌ها: وضعیت اتصال، روشن/خاموش جدا برای هر شبکه، بدون لو رفتن هیچ کلیدی."""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import auth, channels, config, db, worker
from app.main import create_app
from tests.test_webhook import COMMENT, FakeIG

TG = Path(__file__).resolve().parent.parent / "tgbot"


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "telegram").mkdir(parents=True)
    monkeypatch.setattr(config, "DB_PATH", str(data / "bot.db"))
    monkeypatch.setattr(config, "TG_DATA_DIR", str(data / "telegram"))
    monkeypatch.setattr(config, "IG_USER_ID", "me")
    monkeypatch.setattr(config, "PANEL_PASSWORD", "pw")
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    monkeypatch.setattr(config, "WEB_DIST", str(tmp_path / "nodist"))
    monkeypatch.setattr(config, "IG_ACCESS_TOKEN", "secret-token-123")
    monkeypatch.setenv("BOT_TOKEN", "123:tg-secret")
    auth._fails.clear()
    db.init()
    return data


def test_describe_and_toggle(env):
    with db.connect() as c:
        chs = {x["id"]: x for x in channels.describe(c)}
    assert chs["instagram"]["enabled"] and chs["telegram"]["enabled"]
    assert not chs["bale"]["ready"] and not chs["bale"]["enabled"]
    assert {f["key"]: f["set"] for f in chs["instagram"]["fields"]}["IG_ACCESS_TOKEN"] is True
    assert chs["telegram"]["online"] is False
    blob = json.dumps(chs, ensure_ascii=False)
    assert "secret-token-123" not in blob and "tg-secret" not in blob

    (env / "telegram" / "status.json").write_text(json.dumps({"ts": time.time(), "username": "stland_bot", "users": 42}))
    channels.set_enabled("telegram", False)
    with db.connect() as c:
        tg = next(x for x in channels.describe(c) if x["id"] == "telegram")
    assert tg["online"] and tg["username"] == "stland_bot" and tg["users"] == 42 and not tg["enabled"]
    assert json.loads((env / "channels.json").read_text())["telegram"]["enabled"] is False
    with pytest.raises(ValueError):
        channels.set_enabled("bale", True)


@pytest.mark.asyncio
async def test_instagram_off_stores_but_does_not_reply(env):
    channels.set_enabled("instagram", False)
    ig = FakeIG()
    with db.connect() as c:
        db.upsert_rule(c, {"name": "قیمت", "channels": ["comment"], "triggers": [{"type": "any"}],
                           "actions": {"public_replies": ["دایرکت رو ببین"]}})
        db.add_event(c, "e1", "comment", COMMENT["entry"][0]["changes"][0]["value"])
        row = c.execute("SELECT * FROM events WHERE id='e1'").fetchone()
        assert await worker.handle_event(ig, row, c) == "ignored"
        assert ig.calls == [] and c.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 1


def test_api(env):
    with TestClient(create_app(FakeIG())) as cl:
        assert cl.get("/api/channels").status_code == 401
        cl.post("/api/login", json={"password": "pw"})
        assert [x["id"] for x in cl.get("/api/channels").json()][:2] == ["instagram", "telegram"]
        assert cl.put("/api/channels/telegram", json={"enabled": False}).json()["enabled"] is False
        assert cl.put("/api/channels/bale", json={"enabled": True}).status_code == 422
        assert cl.put("/api/channels/nope", json={"enabled": True}).status_code == 404


GATE = ("import os,sys,json,asyncio; os.environ.setdefault('BOT_TOKEN','0:x'); os.environ.setdefault('ADMIN_ID','1');"
        f"sys.path.insert(0,{str(TG)!r}); import logging; logging.disable(logging.CRITICAL); import bot as B\n"
        "from types import SimpleNamespace as NS\n"
        "def run(chat, uid):\n"
        "    up = NS(effective_chat=NS(type=chat), effective_user=NS(id=uid))\n"
        "    try: asyncio.run(B.channel_gate(up, None)); return 'pass'\n"
        "    except B.ApplicationHandlerStop: return 'stop'\n"
        "B._admins.add(1)\n"
        "print(run('private', 99), run('private', 1), run('supergroup', 99))")


def test_telegram_gate(env):
    tg = env / "telegram"
    r = subprocess.run([sys.executable, "-u", "-c", GATE], cwd=tg, capture_output=True, text=True, timeout=120)
    assert r.stdout.split() == ["pass", "pass", "pass"], r.stderr[-1500:]     # پیش‌فرض: روشن
    channels.set_enabled("telegram", False)
    r = subprocess.run([sys.executable, "-u", "-c", GATE], cwd=tg, capture_output=True, text=True, timeout=120)
    assert r.stdout.split() == ["stop", "pass", "pass"], r.stderr[-1500:]     # مشتری نه، مدیر و گروه تیم بله
