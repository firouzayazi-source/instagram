"""کلید سرویس‌های هوش مصنوعی از پنل: در ‎.env‎ نوشته می‌شود، هرگز برنمی‌گردد، فقط نام‌های مجاز."""
import os

import pytest
from fastapi.testclient import TestClient

from app import ai, auth, config, db
from app.main import create_app
from tests.test_instagram_features import IG


@pytest.fixture
def cl(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# تنظیمات\nPANEL_PASSWORD=pw\nANTHROPIC_API_KEY=old-key-1234567\nIG_ACCESS_TOKEN=secret-ig\n", encoding="utf-8")
    os.chmod(env, 0o600)
    monkeypatch.setenv("IGBOT_ENV_FILE", str(env))
    monkeypatch.setattr(config, "PANEL_PASSWORD", "pw")
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    monkeypatch.setattr(config, "WEB_DIST", str(tmp_path / "nodist"))
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "old-key-1234567")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "CUSTOM_AI_BASE_URL", "")
    for k in ("OPENAI_API_KEY", "CUSTOM_AI_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    auth._fails.clear()
    db.init()
    ai.set_client(None)
    with TestClient(create_app(IG())) as c:
        assert c.get("/api/ai/keys").status_code == 401
        c.post("/api/login", json={"password": "pw"})
        c.env = env
        yield c


def test_keys_written_to_env_never_returned(cl):
    items = {x["name"]: x for x in cl.get("/api/ai/keys").json()["items"]}
    assert items["ANTHROPIC_API_KEY"] == {**items["ANTHROPIC_API_KEY"], "set": True, "hint": "…4567"}
    assert "old-key" not in cl.get("/api/ai/keys").text
    r = cl.put("/api/ai/keys/OPENAI_API_KEY", json={"value": "sk-test-abcdefgh9999"})
    assert r.status_code == 200 and "sk-test" not in r.text
    assert next(p for p in r.json()["providers"] if p["id"] == "openai")["configured"]
    text = cl.env.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-test-abcdefgh9999" in text and "IG_ACCESS_TOKEN=secret-ig" in text and "# تنظیمات" in text
    assert oct(os.stat(cl.env).st_mode & 0o777) == "0o600" and config.OPENAI_API_KEY == "sk-test-abcdefgh9999"
    # جایگزینی و حذف
    cl.put("/api/ai/keys/ANTHROPIC_API_KEY", json={"value": "new-key-7654321"})
    assert cl.env.read_text(encoding="utf-8").count("ANTHROPIC_API_KEY=") == 1 and "new-key-7654321" in cl.env.read_text()
    cl.put("/api/ai/keys/OPENAI_API_KEY", json={"value": ""})
    assert "OPENAI_API_KEY" not in cl.env.read_text() and not config.OPENAI_API_KEY


def test_keys_validation(cl):
    assert cl.put("/api/ai/keys/IG_ACCESS_TOKEN", json={"value": "x" * 20}).status_code == 422
    assert cl.put("/api/ai/keys/PANEL_PASSWORD", json={"value": "x" * 20}).status_code == 422
    assert cl.put("/api/ai/keys/OPENAI_API_KEY", json={"value": "bad key\nIG_ACCESS_TOKEN=x"}).status_code == 422
    assert cl.put("/api/ai/keys/CUSTOM_AI_BASE_URL", json={"value": "http://evil.example/v1"}).status_code == 422
    assert cl.put("/api/ai/keys/CUSTOM_AI_BASE_URL", json={"value": "http://127.0.0.1:11434/v1"}).status_code == 200
    assert "IG_ACCESS_TOKEN=secret-ig" in cl.env.read_text() and cl.env.read_text().count("IG_ACCESS_TOKEN") == 1
