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
            c.execute("INSERT INTO customers(id,channel,user_id,username,phone,first_seen,last_seen) VALUES (?,?,?,?,?,?,?)",
                      (f"ig:u{i}", "ig", f"u{i}", f"n{i}", ph, now - 3600, now - 3600))
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
async def test_worker_tags_bot_link_with_rule(tmp_path, monkeypatch):
    from app import worker
    from tests.test_instagram_features import IG
    _tg(tmp_path, monkeypatch, [])
    monkeypatch.setattr(config, "SEND_DELAY_MIN", 0)
    monkeypatch.setattr(config, "SEND_DELAY_MAX", 0)
    db.init()
    ig = IG()
    with db.connect() as c:
        rid = db.upsert_rule(c, {"name": "قیمت", "channels": ["comment"], "triggers": [{"match": "contains", "value": "قیمت"}],
                                 "actions": {"private_replies": [f"لینک: https://t.me/{U}"]}})
        db.add_event(c, "c:k1", "comment", {"id": "k1", "text": "قیمت", "from": {"id": "u1", "username": "a"}, "media": {"id": "m"}})
        assert await worker.handle_event(ig, db.pending_events(c)[0], c) == "done"
    assert ("private", "k1", f"لینک: https://t.me/{U}?start=insta_r{rid}") in ig.calls
