"""هوش مصنوعی مرکزی برای تلگرام: درگاه داخلی هسته، و مسیر واقعی ربات تلگرام تا آن."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import ai, config, db, internal
from app.main import create_app
from tests.test_ai import FakeClaude
from tests.test_webhook import FakeIG

TG = Path(__file__).resolve().parent.parent / "tgbot"


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "telegram").mkdir(parents=True)
    monkeypatch.setattr(config, "DB_PATH", str(data / "bot.db"))
    monkeypatch.setattr(config, "TG_DATA_DIR", str(data / "telegram"))
    monkeypatch.setattr(config, "WEB_DIST", str(tmp_path / "nodist"))
    fake = FakeClaude()
    ai.set_client(fake)
    yield data, fake
    ai.set_client(None)


def _think(cl, key, text="گوشی من آب خورده، درست میشه؟", **extra):
    return cl.post("/internal/think", headers={"X-Internal-Key": key, **extra.pop("headers", {})},
                   json={"channel": "telegram", "user_id": "55", "username": "ali", "text": text, **extra})


def test_internal_think(env):
    data, fake = env
    with TestClient(create_app(FakeIG())) as cl:
        key = internal.key_path().read_text().strip()
        assert len(key) > 30 and oct(os.stat(internal.key_path()).st_mode & 0o777) == "0o600"
        assert _think(cl, "wrong").status_code == 403
        assert _think(cl, key, headers={"X-Forwarded-For": "1.2.3.4"}).status_code == 404   # از اینترنت (پشت nginx)
        assert cl.post("/internal/think", headers={"X-Internal-Key": key},
                       json={"channel": "dm", "user_id": "1", "text": "x"}).status_code == 422

        assert _think(cl, key).json()["skip_reason"] == "disabled"          # هوش مصنوعی خاموش
        with db.connect() as c:
            ai.save_settings(c, {"enabled": True, "brain_enabled": True})
        r = _think(cl, key).json()
        assert r["action"] == "reply" and r["reply"] == fake.out["reply"]
        msgs = fake.calls[-1]["messages"][0]["content"]
        assert "پیام تلگرام" in msgs and "تلگرام" in fake.calls[-1]["system"][0]["text"]
        with db.connect() as c:
            row = c.execute("SELECT channel, user_id, status FROM ai_log ORDER BY id DESC").fetchone()
            assert tuple(row) == ("telegram", "tg:55", "sent")
            ai.save_settings(c, {"telegram_ai": False})
        assert _think(cl, key).json()["skip_reason"] == "channel_disabled"


# ربات تلگرام واقعی: پیامی که موتور فهم نمی‌فهمد → درگاه هسته (یک سرور جعلی محلی) → جواب به مشتری
HARNESS = r'''
import asyncio, json, os, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace as NS
os.environ.setdefault("BOT_TOKEN", "0:x"); os.environ.setdefault("ADMIN_ID", "1")
MODE = sys.argv[2]
seen = []
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        seen.append((self.path, self.headers.get("X-Internal-Key"), body))
        out = {"reply": {"action": "reply", "reply": "جواب هوش مصنوعی مرکزی ✅"},
               "handoff": {"action": "handoff", "reply": "این رو باید همکارم بررسی کنه 🙏"}}[MODE]
        data = json.dumps(out).encode(); self.send_response(200)
        self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)
srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["CORE_URL"] = f"http://127.0.0.1:{srv.server_port}" if MODE != "down" else "http://127.0.0.1:9"
sys.path.insert(0, sys.argv[1])
import logging; logging.disable(logging.CRITICAL)
import bot as B
async def main():
    await B.init_db(); await B.load_human(); await B.load_data(); await B.load_settings(); await B.load_faq()
    await B.load_unmatched(); await B.load_learn(); await B.load_admins()
    B.settings.update(typing_delay=False)
    handed = []
    async def to_human(update, ctx, **k): handed.append(k.get("ack_lead", "")); return True
    B.forward_to_admin = to_human
    class Msg:
        def __init__(s): s.chat_id = 77; s.message_id = 1; s.replies = []
        async def reply_text(s, t, **k): s.replies.append(t)
    async def nop(*a, **k): return NS(message_id=3)
    u = NS(id=77, first_name="مشتری", username="ali", last_name=None, language_code="fa", is_bot=False)
    await B.save_user(u)
    m = Msg()
    await B.assistant_reply(NS(message=m, effective_user=u, effective_chat=NS(id=77, type="private")),
                            NS(bot=NS(send_chat_action=nop, send_message=nop), user_data={}), "زکخحج قثفغ ضصث", u)
    print(json.dumps({"replies": m.replies, "handed": handed, "seen": seen}, ensure_ascii=False))
    sys.stdout.flush(); os._exit(0)
asyncio.run(main())
'''


def _run_bot(tmp_path, mode):
    data = tmp_path / "data"
    tg = data / "telegram"
    tg.mkdir(parents=True, exist_ok=True)
    (data / "internal.key").write_text("k-123")
    script = tmp_path / "harness.py"
    script.write_text(HARNESS, encoding="utf-8")
    r = subprocess.run([sys.executable, "-u", str(script), str(TG), mode], cwd=tg, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_telegram_asks_core_ai_when_engine_does_not_understand(tmp_path):
    out = _run_bot(tmp_path, "reply")
    assert out["replies"] == ["جواب هوش مصنوعی مرکزی ✅"] and out["handed"] == []
    path, key, body = out["seen"][0]
    assert path == "/internal/think" and key == "k-123" and body["channel"] == "telegram" and body["user_id"] == "77"


def test_telegram_core_handoff_goes_to_team(tmp_path):
    out = _run_bot(tmp_path, "handoff")
    assert out["replies"] == [] and out["handed"] == ["این رو باید همکارم بررسی کنه 🙏"]


def test_telegram_falls_back_when_core_down(tmp_path):
    out = _run_bot(tmp_path, "down")
    assert out["seen"] == [] and len(out["replies"]) == 1 and "متوجه نشدم" in out["replies"][0]
