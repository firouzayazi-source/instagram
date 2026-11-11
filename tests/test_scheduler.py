"""زمان‌بندی انتشار: اعتبارسنجی، انتشار سر وقت و فقط یک بار، دیر منتشر نکردن، لغو و فایل عمومی."""
import asyncio
import time

import pytest

from app import config, db, scheduler

NOW = 1_800_000_000.0


class PubIG:
    user_id = "me"

    def __init__(self, status="FINISHED"):
        self.posts, self.status = [], status

    async def _post(self, path, **kw):
        self.posts.append((path, kw.get("json")))
        return {"id": "cont1" if path.endswith("/media") else "ig99"}

    async def _get(self, path, **params):
        return {"status_code": self.status} if path == "cont1" else {"permalink": "https://instagram.com/p/x"}


async def chunks(*parts):
    for p in parts:
        yield p


def upload(name="a.jpg", data=b"x" * 10):
    return asyncio.run(scheduler.save_upload(chunks(data), name))["file"]


def test_upload_and_validation(monkeypatch):
    db.init()
    with pytest.raises(ValueError, match="JPG"):
        upload("a.png")
    with pytest.raises(ValueError, match="خالی"):
        upload("a.jpg", b"")
    monkeypatch.setattr(scheduler, "MAX_BYTES", 5)
    with pytest.raises(ValueError, match="حجم"):
        upload("a.mp4")
    assert not list(scheduler.uploads_dir().iterdir())            # فایل ناقص نمی‌ماند
    monkeypatch.setattr(scheduler, "MAX_BYTES", 1000)
    img, vid = upload("a.JPG"), upload("b.mp4")
    assert scheduler.file_path(img) and scheduler.file_path("../bot.db") is None and scheduler.file_path("x.jpg") is None
    with db.connect() as c:
        for kind, f, at, msg in (("reel", img, NOW + 3600, "ویدیو باشد"), ("post", vid, NOW + 3600, "ریلز"),
                                 ("post", img, NOW + 10, "یک دقیقه"), ("x", img, NOW + 3600, "نامعتبر"),
                                 ("post", "0" * 32 + ".jpg", NOW + 3600, "پیدا نشد")):
            with pytest.raises(ValueError, match=msg):
                scheduler.create(c, kind, f, "", at, now=NOW)
        assert scheduler.create(c, "story", img, "کپشن استوری ندارد", NOW + 3600, now=NOW) == 1
        assert scheduler.listing(c)[0]["caption"] == "" and scheduler.listing(c)[0]["preview"].startswith("/media/")


def test_publishes_on_time_once(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_URL", "https://example.test")
    db.init()
    img, vid = upload("a.jpg"), upload("b.mp4")
    with db.connect() as c:
        scheduler.create(c, "post", img, "سلام", NOW + 600, now=NOW)
        scheduler.create(c, "reel", vid, "ریلز", NOW + 7200, now=NOW)
    ig = PubIG()
    assert asyncio.run(scheduler.run_due(ig, now=NOW + 300)) == 0 and ig.posts == []     # هنوز زود است
    assert asyncio.run(scheduler.run_due(ig, now=NOW + 601, wait=0)) == 1
    assert ig.posts == [("me/media", {"image_url": f"https://example.test/media/{img}", "caption": "سلام"}),
                        ("me/media_publish", {"creation_id": "cont1"})]
    assert asyncio.run(scheduler.run_due(ig, now=NOW + 700, wait=0)) == 0 and len(ig.posts) == 2   # دوباره منتشر نمی‌شود
    assert asyncio.run(scheduler.run_due(ig, now=NOW + 7201, wait=0)) == 1
    assert ig.posts[2][1] == {"video_url": f"https://example.test/media/{vid}", "media_type": "REELS", "caption": "ریلز"}
    with db.connect() as c:
        rows = {r["kind"]: r for r in scheduler.listing(c)}
    assert rows["post"]["status"] == "done" and rows["post"]["permalink"] and rows["reel"]["ig_id"] == "ig99"


def test_late_failed_canceled_and_error():
    db.init()
    img = upload("a.jpg")
    with db.connect() as c:
        late = scheduler.create(c, "story", img, "", NOW + 600, now=NOW)
        bad = scheduler.create(c, "post", img, "", NOW + 7200, now=NOW)
        gone = scheduler.create(c, "post", img, "", NOW + 7200, now=NOW)
        assert scheduler.cancel(c, gone) and not scheduler.cancel(c, gone)
    ig = PubIG(status="ERROR")
    assert asyncio.run(scheduler.run_due(ig, now=NOW + 600 + scheduler.LATE_LIMIT + 1, wait=0)) == 0
    assert ig.posts == []                                              # دیر منتشر نمی‌کند
    assert asyncio.run(scheduler.run_due(ig, now=NOW + 7201, wait=0)) == 0
    with db.connect() as c:
        st = {r["id"]: r for r in scheduler.listing(c)}
    assert st[late]["status"] == "failed" and "گذشته" in st[late]["error"]
    assert st[bad]["status"] == "failed" and "نپذیرفت" in st[bad]["error"] and st[gone]["status"] == "canceled"
    assert [p for p, _ in ig.posts] == ["me/media"]                    # خطا: مرحله‌ی انتشار اجرا نشد


def test_api_and_public_file(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import auth
    from app.main import create_app
    from tests.test_instagram_features import IG
    monkeypatch.setattr(config, "PANEL_PASSWORD", "pw")
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    monkeypatch.setattr(config, "WEB_DIST", str(tmp_path / "nodist"))
    auth._fails.clear()
    db.init()
    with TestClient(create_app(IG())) as cl:
        assert cl.post("/api/schedule/upload?name=a.jpg", content=b"img").status_code == 401
        cl.post("/api/login", json={"password": "pw"})
        f = cl.post("/api/schedule/upload?name=a.jpg", content=b"img").json()["file"]
        assert cl.post("/api/schedule", json={"kind": "reel", "file": f, "publish_at": time.time() + 3600}).status_code == 422
        r = cl.post("/api/schedule", json={"kind": "post", "file": f, "caption": "c", "publish_at": time.time() + 3600}).json()
        assert cl.get("/api/schedule").json()[0]["status"] == "scheduled"
        cl.post("/api/logout")
        assert cl.get(f"/media/{f}").content == b"img"                 # اینستاگرام بدون ورود برمی‌دارد
        assert cl.get("/media/..%2Fbot.db").status_code == 404
        cl.post("/api/login", json={"password": "pw"})
        assert cl.post(f"/api/schedule/{r['id']}/cancel").json() == {"ok": True}
        assert cl.post(f"/api/schedule/{r['id']}/cancel").status_code == 409
