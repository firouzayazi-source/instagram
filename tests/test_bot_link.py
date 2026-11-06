"""ابزار نشانی ربات اصلی: نام قدیم از دکمه‌ی اپل‌آیدی پیدا و همه‌جا با نام تازه جایگزین می‌شود؛ بی --apply چیزی نوشته نمی‌شود."""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import set_bot_link as tool  # noqa: E402


def setup(tmp_path):
    tg = tmp_path / "tg"
    tg.mkdir()
    (tg / "menu.json").write_text(json.dumps([{"key": "p_apl", "label": "🆔 خرید اپل آیدی", "order": 9, "enabled": True}],
                                             ensure_ascii=False), encoding="utf-8")
    (tg / "buttons.json").write_text(json.dumps({"p_apl": {"enabled": True, "items": [{"title": "ربات", "url": "https://t.me/OldShopBot?start=ig"}]},
                                                 "4": {"items": [{"title": "کانال", "url": "https://t.me/OldShopBotNews"}]}}), encoding="utf-8")
    (tg / "data.json").write_text(json.dumps({"p_apl": "ربات ما: @oldshopbot", "5": "ایمیل info@OldShopBot.ir"}, ensure_ascii=False),
                                  encoding="utf-8")
    db = tmp_path / "bot.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT)")
        c.execute("INSERT INTO kv VALUES ('ai_settings', ?)", (json.dumps({"business_info": "ربات: telegram.me/OldShopBot"}),))
    return tg, db


def run(tmp_path, *extra):
    tg, db = setup(tmp_path)
    rc = tool.main(["https://t.me/Stlandd_bot", "--tg-dir", str(tg), "--db", str(db), "--backup-dir", str(tmp_path / "bk"),
                    "--no-service", *extra])
    return tg, db, rc


def test_dry_run_changes_nothing(tmp_path, capsys):
    tg, _, _ = run(tmp_path)
    assert "OldShopBot?start" in (tg / "buttons.json").read_text()
    out = capsys.readouterr().out
    assert "نام قدیم: OldShopBot" in out and "فقط نمایش بود" in out
    assert not (tmp_path / "bk").exists()


def test_apply_replaces_everywhere_but_only_that_bot(tmp_path):
    tg, db, _ = run(tmp_path, "--apply")
    b = json.loads((tg / "buttons.json").read_text())
    assert b["p_apl"]["items"][0]["url"] == "https://t.me/Stlandd_bot?start=ig"
    assert b["4"]["items"][0]["url"] == "https://t.me/OldShopBotNews"          # کانالی با نام شبیه دست نمی‌خورد
    d = json.loads((tg / "data.json").read_text(encoding="utf-8"))
    assert d["p_apl"] == "ربات ما: @Stlandd_bot" and d["5"] == "ایمیل info@OldShopBot.ir"
    with sqlite3.connect(db) as c:
        assert "telegram.me/Stlandd_bot" in c.execute("SELECT value FROM kv").fetchone()[0]
    assert any((tmp_path / "bk").iterdir())


def test_bad_name_and_missing_old(tmp_path):
    tg, db = setup(tmp_path)
    for args in (["a b"], ["Stlandd_bot", "--tg-dir", str(tmp_path / "none")]):
        try:
            tool.main([*args, "--db", str(db), "--no-service"])
            raise AssertionError("باید خطا می‌داد")
        except SystemExit as e:
            assert e.code
