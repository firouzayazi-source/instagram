"""هم‌پای وردست: سکوت بعد از جواب همکار، انتظار برای چند پیام، یادداشت پست و استوری، گزارش، خبر به تلگرام."""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import ai, auth, brain_engine, config, db, reports, tg_notify, worker
from app.main import create_app
from tests.test_ai import FakeClaude
from tests.test_instagram_features import IG, msg, run

TG = Path(__file__).resolve().parent.parent / "tgbot"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "IG_USER_ID", "me")
    monkeypatch.setattr(config, "SEND_DELAY_MIN", 0)
    monkeypatch.setattr(config, "SEND_DELAY_MAX", 0)
    monkeypatch.setattr(config, "PANEL_PASSWORD", "pw")
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    monkeypatch.setattr(config, "WEB_DIST", str(tmp_path / "nodist"))
    auth._fails.clear()
    db.init()
    fake = FakeClaude()
    ai.set_client(fake)
    with db.connect() as c:
        ai.save_settings(c, {"enabled": True})
    yield fake
    ai.set_client(None)


def echo(mid, text, to="u9"):
    return {"sender": {"id": "me"}, "recipient": {"id": to}, "timestamp": 1, "message": {"mid": mid, "text": text, "is_echo": True}}


@pytest.mark.asyncio
async def test_admin_reply_from_instagram_app_pauses_bot(env):
    ig = IG()
    with db.connect() as c:
        assert await run(ig, c, "e1", "message", msg("m1", "سلام")) == "done"
        # پژواک پیام خود ربات: نادیده
        own = c.execute("SELECT id FROM messages WHERE direction='out'").fetchone()[0]
        assert await run(ig, c, "x1", "message", echo(own, "…")) == "skipped" and not db.human_until(c, "u9")
        # همکار از اپ اینستاگرام جواب داد
        assert await run(ig, c, "x2", "message", echo("adm1", "سلام، من همکار فروشگاهم")) == "admin"
        assert db.human_until(c, "u9") > time.time() + 25 * 60
        assert c.execute("SELECT sender, text FROM messages WHERE id='adm1'").fetchone()[0] == "admin"
        n = len(ig.calls)
        assert await run(ig, c, "e2", "message", msg("m2", "قیمتش چنده؟")) == "human" and len(ig.calls) == n
        db.clear_human(c, "u9")
        assert await run(ig, c, "e3", "message", msg("m3", "هستید؟")) == "done"
        ai.save_settings(c, {"human_pause_minutes": 0})
        await run(ig, c, "x3", "message", echo("adm2", "باز هم همکار"))
        assert not db.human_until(c, "u9")


def test_manual_panel_reply_pauses_and_can_resume(env):
    ig = IG()
    with TestClient(create_app(ig)) as cl:
        cl.post("/api/login", json={"password": "pw"})
        with db.connect() as c:
            db.add_message(c, "in1", "u7", "in", "سلام")
        r = cl.post("/api/conversations/u7/send", json={"text": "سلام از پنل"})
        assert r.status_code == 200, r.text
        assert cl.get("/api/conversations/u7/human").json()["until"] > time.time()
        assert cl.delete("/api/conversations/u7/human").json()["until"] == 0
        with db.connect() as c:
            assert c.execute("SELECT sender FROM messages WHERE direction='out'").fetchone()[0] == "admin"


def _row(eid, sender, text, at):
    return {"id": eid, "kind": "message", "created_at": at,
            "payload": json.dumps({"sender": {"id": sender}, "message": {"mid": eid, "text": text}})}


def test_plan_batches():
    now = 1000.0
    rows = [_row("a", "u1", "سلام", 900), _row("b", "u1", "قیمت ۱۳ پرو", 990), _row("c", "u2", "اقساط؟", 950)]
    assert [(r["id"], s, e) for r, s, e in worker.plan_batches(rows, 0, now)] == [("a", False, None), ("b", False, None), ("c", False, None)]
    plan = worker.plan_batches(rows, 30, now)
    assert [(r["id"], s, e) for r, s, e in plan] == [("c", False, None)]          # u1 هنوز ممکن است بنویسد
    plan = worker.plan_batches(rows, 30, now + 20)
    assert [(r["id"], s, e) for r, s, e in plan] == [("a", True, None), ("b", False, ["سلام"]), ("c", False, None)]


@pytest.mark.asyncio
async def test_batched_messages_get_one_answer(env):
    ig = IG()
    with db.connect() as c:
        for i, t in enumerate(["سلام", "یه سؤال", "۱۳ پرو دارید؟"]):
            db.add_event(c, f"e{i}", "message", msg(f"m{i}", t))
        rows = db.pending_events(c)
        plan = worker.plan_batches(rows, 5, time.time() + 10)
        results = [await worker.handle_event(ig, r, c, extra_texts=e, store_only=s) for r, s, e in plan]
        assert results == ["merged", "merged", "done"] and len(ig.calls) == 1
        assert "سلام\nیه سؤال\n۱۳ پرو دارید؟" in env.calls[-1]["messages"][0]["content"]
        assert c.execute("SELECT COUNT(*) FROM messages WHERE direction='in'").fetchone()[0] == 3


@pytest.mark.asyncio
async def test_story_note_and_product_hint(env, monkeypatch):
    ig = IG()
    seen = {}

    def spy(text, username=None, product_hint="", budget=0):
        seen["hint"] = product_hint
        return None
    monkeypatch.setattr(brain_engine, "decide", spy)
    monkeypatch.setattr(brain_engine, "available", lambda: True)
    with db.connect() as c:
        ai.save_settings(c, {"brain_enabled": True})
        db.set_media_note(c, "s77", "story", "کارکرده، باتری ۹۰٪، با جعبه", "آیفون ۱۲")
        await run(ig, c, "e1", "message", msg("m1", "قیمتش چنده؟", reply_to={"story": {"id": "s77"}}))
    assert seen["hint"] == "آیفون ۱۲"
    prompt = env.calls[-1]["messages"][0]["content"]
    assert "آیفون ۱۲" in prompt and "باتری ۹۰٪" in prompt


def test_open_at(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TG_DATA_DIR", str(tmp_path))
    (tmp_path / "workhours.json").write_text(json.dumps({"enabled": True, "schedule": {
        str(k): {"open": k != 6, "shifts": [{"from": "10:00", "to": "22:00"}]} for k in range(7)}}))
    import pytz
    from datetime import datetime
    tz = pytz.timezone("Asia/Tehran")
    sat_noon = tz.localize(datetime(2026, 10, 31, 12, 0)).timestamp()      # شنبه
    sat_night = tz.localize(datetime(2026, 10, 31, 23, 30)).timestamp()
    fri_noon = tz.localize(datetime(2026, 11, 6, 12, 0)).timestamp()       # جمعه
    assert brain_engine.open_at(sat_noon) is True and brain_engine.open_at(sat_night) is False
    assert brain_engine.open_at(fri_noon) is False


def test_reports(env):
    with db.connect() as c:
        now = time.time()
        db.log_reply(c, "e1", None, "dm", "u1", "جواب ربات", ig_id="b1", ok=True)
        db.log_reply(c, "manual:u2", None, "dm", "u2", "جواب پنل", ig_id="p1", ok=True)
        db.add_message(c, "adm", "u3", "out", "از اپ", sender="admin")
        db.add_message(c, "in1", "u4", "in", "سلام", created_at=now - 2 * 86400)
        db.add_message(c, "in2", "u5", "in", "سلام")
        r = reports.report(c, 30)
    assert r["replies"] == {"bot": 1, "admin": 2, "bot_pct": 33}
    assert r["waiting_24h"] == 1 and r["waiting_open"] == 1 and len(r["series"]) == 14
    assert r["out_of_hours"]["pct"] is None          # ساعت کاری تعریف نشده


NOTIFY = (
    "import os,sys,json,asyncio; os.environ.setdefault('BOT_TOKEN','0:x'); os.environ.setdefault('ADMIN_ID','1');"
    f"sys.path.insert(0,{str(TG)!r}); import logging; logging.disable(logging.CRITICAL); import bot as B\n"
    "from types import SimpleNamespace as NS\n"
    "out=[]\n"
    "class Bot:\n"
    "    async def create_forum_topic(self, gid, name): out.append(('topic', gid, name)); return NS(message_thread_id=55)\n"
    "    async def send_message(self, chat, text, **k): out.append(('send', chat, k.get('message_thread_id'), text))\n"
    "async def main():\n"
    "    await B.load_settings(); B.settings['support_group']=-100123\n"
    "    n = await B.process_ig_notify(Bot())\n"
    "    print(json.dumps({'n': n, 'out': out, 'topic': B.settings.get('ig_topic')}, ensure_ascii=False))\n"
    "asyncio.run(main())")


def test_handoff_goes_to_telegram_topic(env, tmp_path, monkeypatch):
    tg = tmp_path / "tgdata"
    tg.mkdir()
    (tg / "faq.json").write_text("[]")
    monkeypatch.setattr(config, "TG_DATA_DIR", str(tg))
    assert tg_notify.send("🙋 ارجاع اینستاگرام: @ali قیمت ۱۳ پرو")
    r = subprocess.run([sys.executable, "-u", "-c", NOTIFY], cwd=tg, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-1500:]
    d = json.loads(r.stdout.strip().splitlines()[-1])
    assert d["n"] == 1 and d["topic"] == 55
    assert d["out"][0] == ["topic", -100123, "📸 اینستاگرام"] and d["out"][1][1:3] == [-100123, 55]
    assert not list((tg / "notify").glob("*.json"))
