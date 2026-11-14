"""دستگاه‌های شناخته‌شده: اولین دستگاه خودکار، دستگاه تازه منتظر تأیید، برداشتن دستگاه، قفل ماندگار."""
import pytest
from fastapi.testclient import TestClient

from app import auth, config, db, tg_notify
from app.main import create_app
from tests.test_instagram_features import IG

UA_IPHONE = {"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit Version/18.0 Mobile Safari/604.1"}
UA_WIN = {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64) Chrome/130.0 Safari/537.36"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PANEL_PASSWORD", "good-password")
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    monkeypatch.setattr(config, "WEB_DIST", str(tmp_path / "nodist"))
    sent = []
    monkeypatch.setattr(tg_notify, "send", lambda t, *a, **k: sent.append(t) or True)
    db.init()
    return sent


def client(headers):
    c = TestClient(create_app(IG()), headers=headers)
    c.__enter__()
    return c


def test_first_device_trusted_new_device_waits_for_approval(env):
    phone, pc = client(UA_IPHONE), client(UA_WIN)
    try:
        assert phone.post("/api/login", json={"password": "good-password"}).status_code == 200
        assert "اولین دستگاه" in env[-1]
        r = pc.post("/api/login", json={"password": "good-password"})
        assert r.status_code == 403 and r.json()["pending"]
        assert pc.get("/api/me").status_code == 401                       # بی‌تأیید، ورودی ساخته نشد
        assert "درخواست ورود" in env[-1] and "ویندوز" in env[-1] and "good-password" not in env[-1]
        d = phone.get("/api/devices").json()
        pend = [x for x in d["items"] if x["status"] == "pending"]
        assert d["lock"] and len(pend) == 1 and pend[0]["name"] == "ویندوز Chrome"
        assert [x for x in d["items"] if x["current"]][0]["name"] == "آیفون Safari"
        phone.post(f"/api/devices/{pend[0]['id']}/approve")
        assert pc.post("/api/login", json={"password": "good-password"}).status_code == 200
        assert pc.get("/api/me").status_code == 200
        # برداشتن دستگاه: ورودش همان لحظه باطل و دیگر با رمز هم وارد نمی‌شود
        assert phone.post(f"/api/devices/{pend[0]['id']}/revoke").status_code == 200
        assert pc.get("/api/me").status_code == 401
        assert pc.post("/api/login", json={"password": "good-password"}).status_code == 403
        cur = [x for x in phone.get("/api/devices").json()["items"] if x["current"]][0]
        assert phone.post(f"/api/devices/{cur['id']}/revoke").status_code == 409   # دستگاه خودتان نه
    finally:
        phone.__exit__(None, None, None); pc.__exit__(None, None, None)


def test_lock_off_lets_new_device_in(env):
    a, b = client(UA_IPHONE), client(UA_WIN)
    try:
        a.post("/api/login", json={"password": "good-password"})
        a.put("/api/devices/lock", json={"on": False})
        assert b.post("/api/login", json={"password": "good-password"}).status_code == 200
    finally:
        a.__exit__(None, None, None); b.__exit__(None, None, None)


def test_legacy_session_becomes_trusted_device(env):
    with db.connect() as c:
        db.add_session(c, "legacy-token-1234567890", 3600)        # ورود قبل از انتشار، بی دستگاه
    with TestClient(create_app(IG()), headers=UA_IPHONE, cookies={"session": "legacy-token-1234567890"}) as c:
        r = c.get("/api/me")
        assert r.status_code == 200 and "device=" in r.headers.get("set-cookie", "")
        assert c.get("/api/devices").json()["items"][0]["status"] == "trusted"


def test_failed_logins_lock_persists(env):
    with client(UA_IPHONE) as a:
        for _ in range(5):
            assert a.post("/api/login", json={"password": "nope"}).status_code == 401
        assert a.post("/api/login", json={"password": "good-password"}).status_code == 429
    with db.connect() as c:                                           # در پایگاه داده، نه حافظه (ری‌استارت پاکش نمی‌کند)
        assert c.execute("SELECT until FROM login_fails").fetchone()[0] > 0


def test_weak_password_flag(env, monkeypatch):
    monkeypatch.setattr(config, "PANEL_PASSWORD", "1234")
    assert auth.weak_password()
    monkeypatch.setattr(config, "PANEL_PASSWORD", "12345678")
    assert not auth.weak_password()
