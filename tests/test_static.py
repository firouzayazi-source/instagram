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
    assert 'id="splash"' in html and "<svg" in html    # صفحه‌ی انتظار با لوگو، داخل همان فایل (بی درخواست اضافه)


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


def test_precompressed_assets_and_api_gzip(tmp_path, monkeypatch):
    import gzip
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>")
    body = b"console.log('x');" * 200
    (dist / "assets" / "index-abc.js").write_bytes(body)
    (dist / "assets" / "index-abc.js.gz").write_bytes(gzip.compress(body))
    monkeypatch.setattr(config, "WEB_DIST", str(dist))
    with TestClient(create_app(IG())) as c:
        r = c.get("/assets/index-abc.js", headers={"accept-encoding": "gzip"})
        assert r.headers["content-encoding"] == "gzip" and "javascript" in r.headers["content-type"] and r.content == body
        assert "content-encoding" not in c.get("/assets/index-abc.js", headers={"accept-encoding": "identity"}).headers


def test_missing_asset_is_404_not_index(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>")
    monkeypatch.setattr(config, "WEB_DIST", str(dist))
    with TestClient(create_app(IG())) as c:
        assert c.get("/assets/RuleForm-old.js").status_code == 404          # نسخه‌ی قبلی: نه index.html
        assert c.get("/rules/new").status_code == 200                       # مسیرهای پنل همچنان index.html
