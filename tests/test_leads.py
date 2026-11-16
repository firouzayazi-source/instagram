"""سرنخ‌ها: نشانه‌ی دستور روی لینک ربات، شمارش ورود هر دستور، وضعیت تماس، یادآور و گزارش هفتگی."""
import json
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app import config, db, leads

TEH = ZoneInfo("Asia/Tehran")
U = "Poshtibani_stland_bot"


@pytest.mark.parametrize("src,out", [
    (f"قیمت اینجا: https://t.me/{U}", f"قیمت اینجا: https://t.me/{U}?start=insta_r7"),
    (f"t.me/{U}?start=insta 🌸", f"https://t.me/{U}?start=insta_r7 🌸"),
    (f"https://t.me/{U}?start=insta-3", f"https://t.me/{U}?start=insta_r7-3"),            # بخش مقصد حفظ می‌شود
    (f"https://t.me/{U}?start=web", f"https://t.me/{U}?start=web"),                      # منبع دیگر دست نمی‌خورد
    ("ربات: {bot}", f"ربات: https://t.me/{U}?start=insta_r7"),
    ("https://t.me/Stlandd_bot", "https://t.me/Stlandd_bot"),                            # ربات اصلی، نه پشتیبان
])
def test_track_links(src, out):
    assert leads.track_links(src, 7, U) == out


def test_track_links_without_bot_name_drops_placeholder():
    assert leads.track_links("ربات: {bot}", 7, "") == "ربات: "


def _tg(tmp_path, monkeypatch, rows):
    tg = tmp_path / "tg"
    tg.mkdir()
    (tg / "status.json").write_text(json.dumps({"username": U}))
    monkeypatch.setattr(config, "TG_DATA_DIR", str(tg))
    with sqlite3.connect(tg / "users.db") as t:
        t.execute("CREATE TABLE users (user_id INTEGER, joined_at TEXT, source TEXT)")
        t.executemany("INSERT INTO users VALUES (?,?,?)", rows)


def test_rule_entries(tmp_path, monkeypatch):
    now = datetime(2026, 11, 14, 12, 0, tzinfo=TEH).timestamp()
    f = lambda t: datetime.fromtimestamp(t, TEH).strftime("%Y-%m-%d %H:%M:%S")  # noqa: E731
    _tg(tmp_path, monkeypatch, [(1, f(now - 60), "insta_r5"), (2, f(now - 60), "insta_r5"), (3, f(now - 60), "insta_r9"),
                                (4, f(now - 60), "insta"), (5, f(now - 40 * 86400), "insta_r5")])
    assert leads.rule_entries(now - 30 * 86400) == {5: 2, 9: 1}


def test_lead_status_reminder_and_weekly(tmp_path, monkeypatch):
    now = datetime(2026, 11, 14, 11, 20, tzinfo=TEH).timestamp()        # شنبه، ساعت ۱۱:۲۰
    f = lambda t: datetime.fromtimestamp(t, TEH).strftime("%Y-%m-%d %H:%M:%S")  # noqa: E731
    _tg(tmp_path, monkeypatch, [(1, f(now - 3600), "insta_r1")])
    db.init()
    with db.connect() as c:
        rid = db.upsert_rule(c, {"name": "قیمت ریلز", "channels": ["comment"], "actions": {"private_replies": ["x"]}})
        for i, ph in enumerate(["09120000001", "09120000002", ""]):
            c.execute("INSERT INTO customers(id,channel,user_id,username,phone,first_seen,last_seen,phone_at) VALUES (?,?,?,?,?,?,?,?)",
                      (f"ig:u{i}", "ig", f"u{i}", f"n{i}", ph, now - 3600, now - 3600, now - 3600 if ph else None))
        assert leads.waiting(c) == 2
        assert leads.remind_due(c, now)
        assert "۲ سرنخ" in leads.remind_text(c, now)
        leads.set_status(c, "ig:u0", "bought")
        assert "خرید کرده" in c.execute("SELECT tags FROM customers WHERE id='ig:u0'").fetchone()[0]
        with pytest.raises(LookupError):
            leads.set_status(c, "ig:u2", "called")               # بی‌شماره سرنخ نیست
        with pytest.raises(ValueError):
            leads.set_status(c, "ig:u1", "??")
        text = leads.weekly_text(c, now)
        assert "شماره‌ی تازه: ۲" in text and "خرید: ۱" in text and "قیمت ریلز: ۱ نفر" in text
        assert "0912" not in text and "n1" not in text                      # بی‌اطلاعات مشتری
        assert rid == 1


def test_weekly_only_saturday_morning():
    db.init()
    with db.connect() as c:
        sat = datetime(2026, 11, 14, 10, 45, tzinfo=TEH).timestamp()
        sun = datetime(2026, 11, 15, 10, 45, tzinfo=TEH).timestamp()
        assert leads.weekly_due(c, sat) and not leads.weekly_due(c, sun)
        db.kv_set(c, "weekly_last", "2026-11-14")
        assert not leads.weekly_due(c, sat)


@pytest.mark.asyncio
@pytest.mark.parametrize("track", [None, True])
async def test_worker_tags_bot_link_with_rule(tmp_path, monkeypatch, track):
    from app import worker
    from tests.test_instagram_features import IG
    _tg(tmp_path, monkeypatch, [])
    monkeypatch.setattr(config, "SEND_DELAY_MIN", 0)
    monkeypatch.setattr(config, "SEND_DELAY_MAX", 0)
    db.init()
    ig = IG()
    with db.connect() as c:
        rule = {"name": "قیمت", "channels": ["comment"], "triggers": [{"match": "contains", "value": "قیمت"}],
                "actions": {"private_replies": [f"لینک: https://t.me/{U}"]}}
        if track:
            rule["advanced"] = {"track_clicks": True}
        rid = db.upsert_rule(c, rule)
        db.add_event(c, "c:k1", "comment", {"id": "k1", "text": "قیمت", "from": {"id": "u1", "username": "a"}, "media": {"id": "m"}})
        assert await worker.handle_event(ig, db.pending_events(c)[0], c) == "done"
    sent = [t for k, tg, t in ig.calls if k == "private" and tg == "k1"][0]
    if not track:     # پیش‌فرض: لینک اصلی (نشانی کوتاه در دایرکت خودکار، پیج را قفل کرد)
        assert sent == f"لینک: https://t.me/{U}?start=insta_r{rid}"
        return
    assert sent.startswith(f"لینک: {config.PUBLIC_URL.rstrip('/')}/l/")          # فقط با روشن کردن صریح
    with db.connect() as c:
        assert c.execute("SELECT url FROM links").fetchone()[0] == f"https://t.me/{U}?start=insta_r{rid}"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,expect", [
    ("public", {"public"}),               # فقط جواب زیر کامنت؛ حتی با متن دایرکت در دستور، دایرکتی نمی‌رود
    ("dm", {"private"}),
    ("both", {"private", "public"}),
])
async def test_comment_reply_modes(tmp_path, monkeypatch, mode, expect):
    from app import worker
    from tests.test_instagram_features import IG
    monkeypatch.setattr(config, "SEND_DELAY_MIN", 0)
    monkeypatch.setattr(config, "SEND_DELAY_MAX", 0)
    db.init()
    ig = IG()
    acts = {"comment_mode": mode, "dm_replies": ["متن دایرکت"]}
    if mode != "dm":
        acts["public_replies"] = ["ممنون 🌸"]
    if mode != "public":
        acts["private_replies"] = ["قیمت در دایرکت"]
    with db.connect() as c:
        db.upsert_rule(c, {"name": "x", "channels": ["comment", "dm"], "triggers": [{"match": "any"}], "actions": acts})
        db.add_event(c, "c:m1", "comment", {"id": "m1", "text": "عالی", "from": {"id": "u1", "username": "a"}, "media": {"id": "p"}})
        assert await worker.handle_event(ig, db.pending_events(c)[0], c) == "done"
    assert {k for k, *_ in ig.calls} == expect


def test_validate_comment_mode():
    from app.importer import validate
    base = {"name": "x", "channels": ["comment"]}
    assert validate({**base, "actions": {"comment_mode": "public", "public_replies": ["ممنون"]}}) == []
    assert validate({**base, "actions": {"comment_mode": "public", "private_replies": ["x"]}})
    assert validate({**base, "actions": {"comment_mode": "both", "private_replies": ["x"]}})
    assert validate({**base, "actions": {"comment_mode": "zzz", "public_replies": ["x"]}})


@pytest.mark.asyncio
async def test_comment_queue_hourly_limit_and_dm_queue_separate(tmp_path, monkeypatch):
    import asyncio
    from app import tg_notify, worker
    from tests.test_instagram_features import IG
    monkeypatch.setattr(config, "SEND_DELAY_MIN", 0)
    monkeypatch.setattr(config, "SEND_DELAY_MAX", 0)
    sent = []
    monkeypatch.setattr(tg_notify, "send", lambda t, *a, **k: sent.append(t) or True)
    db.init()
    ig = IG()
    with db.connect() as c:
        db.kv_set(c, worker.COMMENT_LIMIT_KEY, "2")
        db.upsert_rule(c, {"name": "x", "channels": ["comment"], "triggers": [{"match": "any"}],
                           "actions": {"comment_mode": "public", "public_replies": ["ممنون"]}})
        for i in range(4):
            db.add_event(c, f"c:k{i}", "comment", {"id": f"k{i}", "text": "سلام", "from": {"id": f"u{i}"}, "media": {"id": "p"}})
        db.add_event(c, "m:d1", "message", {"sender": {"id": "z"}, "timestamp": 1, "message": {"mid": "d1", "text": "سلام"}})
        assert [r["id"] for r in db.pending_events(c, comments=False)] == ["m:d1"]
    stop = asyncio.Event()
    task = asyncio.create_task(worker.run_forever(ig, stop, comments=True))
    await asyncio.sleep(1.5)
    stop.set()
    task.cancel()
    with db.connect() as c:
        assert worker.comment_replies_last_hour(c) == 2                 # فقط تا سقف
        assert len(db.pending_events(c, comments=True)) == 2            # بقیه در صف، پاک نشدند
        assert db.pending_events(c, comments=False)[0]["id"] == "m:d1"  # صف کامنت به دایرکت دست نزد
    assert sent and "سقف ۲" in sent[0]


def test_new_lead_counted_by_when_phone_was_given():
    """مشتری قدیمی (یک ماه پیش) که امروز شماره داد، «شماره‌ی تازه» است (قبلاً از تاریخ اولین پیام حساب می‌شد)."""
    import time as _t
    from app import crm
    db.init()
    with db.connect() as c:
        crm.touch(c, "ig", "old1", "old", "message", "سلام")
        c.execute("UPDATE customers SET first_seen=? WHERE id='ig:old1'", (_t.time() - 30 * 86400,))
        crm.touch(c, "ig", "old1", "old", "message", "شماره‌ام ۰۹۱۲۳۴۵۶۷۸۹")
        assert leads.weekly(c)["new_leads"] == 1
        assert "تازه از دیروز" in leads.remind_text(c)


@pytest.mark.asyncio
async def test_random_pick_uses_all_texts(tmp_path, monkeypatch):
    from app import worker
    from tests.test_instagram_features import IG
    monkeypatch.setattr(config, "SEND_DELAY_MIN", 0)
    monkeypatch.setattr(config, "SEND_DELAY_MAX", 0)
    db.init()
    ig = IG()
    texts = ["الف", "ب", "ج"]
    with db.connect() as c:
        db.upsert_rule(c, {"name": "x", "channels": ["comment"], "triggers": [{"match": "any"}],
                           "actions": {"comment_mode": "public", "public_replies": texts}, "advanced": {"random_pick": True}})
        for i in range(40):
            db.add_event(c, f"c:r{i}", "comment", {"id": f"r{i}", "text": "x", "from": {"id": f"u{i}"}, "media": {"id": "p"}})
        for row in db.pending_events(c, limit=100):
            await worker.handle_event(ig, row, c)
    got = [t for k, _, t in ig.calls if k == "public"]
    assert len(got) == 40 and set(got) == set(texts)
