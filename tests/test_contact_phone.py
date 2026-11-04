"""ابزار یکی کردن شماره‌ی تماس: فقط شماره‌ها عوض می‌شوند؛ بی --apply چیزی نوشته نمی‌شود؛ بکاپ گرفته می‌شود."""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import set_contact_phone as tool  # noqa: E402


def setup(tmp_path):
    tg = tmp_path / "tg"
    tg.mkdir()
    (tg / "data.json").write_text(json.dumps({"4": "📞 تماس: ۰۲۵۳۷۷۰۰۱۱۲\n📱 موبایل: ۰۹۱۲۱۱۱۲۲۳۳\n📱 موبایل: ۰۹۱۲۱۱۱۲۲۳۳",
                                              "5": "📍 قم، عمار یاسر، کد پستی ۳۷۱۶۸۹۴۵۶۲"}, ensure_ascii=False), encoding="utf-8")
    (tg / "faq.json").write_text(json.dumps([{"id": "i_phone", "answer": "زنگ بزنید 0935 444 5566", "hits": 4},
                                             {"id": "i_price", "answer": "قیمت ۱۹۰٬۰۰۰٬۰۰۰ تومان"}], ensure_ascii=False),
                                 encoding="utf-8")
    (tg / "buttons.json").write_text(json.dumps({"4": {"items": [{"title": "تماس", "url": "tel:+989121112233"}]}}), encoding="utf-8")
    db = tmp_path / "bot.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT)")
        c.execute("INSERT INTO kv VALUES ('ai_settings', ?)", (json.dumps({"business_info": "تلفن: 025-37700112"}, ensure_ascii=False),))
        c.execute("CREATE TABLE customers (phone TEXT)")
        c.execute("INSERT INTO customers VALUES ('09351112233')")
    return tg, db


def run(tmp_path, *extra):
    tg, db = setup(tmp_path)
    tool.main(["09127488434", "--tg-dir", str(tg), "--db", str(db), "--backup-dir", str(tmp_path / "bk"), "--no-service", *extra])
    return tg, db


def test_dry_run_changes_nothing(tmp_path, capsys):
    tg, db = run(tmp_path)
    assert "۰۲۵۳۷۷۰۰۱۱۲" in (tg / "data.json").read_text(encoding="utf-8")
    out = capsys.readouterr().out
    assert "جای تغییر" in out and "فقط نمایش بود" in out and "قبل:" in out
    assert not (tmp_path / "bk").exists()


def test_apply_replaces_only_phones(tmp_path):
    tg, db = run(tmp_path, "--apply")
    data = json.loads((tg / "data.json").read_text(encoding="utf-8"))
    assert data["4"] == "📞 تماس: ۰۹۱۲۷۴۸۸۴۳۴\n📱 موبایل: ۰۹۱۲۷۴۸۸۴۳۴"          # تکراری یکی شد
    assert "۳۷۱۶۸۹۴۵۶۲" in data["5"]                                                # کد پستی دست نخورد
    faq = json.loads((tg / "faq.json").read_text(encoding="utf-8"))
    assert faq[0]["answer"] == "زنگ بزنید 09127488434" and faq[0]["hits"] == 4
    assert faq[1]["answer"] == "قیمت ۱۹۰٬۰۰۰٬۰۰۰ تومان"
    assert json.loads((tg / "buttons.json").read_text())["4"]["items"][0]["url"] == "tel:+989127488434"
    with sqlite3.connect(db) as c:
        assert "09127488434" in c.execute("SELECT value FROM kv").fetchone()[0]
        assert c.execute("SELECT phone FROM customers").fetchone()[0] == "09351112233"   # داده‌ی مشتری دست نخورد
    bk = next((tmp_path / "bk").iterdir())
    assert "۰۲۵۳۷۷۰۰۱۱۲" in (bk / "data.json").read_text(encoding="utf-8") and (bk / "bot.db").exists()
