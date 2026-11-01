import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.main import create_app
from tests.test_webhook import COMMENT, MESSAGE, FakeIG


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "PANEL_PASSWORD", "pw123")
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    monkeypatch.setattr(config, "IG_USER_ID", "me")
    monkeypatch.setattr(config, "WEB_DIST", str(tmp_path / "nodist"))
    from app import auth
    auth._fails.clear()
    db.init()
    fake = FakeIG()
    with TestClient(create_app(fake)) as c:
        c.ig = fake
        yield c


def login(c):
    assert c.post("/api/login", json={"password": "pw123"}).status_code == 200


def test_auth_required_and_lockout(client):
    assert client.get("/api/stats").status_code == 401
    for _ in range(5):
        assert client.post("/api/login", json={"password": "bad"}).status_code == 401
    assert client.post("/api/login", json={"password": "pw123"}).status_code == 429


def test_login_logout(client):
    login(client)
    assert client.get("/api/me").json()["ok"]
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/me").status_code == 401


def test_rules_crud_and_test(client):
    login(client)
    bad = client.post("/api/rules", json={"name": "x", "channels": ["comment"], "actions": {}})
    assert bad.status_code == 422
    r = client.post("/api/rules", json={"name": "تقویم", "channels": ["comment"],
                                        "triggers": [{"match": "contains", "value": "تقویم"}],
                                        "actions": {"public_replies": ["چک کن دایرکت"]}})
    rid = r.json()["id"]
    assert client.post("/api/rules/test", json={"channel": "comment", "text": "تقويم رو میخوام"}).json()["rule"]["id"] == rid
    assert client.post("/api/rules/test", json={"channel": "dm", "text": "تقویم"}).json()["rule"] is None
    assert client.get("/api/saved-replies").json() == ["چک کن دایرکت"]
    client.post(f"/api/rules/{rid}/enable", json={"enabled": False})
    assert client.get("/api/rules").json()[0]["enabled"] == 0
    assert client.post("/api/rules/test", json={"channel": "comment", "text": "تقویم"}).json()["rule"] is None
    client.delete(f"/api/rules/{rid}")
    assert client.get("/api/rules").json() == []


def test_inbox_flow(client):
    from app import worker
    login(client)
    with db.connect() as c:
        db.add_event(c, "c:c100", "comment", COMMENT["entry"][0]["changes"][0]["value"])
        db.add_event(c, "m:mid1", "message", MESSAGE["entry"][0]["messaging"][0])
        import asyncio

        async def run_all():
            for row in db.pending_events(c):
                await worker.handle_event(client.ig, row, c)
        asyncio.run(run_all())
    cs = client.get("/api/comments", params={"filter": "unanswered"}).json()
    assert len(cs) == 1 and cs[0]["username"] == "x" and cs[0]["read"] == 0
    assert client.post("/api/comments/c100/reply", json={"text": "ممنون"}).json()["ok"]
    assert client.get("/api/comments", params={"filter": "unanswered"}).json() == []
    assert client.get("/api/comments", params={"filter": "answered"}).json()[0]["read"] == 1

    convs = client.get("/api/conversations", params={"filter": "unread"}).json()
    assert len(convs) == 1 and convs[0]["username"] == "user_u2" and convs[0]["last_text"] == "قیمت"
    msgs = client.get("/api/conversations/u2/messages").json()
    assert [m["direction"] for m in msgs] == ["in"]
    assert client.get("/api/conversations", params={"filter": "unread"}).json() == []
    assert client.post("/api/conversations/u2/send", json={"text": "سلام"}).json()["ok"]
    assert [m["direction"] for m in client.get("/api/conversations/u2/messages").json()] == ["in", "out"]
    assert client.get("/api/conversations", params={"filter": "unanswered"}).json() == []
    s = client.get("/api/stats").json()
    assert s["replies_ok_24h"] == 2 and s["comments_24h"] == 1


def test_media_and_settings(client):
    login(client)
    assert client.get("/api/media").json()[0]["id"] == "m1"
    assert client.get("/api/settings").json()["push_mode"] == "unanswered"
    assert client.put("/api/settings", json={"push_mode": "all"}).status_code == 200
    assert client.put("/api/settings", json={"push_mode": "x"}).status_code == 422
    sub = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "AAA", "auth": "BBB"}}
    assert client.post("/api/push/subscribe", json=sub).status_code == 200
    with db.connect() as c:
        assert len(db.push_subs(c)) == 1
    client.request("DELETE", "/api/push/subscribe", json={"endpoint": sub["endpoint"]})
    with db.connect() as c:
        assert db.push_subs(c) == []
