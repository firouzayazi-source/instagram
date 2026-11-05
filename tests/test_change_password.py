"""تغییر رمز از پنل: رمز فعلی لازم است، فقط خط PANEL_PASSWORD عوض می‌شود، دستگاه‌های دیگر خارج می‌شوند."""
import os

import pytest
from fastapi.testclient import TestClient

from app import auth, config, db
from app.main import create_app
from tests.test_instagram_features import IG


@pytest.fixture
def env(tmp_path, monkeypatch):
    e = tmp_path / ".env"
    e.write_text("# تنظیمات\nPANEL_PASSWORD=old-password-1\nIG_ACCESS_TOKEN=keep\n", encoding="utf-8")
    os.chmod(e, 0o600)
    monkeypatch.setenv("IGBOT_ENV_FILE", str(e))
    monkeypatch.setattr(config, "PANEL_PASSWORD", "old-password-1")
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    monkeypatch.setattr(config, "WEB_DIST", str(tmp_path / "nodist"))
    auth._fails.clear()
    db.init()
    return e


def login(pw):
    c = TestClient(create_app(IG()))
    c.__enter__()
    assert c.post("/api/login", json={"password": pw}).status_code == 200
    return c


def test_change_password(env):
    a, b = login("old-password-1"), login("old-password-1")       # دو دستگاه
    try:
        assert a.post("/api/password", json={"current": "wrong", "new": "new-password-22"}).status_code == 401
        assert a.post("/api/password", json={"current": "old-password-1", "new": "abc"}).status_code == 422
        assert a.post("/api/password", json={"current": "old-password-1", "new": "has space inside"}).status_code == 422
        r = a.post("/api/password", json={"current": "old-password-1", "new": "new-password-22"})
        assert r.status_code == 200 and "new-password" not in r.text
        text = env.read_text(encoding="utf-8")
        assert "PANEL_PASSWORD=new-password-22" in text and "IG_ACCESS_TOKEN=keep" in text and "# تنظیمات" in text
        assert "old-password-1" not in text and oct(os.stat(env).st_mode & 0o777) == "0o600"
        assert a.get("/api/me").status_code == 200          # همین دستگاه می‌ماند
        assert b.get("/api/me").status_code == 401          # دستگاه دیگر خارج شد
        assert b.post("/api/login", json={"password": "old-password-1"}).status_code == 401
        assert b.post("/api/login", json={"password": "new-password-22"}).status_code == 200
    finally:
        a.__exit__(None, None, None); b.__exit__(None, None, None)


def test_wrong_current_locks_after_five(env):
    a = login("old-password-1")
    try:
        for _ in range(5):
            a.post("/api/password", json={"current": "nope", "new": "new-password-22"})
        assert a.post("/api/password", json={"current": "old-password-1", "new": "new-password-22"}).status_code == 429
        assert "PANEL_PASSWORD=old-password-1" in env.read_text(encoding="utf-8")
    finally:
        a.__exit__(None, None, None)


def test_requires_login(env):
    with TestClient(create_app(IG())) as c:
        assert c.post("/api/password", json={"current": "old-password-1", "new": "new-password-22"}).status_code == 401


def test_four_char_password_allowed(env):
    a = login("old-password-1")
    try:
        assert a.post("/api/password", json={"current": "old-password-1", "new": "a1b2"}).status_code == 200
        assert "PANEL_PASSWORD=a1b2" in env.read_text(encoding="utf-8")
    finally:
        a.__exit__(None, None, None)


# ---------- ورود با گوگل ----------
import asyncio  # noqa: E402
import time  # noqa: E402

import httpx  # noqa: E402
from fastapi import HTTPException  # noqa: E402

CID = "123456789-abcdefghijkl.apps.googleusercontent.com"


class Req:
    headers = {}
    client = type("C", (), {"host": "1.2.3.4"})()


def google(info, status=200):
    seen = {}

    def h(r):
        seen["token"] = r.url.params.get("id_token")
        return httpx.Response(status, json=info)
    return httpx.MockTransport(h), seen


def good(**kw):
    return {"aud": CID, "iss": "https://accounts.google.com", "email": "Owner@Gmail.com",
            "email_verified": "true", "exp": str(int(time.time()) + 600), **kw}


def setup_google(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", CID, raising=False)
    monkeypatch.setattr(config, "LOGIN_EMAILS", "owner@gmail.com", raising=False)
    auth._fails.clear()
    db.init()


def test_google_login_ok(monkeypatch):
    setup_google(monkeypatch)
    t, seen = google(good())
    token = asyncio.run(auth.google_login(Req(), "jwt-abc", transport=t))
    assert seen["token"] == "jwt-abc" and len(token) > 20
    with db.connect() as c:
        assert db.session_valid(c, token)


@pytest.mark.parametrize("info,msg", [
    (good(email="stranger@gmail.com"), "اجازه"),         # ایمیل غیرمجاز
    (good(aud="other.apps.googleusercontent.com"), "ناموفق"),   # توکن برای اپ دیگری
    (good(email_verified="false"), "ناموفق"),
    (good(exp=str(int(time.time()) - 5)), "ناموفق"),     # منقضی
    (good(iss="https://evil.example"), "ناموفق"),
])
def test_google_login_rejected(monkeypatch, info, msg):
    setup_google(monkeypatch)
    t, _ = google(info)
    with pytest.raises(HTTPException) as e:
        asyncio.run(auth.google_login(Req(), "jwt", transport=t))
    assert e.value.status_code == 401 and msg in e.value.detail


def test_google_disabled_without_config(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "", raising=False)
    monkeypatch.setattr(config, "LOGIN_EMAILS", "", raising=False)
    with pytest.raises(HTTPException) as e:
        asyncio.run(auth.google_login(Req(), "jwt"))
    assert e.value.status_code == 409


def test_google_public_config_hides_emails(env, monkeypatch):
    setup_google(monkeypatch)
    with TestClient(create_app(IG())) as c:
        d = c.get("/api/login/google").json()
        assert d == {"enabled": True, "client_id": CID}
        assert "gmail" not in c.get("/api/login/google").text


def test_google_settings_validated(env):
    from app import secrets_env
    with pytest.raises(ValueError):
        secrets_env.set_value("GOOGLE_CLIENT_ID", "not-a-client-id")
    with pytest.raises(ValueError):
        secrets_env.set_value("LOGIN_EMAILS", "bad email")
    secrets_env.set_value("LOGIN_EMAILS", " A@Gmail.com , b@x.ir ")
    assert "LOGIN_EMAILS=a@gmail.com,b@x.ir" in env.read_text(encoding="utf-8")
    secrets_env.set_value("LOGIN_EMAILS", "")
    config.LOGIN_EMAILS = ""
