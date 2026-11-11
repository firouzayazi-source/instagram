"""نظارت: هشدار فقط بعد از خطای پیوسته و یک بار؛ قیف و خلاصه‌ی روزانه از داده‌ی محلی."""
import json
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from app import comment_poll, config, db, monitor

T0 = 1_800_000_000.0


def setst(c, key, ok, at, error=""):
    db.kv_set(c, key, json.dumps({"at": at, "ok": ok, "error": error}))


def test_alert_once_after_sustained_failure_then_recovery():
    db.init()
    with db.connect() as c:
        setst(c, comment_poll.STATUS_KEY, True, T0)
        assert monitor.check_health(c, True, T0) == []
        setst(c, comment_poll.STATUS_KEY, False, T0 + 60, "Composio 401")
        assert monitor.check_health(c, True, T0 + 60) == []                  # خطای لحظه‌ای: هنوز نه
        setst(c, comment_poll.STATUS_KEY, False, T0 + 700, "Composio 401")
        out = monitor.check_health(c, True, T0 + 700)
        assert len(out) == 1 and "خوانش کامنت‌ها" in out[0] and "401" in out[0]
        assert monitor.check_health(c, True, T0 + 1000) == []                # تکرار نمی‌شود
        setst(c, comment_poll.STATUS_KEY, True, T0 + 1100)
        assert monitor.check_health(c, True, T0 + 1100) == ["✅ خوانش کامنت‌ها دوباره کار می‌کند"]
        # بی‌خبری: خوانشی که باید هر دقیقه اجرا شود متوقف شده
        out = monitor.check_health(c, True, T0 + 1100 + 1000)
        assert len(out) == 1 and "اجرا نشده" in out[0]
        assert monitor.check_health(c, False, T0 + 5000) == []               # پل خاموش: هشداری نیست


def test_funnel_and_digest(tmp_path, monkeypatch):
    tg = tmp_path / "tg"
    tg.mkdir()
    (tg / "faq.json").write_text("[]")
    monkeypatch.setattr(config, "TG_DATA_DIR", str(tg))
    now = datetime(2026, 11, 10, 22, 35, tzinfo=ZoneInfo("Asia/Tehran")).timestamp()
    f = lambda t: datetime.fromtimestamp(t, ZoneInfo("Asia/Tehran")).strftime("%Y-%m-%d %H:%M:%S")  # noqa: E731
    with sqlite3.connect(tg / "users.db") as t:
        t.execute("CREATE TABLE users (user_id INTEGER, joined_at TEXT, source TEXT)")
        t.executemany("INSERT INTO users VALUES (?,?,?)", [(1, f(now - 3600), "insta"), (2, f(now - 7200), "insta-3"),
                                                          (3, f(now - 3600), "qr"), (4, f(now - 9 * 86400), "insta")])
    db.init()
    with db.connect() as c:
        for i, cid in enumerate(["c1", "c2", "c3"]):
            c.execute("INSERT INTO comments(id,media_id,user_id,username,text,created_at,answered) VALUES (?,?,?,?,?,?,?)",
                      (cid, "p1", f"u{i}", "x", "قیمت", now - 600, 1 if i < 2 else 0))
        for cid in ("c1", "c2"):
            db.log_reply(c, f"c:{cid}", 1, "private", cid, "لینک", ig_id="m" + cid, ok=True)
            db.log_reply(c, f"c:{cid}", 1, "public", cid, "دایرکت", ig_id="r" + cid, ok=True)
        c.execute("UPDATE replies SET created_at=?", (now - 500,))
        db.add_message(c, "in1", "u9", "in", "سلام", now - 300)
        fn = monitor.funnel(c, 7, now)
        assert (fn["comments"], fn["auto_dms"], fn["auto_public"], fn["dm_in"], fn["waiting"], fn["tg_entries"]) == (3, 2, 2, 1, 1, 2)
        assert fn["posts"][0]["media_id"] == "p1" and fn["posts"][0]["comments"] == 3 and fn["posts"][0]["dms"] == 2
        text = monitor.digest_text(c, now)
        assert "کامنت تازه: ۳" in text and "دایرکت خودکار: ۲" in text and "ورود به ربات از اینستاگرام: ۲" in text
        assert "سلام" not in text and "قیمت" not in text                     # متن پیام مشتری در خلاصه نیست
        assert monitor.digest_due(c, now)
        db.kv_set(c, "digest_last", "2026-11-10")
        assert not monitor.digest_due(c, now)
        db.kv_set(c, "digest_last", "")
        assert not monitor.digest_due(c, now - 3600)                           # پیش از ۲۲:۳۰
        db.kv_set(c, monitor.DIGEST_KEY, "0")
        assert not monitor.digest_due(c, now)
