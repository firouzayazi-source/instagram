"""خروجی پیام‌های واقعی برای رشد دانش ربات: بی‌نام، شماره‌ها پوشانده، یکتا با تعداد، فقط خواندن."""
import json
import sqlite3

from tools import export_questions as ex


def test_mask_hides_personal_details():
    t = ex.mask("سلام شمارم ۰۹۱۲ ۳۴۵ ۶۷۸۹ هست، ایمیل a.b@gmail.com و پیجم @my.page لینک https://x.ir/abc")
    for bad in ("0912", "6789", "gmail", "my.page", "x.ir"):
        assert bad not in t
    assert "<شماره>" in t and "<ایمیل>" in t and "<آیدی>" in t and "<لینک>" in t
    assert ex.mask("قیمت ۱۳ پرو ۲۵۶ چنده") == "قیمت 13 پرو 256 چنده"     # عدد کوتاه (مدل، حافظه) می‌ماند
    assert ex.mask("↩️ (جواب به استوری) ایکس چند") == "ایکس چند"           # برچسب نمایشی صندوق
    assert ex.mask("👍 مفید بود") == "" and ex.mask("🖼 عکس") == ""


def test_export_reads_all_sources(tmp_path):
    db = tmp_path / "bot.db"
    c = sqlite3.connect(db)
    c.executescript("CREATE TABLE messages(id TEXT,user_id TEXT,direction TEXT,text TEXT,created_at REAL);"
                    "CREATE TABLE comments(id TEXT,text TEXT,created_at REAL);"
                    "CREATE TABLE ai_log(input TEXT,channel TEXT,is_test INT,created_at REAL);")
    now = 2_000_000_000
    c.executemany("INSERT INTO messages VALUES (?,?,?,?,?)", [
        ("1", "u", "in", "قیمت ۱۳ پرو؟", now), ("2", "u", "in", "قیمت ۱۳ پرو", now),
        ("3", "u", "out", "جواب ربات", now), ("4", "u", "in", "قدیمی", 10)])
    c.execute("INSERT INTO comments VALUES ('c','اسنپ پی دارید',?)", (now,))
    c.execute("INSERT INTO ai_log VALUES ('بازبینی شبانه','review',0,?)", (now,))
    c.execute("INSERT INTO ai_log VALUES ('آزمون پنل','dm',1,?)", (now,))
    c.commit(); c.close()
    tg = tmp_path / "tg"
    tg.mkdir()
    (tg / "unmatched.json").write_text(json.dumps([{"text": "تعمیر دارید", "count": 3}], ensure_ascii=False), encoding="utf-8")
    items, stats = ex.build(ex.collect(db, tg, now - 100), 100)
    got = dict(items)
    assert got == {"قیمت 13 پرو؟": 2, "تعمیر دارید": 3, "اسنپ پی دارید": 1}
    assert stats["دایرکت اینستاگرام"] == 2 and stats["جستجوی کالای تلگرام"] == 0
    assert "کامنت اینستاگرام" not in ex.collect(db, tg, now - 100, comments=False)
    out = tmp_path / "q.json"
    assert ex.main(["--db", str(db), "--tg-dir", str(tg), "--out", str(out), "--days", "100000"]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))
