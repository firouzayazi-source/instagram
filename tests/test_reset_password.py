"""بازیابی رمز پنل: فقط PANEL_PASSWORD عوض می‌شود، بکاپ و ۶۰۰ می‌ماند، ورودهای قبلی باطل می‌شوند."""
import os
import re
import sqlite3

from tools import reset_panel_password as r


def test_dry_run_changes_nothing(tmp_path):
    env = tmp_path / ".env"
    env.write_text("PANEL_PASSWORD=old\nIG_ACCESS_TOKEN=keep\n", encoding="utf-8")
    assert r.main(["--env", str(env), "--no-service", "--backup-dir", str(tmp_path / "b")]) == 0
    assert env.read_text(encoding="utf-8") == "PANEL_PASSWORD=old\nIG_ACCESS_TOKEN=keep\n"
    assert not (tmp_path / "b").exists()


def test_apply_resets_password(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("# تنظیمات\nPANEL_PASSWORD=old\nIG_ACCESS_TOKEN=keep\n", encoding="utf-8")
    os.chmod(env, 0o600)
    db = tmp_path / "bot.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE sessions(token TEXT, created_at REAL, expires_at REAL)")
        c.execute("INSERT INTO sessions VALUES('t', 0, 9e12)")
    r.main(["--apply", "--env", str(env), "--db", str(db), "--no-service", "--backup-dir", str(tmp_path / "b")])
    text = env.read_text(encoding="utf-8")
    pw = re.search(r"^PANEL_PASSWORD=(.+)$", text, re.M).group(1)
    assert re.fullmatch(r"[a-z2-9]{5}(-[a-z2-9]{5}){3}", pw) and pw != "old"
    assert "IG_ACCESS_TOKEN=keep" in text and "# تنظیمات" in text and text.count("PANEL_PASSWORD") == 1
    assert oct(os.stat(env).st_mode & 0o777) == "0o600"
    backup = next((tmp_path / "b").iterdir())
    assert "PANEL_PASSWORD=old" in backup.read_text(encoding="utf-8") and oct(os.stat(backup).st_mode & 0o777) == "0o600"
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    assert pw in capsys.readouterr().out                 # فقط روی ترمینال خود صاحب سرور


def test_passwords_are_random():
    assert len({r.new_password() for _ in range(50)}) == 50
