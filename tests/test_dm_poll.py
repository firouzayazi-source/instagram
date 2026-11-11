"""خوانش دایرکت با Composio: فقط پیام‌های تازه، echo برای پیام خود پیج، پیش‌فرض فقط صندوق."""
import asyncio
import json
from datetime import datetime, timezone

import pytest

from app import comment_poll, config, db, worker

T0 = 1_800_000_000.0


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")


class DmIG:
    def __init__(self):
        self.user_id = "me"
        self.convs = [{"id": "cv1", "updated_time": iso(T0 - 100)}]
        self.msgs = {"cv1": [{"id": "old", "created_time": iso(T0 - 100), "from": {"id": "u1", "username": "ali"}, "message": "قدیمی"}]}
        self.gets = []

    def via_composio(self):
        return True

    async def _get(self, path, **params):
        self.gets.append(path)
        if path == "me":
            return {"username": "stock_land.ir"}
        if path == "me/conversations":
            return {"data": self.convs}
        return {"data": self.msgs[path.split("/")[0]]}


def events(c):
    return {r["id"]: json.loads(r["payload"]) for r in c.execute("SELECT * FROM events")}


def test_only_new_messages_and_echo():
    ig = DmIG()
    db.init()
    with db.connect() as c:
        assert asyncio.run(comment_poll.poll_dms_once(ig, c, now=T0)) == {"queued": 0, "checked": 0}
        assert "cv1/messages" not in ig.gets                      # بار اول: فقط نقطه‌ی شروع
        ig.convs[0]["updated_time"] = iso(T0 + 50)
        ig.msgs["cv1"] = [
            {"id": "m3", "created_time": iso(T0 + 50), "from": {"id": "page", "username": "stock_land.ir"},
             "to": {"data": [{"id": "u1", "username": "ali"}]}, "message": "جواب همکار"},
            {"id": "m2", "created_time": iso(T0 + 40), "from": {"id": "u1", "username": "ali"}, "message": "قیمت ۱۳؟",
             "story": {"reply_to": {"id": "st9", "link": "x"}}},
            {"id": "old", "created_time": iso(T0 - 100), "from": {"id": "u1", "username": "ali"}, "message": "قدیمی"}]
        assert asyncio.run(comment_poll.poll_dms_once(ig, c, now=T0 + 60)) == {"queued": 2, "checked": 1}
        ev = events(c)
        assert set(ev) == {"m:m2", "m:m3"}
        assert ev["m:m2"]["sender"] == {"id": "u1", "username": "ali"} and ev["m:m2"]["message"]["reply_to"]["story"]["id"] == "st9"
        assert ev["m:m3"]["message"]["is_echo"] and ev["m:m3"]["recipient"]["id"] == "u1"
        n = len(ig.gets)
        assert asyncio.run(comment_poll.poll_dms_once(ig, c, now=T0 + 120))["checked"] == 0   # تازه نشده: خوانده نمی‌شود
        assert ig.gets[n:] == ["me/conversations"]


@pytest.fixture
def wenv(monkeypatch):
    from tests.test_instagram_features import IG
    monkeypatch.setattr(config, "SEND_DELAY_MIN", 0)
    monkeypatch.setattr(config, "SEND_DELAY_MAX", 0)
    db.init()
    return IG()


@pytest.mark.asyncio
async def test_polled_dm_inbox_only_until_enabled(wenv):
    with db.connect() as c:
        db.upsert_rule(c, {"name": "قیمت", "channels": ["dm"], "triggers": [{"match": "contains", "value": "قیمت"}],
                           "actions": {"dm_replies": ["لینک ربات"]}})
        def ev(mid):
            return {"sender": {"id": "u1", "username": "ali"}, "timestamp": int(T0 * 1000),
                    "message": {"mid": mid, "text": "قیمت"}, "_via": "poll"}
        db.add_event(c, "m:a1", "message", ev("a1"))
        assert await worker.handle_event(wenv, db.pending_events(c)[0], c) == "skipped"
        assert wenv.calls == [] and db.conversation_username(c, "u1") == "ali"
        assert c.execute("SELECT COUNT(*) FROM messages WHERE direction='in'").fetchone()[0] == 1
        db.kv_set(c, comment_poll.DM_REPLY_KEY, "1")
        db.add_event(c, "m:a2", "message", ev("a2"))
        row = [r for r in db.pending_events(c) if r["id"] == "m:a2"][0]
        assert await worker.handle_event(wenv, row, c) == "done"
    assert [x[:2] for x in wenv.calls if x[0] == "dm"] == [("dm", "u1")]


@pytest.mark.asyncio
async def test_polled_echo_pauses_bot(wenv):
    with db.connect() as c:
        db.add_event(c, "m:e1", "message", {"sender": {"id": "page"}, "recipient": {"id": "u1"}, "timestamp": int(T0 * 1000),
                                            "message": {"mid": "e1", "text": "سلام", "is_echo": True}, "_via": "poll"})
        assert await worker.handle_event(wenv, db.pending_events(c)[0], c) == "admin"
        assert db.human_until(c, "u1") > 0


@pytest.mark.asyncio
async def test_polled_echo_of_bot_message_is_not_a_human(wenv):
    with db.connect() as c:
        db.add_message(c, "sent-1", "u1", "out", "لینک ربات", sender="bot")
        db.add_event(c, "m:e2", "message", {"sender": {"id": "page"}, "recipient": {"id": "u1"}, "timestamp": 1,
                                            "message": {"mid": "other-id", "text": "لینک ربات", "is_echo": True}, "_via": "poll"})
        assert await worker.handle_event(wenv, db.pending_events(c)[0], c) == "skipped"
        assert db.human_until(c, "u1") == 0
