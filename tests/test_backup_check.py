"""آزمون بازگردانی بکاپ: بکاپ سالم ← ok؛ بکاپ خراب، قدیمی یا نصفه ← هشدار در نظارت."""
import json
import os
import sqlite3
import time

from app import db, monitor
from tools import backup_check


def _backup(tmp_path, name="bot-2026-11-13.db"):
    d = tmp_path / "bk"
    d.mkdir(exist_ok=True)
    live = tmp_path / "live.db"
    db.init(str(live))
    with db.connect(str(live)) as c:
        db.upsert_rule(c, {"name": "x"})
    with sqlite3.connect(live) as src, sqlite3.connect(d / name) as dst:
        src.backup(dst)
    return d, live


def test_good_backup(tmp_path):
    d, live = _backup(tmp_path)
    r = backup_check.run(d, live)
    assert r["ok"], r


def test_corrupt_old_or_shrunk_backup(tmp_path):
    d, live = _backup(tmp_path)
    (d / "bot-2026-11-14.db").write_bytes(b"not a database" * 100)
    r = backup_check.run(d, live)
    assert not r["ok"] and "bot-2026-11-14.db" in r["error"]
    (d / "bot-2026-11-14.db").unlink()
    old = time.time() - 40 * 3600
    os.utime(d / "bot-2026-11-13.db", (old, old))
    assert "قدیمی" in backup_check.run(d, live)["error"]
    os.utime(d / "bot-2026-11-13.db", None)
    with db.connect(str(live)) as c:
        for i in range(40):
            db.upsert_rule(c, {"name": f"r{i}"})
    assert "rules" in backup_check.run(d, live)["error"]           # بکاپ نصف داده‌ی زنده


def test_monitor_alerts_on_backup_problem():
    db.init()
    now = time.time()
    with db.connect() as c:
        db.kv_set(c, "backup_check", json.dumps({"at": now, "ok": False, "error": "باز نشد"}))
        assert monitor.check_health(c, False, now) == []                    # تا ۱۰ دقیقه صبر
        out = monitor.check_health(c, False, now + 700)                     # بی‌پل Composio هم بررسی می‌شود
        assert len(out) == 1 and "بکاپ شبانه" in out[0]
        db.kv_set(c, "backup_check", json.dumps({"at": now + 900, "ok": True}))
        assert any("دوباره کار" in m for m in monitor.check_health(c, False, now + 1000))


def test_missing_dir_and_empty_dir(tmp_path):
    r = backup_check.run(tmp_path / "nope", tmp_path / "live.db")
    assert not r["ok"] and "نیست" in r["error"]
    (tmp_path / "empty").mkdir()
    assert "خالی" in backup_check.run(tmp_path / "empty", tmp_path / "live.db")["error"]
