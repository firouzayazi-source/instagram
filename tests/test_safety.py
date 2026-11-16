"""قواعد ایمنی پیج (بعد از قفل ۲۵ آبان ۱۴۰۵): ترمز اضطراری، لینک‌ها، سقف و فاصله‌ی جواب کامنت، پنجره‌ی ۲۴ ساعته."""
import asyncio
import time

import pytest

from app import config, db, safety, tg_notify, worker
from app.importer import validate
from app.instagram import Instagram


@pytest.mark.parametrize("err,bad", [
    ("IG 400: {'message': 'Error validating access token', 'type': 'OAuthException', 'code': 190}", True),
    ("IG 400: {'message': 'You are temporarily blocked', 'code': 368}", True),
    ("IG 400: {'message': 'x', 'code': 100, 'error_subcode': 2207051}", True),
    ("IG 403: {'message': 'Application request limit reached', 'code': 4}", True),
    ("IG 400: {'message': 'The length of the message sent is over 1000 characters', 'code': 100}", False),
    ("IG 400: {'message': \"Object with ID '1' does not exist\", 'code': 100}", False),
    ("IG 400: {'message': 'This message is sent outside of allowed window.', 'code': 10, 'error_subcode': 2534022}", False),
])
def test_dangerous_errors(err, bad):
    assert safety.dangerous(err) is bad


def test_brake_trips_on_block_and_stops_all_posts(monkeypatch):
    db.init()
    alerts, sent = [], []
    monkeypatch.setattr(tg_notify, "send", lambda t, *a, **k: alerts.append(t) or True)

    class Fake:
        async def graph(self, method, url, body=None, params=None):
            sent.append(url)
            return 400, {"error": {"message": "You are temporarily blocked from performing this action", "code": 368}}
    monkeypatch.setattr(config, "IG_ACCESS_TOKEN", "")
    monkeypatch.setattr(config, "COMPOSIO_API_KEY", "ck_test", raising=False)
    ig = Instagram()
    ig._composio = Fake()
    with pytest.raises(RuntimeError, match="IG 400"):
        asyncio.run(ig.reply_comment("c1", "ممنون"))
    assert safety.active() and len(alerts) == 1 and "توقف اضطراری" in alerts[0]
    with pytest.raises(RuntimeError, match="BRAKE"):
        asyncio.run(ig.send_dm("u1", "سلام"))
    assert len(sent) == 1                                   # بعد از ترمز هیچ درخواستی به اینستاگرام نرفت
    safety.release()
    assert not safety.active()


@pytest.mark.asyncio
async def test_braked_events_go_to_inbox_only(monkeypatch):
    from tests.test_instagram_features import IG
    monkeypatch.setattr(tg_notify, "send", lambda *a, **k: True)
    db.init()
    ig = IG()
    safety.trip("آزمون", manual=True)
    with db.connect() as c:
        db.upsert_rule(c, {"name": "x", "channels": ["comment"], "triggers": [{"match": "any"}],
                           "actions": {"comment_mode": "public", "public_replies": ["ممنون"]}})
        db.add_event(c, "c:k1", "comment", {"id": "k1", "text": "سلام", "from": {"id": "u1"}, "media": {"id": "p"}})
        assert await worker.handle_event(ig, db.pending_events(c)[0], c) == "braked"
    assert ig.calls == []


@pytest.mark.asyncio
async def test_public_reply_with_link_and_shortener_not_sent(monkeypatch):
    from tests.test_instagram_features import IG
    monkeypatch.setattr(config, "SEND_DELAY_MIN", 0)
    monkeypatch.setattr(config, "SEND_DELAY_MAX", 0)
    db.init()
    ig = IG()
    with db.connect() as c:
        db.upsert_rule(c, {"name": "x", "channels": ["comment"], "triggers": [{"match": "any"}],
                           "actions": {"comment_mode": "both", "public_replies": ["اینجا: stland.ir/shop"],
                                       "private_replies": ["لینک: https://bit.ly/abc"]}})
        db.add_event(c, "c:k1", "comment", {"id": "k1", "text": "قیمت", "from": {"id": "u1"}, "media": {"id": "p"}})
        await worker.handle_event(ig, db.pending_events(c)[0], c)
        errs = [r[0] for r in c.execute("SELECT error FROM replies WHERE ok=0")]
    assert errs and all(e.startswith("ایمنی:") for e in errs)
    assert [k for k, *_ in ig.calls] == ["public"] and "http" not in ig.calls[0][2]      # فقط راهنمای بی‌لینک دایرکت


def test_validate_safety_rules():
    base = {"name": "x", "channels": ["comment"], "triggers": [{"match": "contains", "value": "قیمت"}]}
    assert validate({**base, "actions": {"comment_mode": "public", "public_replies": ["ببین https://stland.ir"]}})
    assert validate({**base, "actions": {"comment_mode": "dm", "private_replies": ["https://bit.ly/x"]}})
    assert validate({**base, "actions": {"comment_mode": "dm", "private_replies": ["x"],
                                         "buttons": [{"title": "سایت", "url": "https://tinyurl.com/x"}]}})
    assert validate({"name": "x", "channels": ["dm"], "actions": {"dm_replies": ["سلام"]},
                     "advanced": {"followup": {"after_seconds": 30 * 3600, "text": "هنوز هستی؟"}}})
    assert validate({**base, "actions": {"comment_mode": "dm", "private_replies": ["لینک: https://stland.ir"]}}) == []


@pytest.mark.asyncio
async def test_followup_skipped_outside_24h_window():
    from tests.test_instagram_features import IG
    db.init()
    ig = IG()
    now = time.time()
    with db.connect() as c:
        db.add_message(c, "in1", "u1", "in", "سلام", sender="user")
        c.execute("UPDATE messages SET created_at=? WHERE id='in1'", (now - 30 * 3600,))
        db.add_followup(c, 1, "u1", "هنوز هستی؟", 0)
        assert await worker.process_followups(ig, c, now=now + 1) == 0
    assert ig.calls == []


def test_comment_limit_capped():
    db.init()
    with db.connect() as c:
        assert worker.comment_limit(c) == 30
        db.kv_set(c, worker.COMMENT_LIMIT_KEY, "100")
        assert worker.comment_limit(c) == worker.COMMENT_LIMIT_MAX == 60


@pytest.mark.asyncio
async def test_public_only_reply_with_link_not_sent(monkeypatch):
    from tests.test_instagram_features import IG
    monkeypatch.setattr(config, "SEND_DELAY_MIN", 0)
    monkeypatch.setattr(config, "SEND_DELAY_MAX", 0)
    db.init()
    ig = IG()
    with db.connect() as c:
        db.upsert_rule(c, {"name": "x", "channels": ["comment"], "triggers": [{"match": "any"}],
                           "actions": {"comment_mode": "public", "public_replies": ["اینجا: stland.ir/shop"]}})
        db.add_event(c, "c:k2", "comment", {"id": "k2", "text": "قیمت", "from": {"id": "u1"}, "media": {"id": "p"}})
        await worker.handle_event(ig, db.pending_events(c)[0], c)
    assert ig.calls == []


@pytest.mark.asyncio
async def test_braked_comment_queue_drains_to_inbox_without_replies(monkeypatch):
    """بعد از برداشتن توقف، موج جواب به کامنت‌های دوره‌ی توقف نمی‌رود."""
    from tests.test_instagram_features import IG
    monkeypatch.setattr(tg_notify, "send", lambda *a, **k: True)
    db.init()
    ig = IG()
    safety.trip("آزمون", manual=True)
    with db.connect() as c:
        db.upsert_rule(c, {"name": "x", "channels": ["comment"], "triggers": [{"match": "any"}],
                           "actions": {"comment_mode": "public", "public_replies": ["ممنون"]}})
        for i in range(5):
            db.add_event(c, f"c:z{i}", "comment", {"id": f"z{i}", "text": "سلام", "from": {"id": f"u{i}"}, "media": {"id": "p"}})
    stop = asyncio.Event()
    task = asyncio.create_task(worker.run_forever(ig, stop, comments=True))
    await asyncio.sleep(1)
    stop.set()
    task.cancel()
    with db.connect() as c:
        assert db.pending_events(c, comments=True) == []
    assert ig.calls == []


@pytest.mark.asyncio
async def test_public_replies_daily_cap_and_no_identical_in_a_row(monkeypatch):
    from tests.test_instagram_features import IG
    monkeypatch.setattr(config, "SEND_DELAY_MIN", 0)
    monkeypatch.setattr(config, "SEND_DELAY_MAX", 0)
    monkeypatch.setattr(worker, "PUBLIC_DAILY_LIMIT", 3)
    db.init()
    ig = IG()
    with db.connect() as c:
        db.upsert_rule(c, {"name": "x", "channels": ["comment"], "triggers": [{"match": "any"}],
                           "actions": {"comment_mode": "both", "public_replies": ["الف", "ب"], "private_replies": ["لینک"]},
                           "advanced": {"random_pick": True, "once_per_user": False}})
        for i in range(5):
            db.add_event(c, f"c:q{i}", "comment", {"id": f"q{i}", "text": "x", "from": {"id": f"u{i}"}, "media": {"id": "p"}})
        for row in db.pending_events(c, limit=10):
            await worker.handle_event(ig, row, c)
    pub = [t for k, _, t in ig.calls if k == "public"]
    assert len(pub) == 3 and all(a != b for a, b in zip(pub, pub[1:]))       # سقف، و هیچ دو تای یکسان پیاپی
    assert len([1 for k, *_ in ig.calls if k == "private"]) == 5            # دایرکت‌ها همه رفتند


def test_any_comment_only_for_specific_posts_and_short_public():
    any_all = {"name": "x", "channels": ["comment"], "triggers": [{"match": "any"}],
               "actions": {"comment_mode": "dm", "private_replies": ["سلام"]}}
    assert validate(any_all)                                            # هر کامنتِ همه‌ی پست‌ها: نه
    assert validate({**any_all, "post_scope": ["123"]}) == []           # هر کامنتِ یک پست: بله
    assert validate({"name": "x", "channels": ["comment"], "triggers": [{"match": "contains", "value": "قیمت"}],
                     "actions": {"comment_mode": "public", "public_replies": ["ا" * 151]}})
