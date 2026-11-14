"""فایل‌های پنل: فونت از خود برنامه (نه گوگل)، کش بلند برای فایل‌های هش‌دار، بی‌کش برای صفحه‌ی اصلی."""
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.main import create_app
from tests.test_instagram_features import IG

ROOT = Path(__file__).resolve().parent.parent


def test_no_external_font_in_index():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "fonts.googleapis" not in html and "fonts.gstatic" not in html
    assert 'id="boot"' in html                      # پیش‌نمایش فوری به‌جای صفحه‌ی سفید


def test_cache_headers(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>")
    (dist / "sw.js").write_text("//")
    (dist / "assets" / "index-abc.js").write_text("//")
    monkeypatch.setattr(config, "WEB_DIST", str(dist))
    with TestClient(create_app(IG())) as c:
        assert "immutable" in c.get("/assets/index-abc.js").headers["cache-control"]
        assert c.get("/sw.js").headers["cache-control"] == "no-cache"
        assert c.get("/some/route").headers["cache-control"] == "no-cache"
