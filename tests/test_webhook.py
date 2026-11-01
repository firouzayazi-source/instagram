import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app import config, db, worker
from app.main import create_app, extract_events


class FakeIG:
    def __init__(self):
        self.token = "t"
        self.calls = []

    async def reply_comment(self, cid, text):
        self.calls.append(("public", cid, text))
        return "r1"

    async def private_reply(self, cid, text):
        self.calls.append(("private", cid, text))
        return "p1"

    async def send_dm(self, uid, text):
        self.calls.append(("dm", uid, text))
        return "d1"

    async def is_follower(self, uid):
        return uid == "follower"

    async def profile(self, uid):
        return {"username": f"user_{uid}", "is_user_follow_business": uid == "follower"}

    async def media(self, limit=50):
        return [{"id": "m1", "caption": "پست یک"}]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "IG_APP_SECRET", "secret")
    monkeypatch.setattr(config, "IG_VERIFY_TOKEN", "verify")
    monkeypatch.setattr(config, "IG_USER_ID", "me")
    monkeypatch.setattr(config, "SEND_DELAY_MIN", 0)
    monkeypatch.setattr(config, "SEND_DELAY_MAX", 0)
    db.init()
    return FakeIG()


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()


COMMENT = {
    "entry": [{"changes": [{"field": "comments", "value": {
        "id": "c100", "text": "تقویم", "from": {"id": "u1", "username": "x"}, "media": {"id": "m1"}}}]}]
}
MESSAGE = {"entry": [{"messaging": [{"sender": {"id": "u2"}, "recipient": {"id": "me"},
                                      "message": {"mid": "mid1", "text": "قیمت"}}]}]}


def test_verify_handshake(env):
    with TestClient(create_app(env)) as client:
        ok = client.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verify", "hub.challenge": "123"})
        assert ok.status_code == 200 and ok.text == "123"
        assert client.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"}).status_code == 403


def test_signature_required_and_dedupe(env):
    body = json.dumps(COMMENT).encode()
    with TestClient(create_app(env)) as client:
        assert client.post("/webhook", content=body).status_code == 403
        assert client.post("/webhook", content=body, headers={"X-Hub-Signature-256": "sha256=bad"}).status_code == 403
        assert client.post("/webhook", content=body, headers={"X-Hub-Signature-256": sign(body)}).json() == {"queued": 1}
        assert client.post("/webhook", content=body, headers={"X-Hub-Signature-256": sign(body)}).json() == {"queued": 0}


def test_extract_events():
    assert [e[:2] for e in extract_events(COMMENT)] == [("c:c100", "comment")]
    assert [e[:2] for e in extract_events(MESSAGE)] == [("m:mid1", "message")]


@pytest.mark.asyncio
async def test_worker_comment_sends_private_and_public(env):
    with db.connect() as c:
        db.upsert_rule(c, {"name": "تقویم", "channels": ["comment"], "triggers": [{"match": "contains", "value": "تقویم"}],
                           "actions": {"public_replies": ["چک کن دایرکت"], "private_replies": ["لینک: x"]}})
        db.add_event(c, "c:c100", "comment", COMMENT["entry"][0]["changes"][0]["value"])
        row = db.pending_events(c)[0]
        assert await worker.handle_event(env, row, c) == "done"
        assert db.last_hit(c, 1, "u1") is not None
        assert c.execute("SELECT COUNT(*) FROM replies WHERE ok=1").fetchone()[0] == 2
    assert env.calls == [("private", "c100", "لینک: x"), ("public", "c100", "چک کن دایرکت")]


@pytest.mark.asyncio
async def test_worker_dm_and_skips(env):
    with db.connect() as c:
        db.upsert_rule(c, {"name": "قیمت", "channels": ["dm"], "triggers": [{"match": "exact", "value": "قیمت"}],
                           "actions": {"dm_replies": ["بزودی تماس می‌گیریم"]}})
        db.add_event(c, "m:mid1", "message", MESSAGE["entry"][0]["messaging"][0])
        echo = {"sender": {"id": "me"}, "message": {"mid": "e1", "text": "x", "is_echo": True}}
        db.add_event(c, "m:e1", "message", echo)
        rows = db.pending_events(c)
        assert await worker.handle_event(env, rows[0], c) == "done"
        assert await worker.handle_event(env, rows[1], c) == "skipped"
    assert env.calls == [("dm", "u2", "بزودی تماس می‌گیریم")]


@pytest.mark.asyncio
async def test_followup_scheduled_and_sent_when_due(env):
    import time
    with db.connect() as c:
        db.upsert_rule(c, {"name": "x", "channels": ["dm"], "triggers": [{"match": "any"}],
                           "actions": {"dm_replies": ["سلام"]},
                           "advanced": {"followup": {"after_seconds": 3600, "text": "هنوز سوالی داری؟"}}})
        db.add_event(c, "m:mid1", "message", MESSAGE["entry"][0]["messaging"][0])
        await worker.handle_event(env, db.pending_events(c)[0], c)
        assert await worker.process_followups(env, c) == 0            # هنوز سررسید نشده
        assert await worker.process_followups(env, c, now=time.time() + 3601) == 1
        assert await worker.process_followups(env, c, now=time.time() + 7200) == 0  # دوباره نمی‌فرستد
    assert env.calls[-1] == ("dm", "u2", "هنوز سوالی داری؟")


@pytest.mark.asyncio
async def test_require_follow(env):
    with db.connect() as c:
        db.upsert_rule(c, {"name": "x", "channels": ["comment"], "actions": {"private_replies": ["لینک"]},
                           "advanced": {"require_follow": True, "follow_prompt": "اول فالو کن"}})
        db.add_event(c, "c:c100", "comment", COMMENT["entry"][0]["changes"][0]["value"])
        await worker.handle_event(env, db.pending_events(c)[0], c)
    assert env.calls == [("public", "c100", "اول فالو کن")]
