import json
import sys
from pathlib import Path

from app import config

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import set_section as tool  # noqa: E402


def test_queue_section_with_backup(tmp_path, monkeypatch, capsys):
    tg = tmp_path / "tg"
    tg.mkdir()
    (tg / "faq.json").write_text("[]")
    (tg / "data.json").write_text(json.dumps({"3": "متن قدیمی آیپد و مک‌بوک"}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(config, "TG_DATA_DIR", str(tg))
    txt = Path(__file__).resolve().parent.parent / "deploy" / "texts" / "installment.txt"
    tool.main(["3", str(txt), "--backup-dir", str(tmp_path / "bk")])
    assert "فقط نمایش" in capsys.readouterr().out and not (tg / "inbox").exists()
    tool.main(["3", str(txt), "--backup-dir", str(tmp_path / "bk"), "--apply"])
    op = json.loads(next((tg / "inbox").glob("*.json")).read_text(encoding="utf-8"))
    assert op["op"] == "section_set" and op["key"] == "3" and "۱ تا ۱۰ ماه" in op["text"] and "۰۹۱۲۷۴۸۸۴۳۴" in op["text"]
    assert "مک‌بوک" not in op["text"] and any((tmp_path / "bk").iterdir())
