"""دانشنامه‌ی محصولات اپل: پیدا کردن مدل از نوشته‌ی مشتری، کارت مشخصات، و مرز با قیمت و موجودی."""
import json
import sys
from pathlib import Path

import pytest

TG = Path(__file__).resolve().parent.parent / "tgbot"
sys.path.insert(0, str(TG))
import apple_db  # noqa: E402


@pytest.fixture
def sample(tmp_path, monkeypatch):
    (tmp_path / "iphone.json").write_text(json.dumps([
        {"key": "x", "name": "iPhone X", "name_fa": "آیفون X", "aliases": ["iphone 10", "آیفون ۱۰", "ایفون ده"],
         "year": 2017, "chip": "A11 Bionic", "display": {"inch": 5.8, "type": "OLED", "hz": 60},
         "storage_gb": [64, 256], "colors": [{"en": "Silver", "fa": "نقره‌ای"}, {"en": "Space Gray", "fa": "خاکستری"}],
         "port": "Lightning", "biometrics": "Face ID", "sources": ["https://apple.com/x"]},
        {"key": "15 pro", "name": "iPhone 15 Pro", "name_fa": "آیفون ۱۵ پرو", "year": 2023, "chip": "A17 Pro",
         "storage_gb": [128, 256, 512, 1024], "colors": [{"en": "Natural Titanium", "fa": "تیتانیوم طبیعی"}]},
        {"key": "15 pro max", "name": "iPhone 15 Pro Max", "name_fa": "آیفون ۱۵ پرو مکس", "year": 2023,
         "chip": "A17 Pro"}], ensure_ascii=False), encoding="utf-8")
    (tmp_path / "mac.json").write_text(json.dumps([
        {"key": "macbook air m2", "name": "MacBook Air (M2, 2022)", "name_fa": "مک‌بوک ایر M2 (۲۰۲۲)",
         "aliases": ["macbook air m2"], "year": 2022, "chips": ["M2 (8-core CPU)"], "ram_gb": [8, 16, 24],
         "weight_kg": 1.24}], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(apple_db, "DIR", tmp_path)
    monkeypatch.setattr(apple_db, "_items", None)
    monkeypatch.setattr(apple_db, "_index", None)
    return tmp_path


def test_find_by_customer_spelling(sample):
    assert [r["key"] for r in apple_db.find("مشخصات ایفون ده")] == ["x"]
    assert [r["key"] for r in apple_db.find("ایفون ۱۵ پرو مکس چه رنگی داره")] == ["15 pro max"]     # بلندترین نام
    assert [r["key"] for r in apple_db.find("مکبوک ایر ام ۲ رمش چنده")] == ["macbook air m2"]
    assert [r["key"] for r in apple_db.find("فرق آیفون X با ۱۵ پرو")][:1] == ["x"]
    assert apple_db.find("سلام وقت بخیر") == []


def test_card_and_public(sample):
    r = apple_db.find("iphone x")[0]
    c = apple_db.card(r)
    assert "A11 Bionic" in c and "نقره‌ای" in c and "۲۵۶ گیگ" in c and "فیس‌آیدی" in c and "apple.com" not in c
    assert "۱ ترابایت" in apple_db.card(apple_db.find("ایفون ۱۵ پرو")[0], html=False)
    assert "sources" not in apple_db.public(r) and "aliases" not in apple_db.public(r)


def test_spec_question_not_price(sample):
    assert apple_db.spec_question("مشخصات ایفون ده")
    assert apple_db.spec_question("رنگای ایفون ۱۵ پرو چیه")
    assert apple_db.spec_question("قیمت ایفون ۱۵ پرو چنده") == []          # قیمت مال فهرست زنده است
    assert apple_db.spec_question("ایفون ۱۵ پرو دارید") == []


def test_real_dataset_loads():
    """داده‌ی واقعی پوشه‌ی apple/: هر رکورد نام و سال دارد و هیچ نامی بین دو مدل مشترک نیست."""
    rows = apple_db.items()
    if not rows:
        pytest.skip("داده‌ی دانشنامه هنوز نیست")
    assert all(r.get("name") and r.get("year") for r in rows)
    keys = [(r["category"], r.get("key")) for r in rows]
    assert len(keys) == len(set(keys))
