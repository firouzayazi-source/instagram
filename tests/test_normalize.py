from app.normalize import normalize


def test_arabic_letters_and_digits():
    assert normalize("تقويم") == normalize("تقویم")
    assert normalize("كيف پول") == "کیف پول"
    assert normalize("۱۲۳ ٤٥") == "123 45"


def test_edge_punctuation_and_spaces():
    assert normalize("  تقویم.  ") == "تقویم"
    assert normalize("«لینک»!") == "لینک"
    assert normalize("سلام   تقویم‌") == "سلام تقویم"


def test_empty():
    assert normalize(None) == ""
    assert normalize("") == ""
