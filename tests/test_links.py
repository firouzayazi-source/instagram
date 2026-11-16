"""لینک ردیابی‌شده، نام کاربر در پیام، و دکمه‌ی لینک در دایرکت."""
import pytest
from fastapi.testclient import TestClient

from app import config, db, links, worker
from app.main import create_app
from tests.test_instagram_features import IG


def test_personalize():
    assert links.personalize("سلام {username} 🌸", "ali") == "سلام ali 🌸"
    assert links.personalize("سلام {username} عزیز", None) == "سلام عزیز"
    assert links.personalize("بی‌نام", "x") == "بی‌نام"


def test_track_text_stable_and_punctuation():
    db.init()
    with db.connect() as c:
        t1 = links.track_text(c, "اینجا: https://stland.ir/p/1.", 5)
        t2 = links.track_text(c, "دوباره https://stland.ir/p/1", 5)
        assert t1.endswith(".") and "/l/" in t1 and t1.split()[-1][:-1] == t2.split()[-1]   # کد ثابت، نقطه بیرون
        assert links.track_text(c, t2, 5) == t2                                            # دو بار پیچیده نمی‌شود


def test_click_redirect_and_stats(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "WEB_DIST", str(tmp_path / "nodist"))
    db.init()
    with db.connect() as c:
        code = links.short(c, "https://stland.ir/x", 7).rsplit("/", 1)[1]
    with TestClient(create_app(IG()), follow_redirects=False) as cl:
        for _ in range(3):
            r = cl.get(f"/l/{code}")
            assert r.status_code in (302, 307) and r.headers["location"] == "https://stland.ir/x"
        assert cl.get("/l/zzzzzzzz").status_code == 404
        assert cl.get("/l/../etc").status_code == 404
    with db.connect() as c:
        assert links.rule_clicks(c) == {7: {"clicks": 3, "people": 1}}
        assert not c.execute("SELECT 1 FROM link_clicks WHERE visitor LIKE '%testclient%'").fetchone()   # IP خام نیست


def test_buttons_validation():
    assert links.clean_buttons([{"title": "سایت", "url": "https://stland.ir"}, {"title": "", "url": ""}]) == [{"title": "سایت", "url": "https://stland.ir"}]
    with pytest.raises(ValueError):
        links.clean_buttons([{"title": "x", "url": "http://a"}])


class BtnIG(IG):
    def __init__(self, fail=False):
        super().__init__()
        self.fail, self.btn = fail, []

    async def private_reply(self, cid, text, buttons=None):
        if buttons and self.fail:
            raise RuntimeError("IG 400 template not supported")
        self.btn.append(buttons)
        self.calls.append(("private", cid, text))
        return "p"


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_private_reply_with_buttons_and_fallback(monkeypatch, fail):
    monkeypatch.setattr(config, "SEND_DELAY_MIN", 0)
    monkeypatch.setattr(config, "SEND_DELAY_MAX", 0)
    db.init()
    ig = BtnIG(fail)
    with db.connect() as c:
        db.upsert_rule(c, {"name": "x", "channels": ["comment"], "triggers": [{"match": "any"}],
                           "actions": {"comment_mode": "dm", "private_replies": ["سلام {username}"],
                                       "buttons": [{"title": "🌐 سایت", "url": "https://stland.ir"}]}})
        db.add_event(c, "c:b1", "comment", {"id": "b1", "text": "x", "from": {"id": "u1", "username": "ali"}, "media": {"id": "p"}})
        assert await worker.handle_event(ig, db.pending_events(c)[0], c) == "done"
    text = ig.calls[-1][2]
    if fail:     # دکمه رد شد: همان پیام با لینک در متن
        assert text.startswith("سلام ali") and "🌐 سایت: https://stland.ir" in text and "/l/" not in text and ig.btn == [None]
    else:
        assert text == "سلام ali" and ig.btn[0][0]["title"] == "🌐 سایت" and ig.btn[0][0]["url"] == "https://stland.ir"   # لینک اصلی، نه نشانی کوتاه


def test_fit_and_chunks():
    long = "\n".join(f"آیفون {i} — قیمت تماس بگیرید" for i in range(80))
    f = worker._fit(long)
    assert len(f) <= worker.DM_MAX and f.endswith("بپرس 🌸)") and "آیفون 0" in f
    parts = worker._chunks(long)
    assert len(parts) > 1 and all(len(p) <= worker.DM_MAX for p in parts) and "\n".join(parts) == long


def test_long_private_text_rejected_on_save():
    from app.importer import validate
    errs = validate({"name": "x", "channels": ["comment"], "actions": {"private_replies": ["ا" * 1200]}})
    assert any("۱۰۰۰" in e or "1000" in e for e in errs)


@pytest.mark.asyncio
async def test_public_reply_does_not_claim_sent_when_dm_fails(monkeypatch):
    monkeypatch.setattr(config, "SEND_DELAY_MIN", 0)
    monkeypatch.setattr(config, "SEND_DELAY_MAX", 0)
    monkeypatch.setattr(worker, "MAX_RETRIES", 1)

    class Fail(IG):
        async def private_reply(self, cid, text, buttons=None):
            raise RuntimeError("IG 400 over the limit")
    db.init()
    ig = Fail()
    with db.connect() as c:
        db.upsert_rule(c, {"name": "x", "channels": ["comment"], "triggers": [{"match": "any"}],
                           "actions": {"comment_mode": "both", "private_replies": ["لیست"], "public_replies": ["برات فرستادم"]}})
        db.add_event(c, "c:f1", "comment", {"id": "f1", "text": "لیست", "from": {"id": "u1"}, "media": {"id": "p"}})
        await worker.handle_event(ig, db.pending_events(c)[0], c)
    pub = [t for k, _, t in ig.calls if k == "public"]
    assert pub and "برات فرستادم" not in pub[0] and "دایرکت" in pub[0]


@pytest.mark.asyncio
async def test_once_per_user_not_burned_by_failed_dm_and_per_post(monkeypatch):
    """دایرکتی که نرسید «یک بار» را مصرف نمی‌کند؛ «یک بار» برای هر پست جداست؛ ارسال ناموفق سهمیه نمی‌خورد."""
    monkeypatch.setattr(config, "SEND_DELAY_MIN", 0)
    monkeypatch.setattr(config, "SEND_DELAY_MAX", 0)
    monkeypatch.setattr(worker, "MAX_RETRIES", 1)

    class Flaky(IG):
        fail = True

        async def private_reply(self, cid, text, buttons=None):
            if self.fail:
                raise RuntimeError("IG 400 user cannot be messaged")
            self.calls.append(("private", cid, text))
            return "p"
    db.init()
    ig = Flaky()

    async def comment(cid, media="p1"):
        with db.connect() as c:
            db.add_event(c, f"c:{cid}", "comment", {"id": cid, "text": "لیست", "from": {"id": "u1"}, "media": {"id": media}})
            row = [r for r in db.pending_events(c) if r["id"] == f"c:{cid}"][0]
            return await worker.handle_event(ig, row, c)
    with db.connect() as c:
        db.upsert_rule(c, {"name": "لیست", "channels": ["comment"], "triggers": [{"match": "contains", "value": "لیست"}],
                           "actions": {"comment_mode": "dm", "private_replies": ["لیست قیمت"]}, "advanced": {"once_per_user": True}})
    await comment("a1")                                  # دایرکت نرسید
    ig.fail = False
    assert await comment("a2") == "done"                 # دوباره امتحان می‌شود
    assert ("private", "a2", "لیست قیمت") in ig.calls
    n = len(ig.calls)
    assert await comment("a3") != "done" and len(ig.calls) == n      # حالا رسیده: همان پست دیگر نه
    assert await comment("b1", media="p2") == "done"     # پست دیگر: دوباره
    with db.connect() as c:
        assert c.execute("SELECT use_count FROM rules").fetchone()[0] == 2     # فقط ارسال‌های موفق


def test_normalize_and_matching_edge_cases():
    from app.normalize import normalize
    from app.rules import trigger_matches
    ex = {"match": "exact", "value": "لیست"}
    for t in ["لیست 😍", "لیست❤️", "لیـست", "لیستُ", "  لیست!! 🙏"]:
        assert trigger_matches(ex, normalize(t)), t
    assert trigger_matches({"match": "contains", "value": "میخوام"}, normalize("می خوام لیست"))
    assert trigger_matches({"match": "regex", "value": "IPHONE"}, normalize("iphone 13"))


def test_chunks_keep_order_with_very_long_line():
    parts = worker._chunks("A\n" + "x" * 2500 + "\nB")
    assert parts[0] == "A" and parts[-1].endswith("B") and all(len(p) <= worker.DM_MAX for p in parts)


def test_retry_only_when_clearly_not_sent():
    assert worker._retryable("IG 503: service unavailable") and worker._retryable("IG 429: rate")
    assert not worker._retryable("TimeoutError") and not worker._retryable("IG 400: bad")


def test_menu_negative_index():
    from app import dm_menu
    db.init()
    with db.connect() as c:
        dm_menu.save(c, [{"title": "ساعت", "type": "text", "value": "۱۱ تا ۱۴"}])
        assert dm_menu.reply_for(c, "MENU:-1", "") is None and dm_menu.reply_for(c, "MENU:0", "") == "۱۱ تا ۱۴"
