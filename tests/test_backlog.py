"""صف عقب‌افتاده‌ی کامنت‌ها: دسته‌بندی، کامنت قدیمی‌تر از ۷ روز بی‌دایرکت، کامنت تازه همیشه جلوتر."""
import pytest

from app import config, db, worker
from tools import backlog_comments as bc

T0 = 1_800_000_000.0
TEXTS = {"question": "سؤال", "greet": "سلام", "old": "دایرکت بده", "thanks": ["مرسی"]}


def c_(cid, text, age_days, media="p1"):
    return {"id": cid, "text": text, "from": {"id": f"u{cid}", "username": f"n{cid}"}, "media": media, "ts": T0 - age_days * 86400}


def test_classify():
    assert bc.classify("@ali.r @x") == "skip" and bc.classify("") == "skip"
    assert bc.classify("سلام") == "greet" and bc.classify("درود!") == "greet"
    assert bc.classify("xs پلمپ چند؟") == "question" and bc.classify("لینک تقویم") == "thanks"
    assert bc.classify("عالی بود ❤️") == "thanks"


def test_plan_rule_old_and_fallbacks():
    db.init()
    with db.connect() as c:
        db.upsert_rule(c, {"name": "تقویم", "channels": ["comment"], "post_scope": ["p1"], "triggers": [{"match": "any"}],
                           "actions": {"comment_mode": "both", "private_replies": ["لینک"], "public_replies": ["ارسال شد"]}})
        items = bc.plan(c, [c_("a", "سلام", 2), c_("b", "تقویم", 10), c_("c", "قیمت؟", 1, "p2"), c_("d", "@x", 1, "p2"),
                            c_("e", "سلام", 1, "p2")], TEXTS, now=T0)
    k = {i["id"]: i for i in items}
    assert k["a"]["kind"] == "rule" and not k["a"]["old"]
    assert k["b"]["kind"] == "rule" and k["b"]["old"]
    assert k["c"]["payload"]["_backlog"]["reply"] == "سؤال" and k["d"]["kind"] == "skip"
    assert k["e"]["payload"]["_backlog"]["reply"] == "سلام"


@pytest.mark.asyncio
async def test_old_rule_comment_gets_public_dm_hint_not_false_sent(monkeypatch):
    from tests.test_instagram_features import IG
    monkeypatch.setattr(config, "SEND_DELAY_MIN", 0)
    monkeypatch.setattr(config, "SEND_DELAY_MAX", 0)
    db.init()
    ig = IG()
    with db.connect() as c:
        db.upsert_rule(c, {"name": "تقویم", "channels": ["comment"], "triggers": [{"match": "any"}],
                           "actions": {"comment_mode": "both", "private_replies": ["لینک"], "public_replies": ["ارسال شد"]}})
        for it in bc.plan(c, [c_("old1", "تقویم", 12), c_("new1", "تقویم", 1)], TEXTS, now=T0):
            db.add_event(c, f"c:{it['id']}", "comment", it["payload"])
        for row in db.pending_events(c):
            await worker.handle_event(ig, row, c)
    assert ("public", "old1", "دایرکت بده") in ig.calls and not any(k == "private" and t == "old1" for k, t, _ in ig.calls)
    assert ("private", "new1", "لینک") in ig.calls and ("public", "new1", "ارسال شد") in ig.calls


def test_live_comments_before_backlog():
    db.init()
    with db.connect() as c:
        db.add_event(c, "c:bk", "comment", {"id": "bk", "_backlog": {"reply": "x"}})
        db.add_event(c, "c:live", "comment", {"id": "live"})
        assert [r["id"] for r in db.pending_events(c, comments=True)] == ["c:live", "c:bk"]


def test_previously_ignored_comment_is_requeued():
    db.init()
    with db.connect() as c:
        db.upsert_rule(c, {"name": "x", "channels": ["comment"], "triggers": [{"match": "any"}],
                           "actions": {"comment_mode": "public", "public_replies": ["مرسی"]}})
        db.add_event(c, "c:ig1", "comment", {"id": "ig1"})
        db.finish_event(c, "c:ig1", "ignored")               # آن موقع دستوری نبود
        db.add_event(c, "c:done1", "comment", {"id": "done1"})
        db.finish_event(c, "c:done1", "done")
        items = {i["id"]: i for i in bc.plan(c, [c_("ig1", "سلام", 2), c_("done1", "سلام", 2)], TEXTS, now=T0)}
    assert items["ig1"]["kind"] == "rule" and items["ig1"]["eid"] == "c:ig1:b"
    assert items["done1"]["kind"] == "queued"


def test_comment_days_filter(monkeypatch):
    import asyncio as _a
    olds = [c_("n1", "سلام", 1), c_("o1", "سلام", 20)]
    for x in olds:
        x["ts"] = __import__("time").time() - (1 if x["id"] == "n1" else 20) * 86400

    async def fake_collect(ig, days, me, only=None):
        return olds
    monkeypatch.setattr(bc, "collect", fake_collect)

    class FakeIG:
        token = "t"
        def via_composio(self): return False
        async def _get(self, *a, **k): return {"username": "stock_land.ir"}
    monkeypatch.setattr("app.instagram.Instagram", lambda *a, **k: FakeIG())
    db.init()
    with db.connect() as c:
        db.upsert_rule(c, {"name": "x", "channels": ["comment"], "triggers": [{"match": "any"}],
                           "actions": {"comment_mode": "public", "public_replies": ["مرسی"]}})
    assert bc.main(["--comment-days", "7", "--apply"]) == 0
    with db.connect() as c:
        ids = {r[0] for r in c.execute("SELECT id FROM events")}
    assert ids == {"c:n1"}
