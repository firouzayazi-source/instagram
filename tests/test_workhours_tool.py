import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import set_workhours as tool  # noqa: E402


def test_shifts_on_open_days_friday_stays_closed(tmp_path, capsys):
    tg = tmp_path / "tg"
    tg.mkdir()
    (tg / "workhours.json").write_text(json.dumps({"enabled": True, "schedule": {
        str(i): {"open": i != 6, "shifts": [{"from": "10:00", "to": "22:00"}]} for i in range(7)}}), encoding="utf-8")
    args = ["11:00-14:00", "17:00-22:00", "--tg-dir", str(tg), "--backup-dir", str(tmp_path / "bk"), "--no-service"]
    tool.main(args)
    assert "10:00" in (tg / "workhours.json").read_text() and "فقط نمایش" in capsys.readouterr().out
    tool.main(args + ["--apply"])
    s = json.loads((tg / "workhours.json").read_text())["schedule"]
    assert s["0"] == {"open": True, "shifts": [{"from": "11:00", "to": "14:00"}, {"from": "17:00", "to": "22:00"}]}
    assert s["6"]["open"] is False and any((tmp_path / "bk").iterdir())


def test_friday_untouched_by_default(tmp_path):
    tg = tmp_path / "tg"
    tg.mkdir()
    (tg / "workhours.json").write_text(json.dumps({"enabled": True, "schedule": {
        **{str(i): {"open": True, "shifts": [{"from": "10:00", "to": "22:00"}]} for i in range(6)},
        "6": {"open": True, "shifts": [{"from": "17:00", "to": "23:00"}]}}}), encoding="utf-8")
    tool.main(["11:00-14:00", "17:00-22:00", "--tg-dir", str(tg), "--backup-dir", str(tmp_path / "bk"), "--no-service", "--apply"])
    s = json.loads((tg / "workhours.json").read_text())["schedule"]
    assert s["6"] == {"open": True, "shifts": [{"from": "17:00", "to": "23:00"}]} and len(s["5"]["shifts"]) == 2


def test_days_changes_only_that_day_and_close(tmp_path):
    tg = tmp_path / "tg"
    tg.mkdir()
    (tg / "workhours.json").write_text(json.dumps({"enabled": True, "schedule": {
        str(i): {"open": True, "shifts": [{"from": "11:00", "to": "14:00"}]} for i in range(7)}}), encoding="utf-8")
    base = ["--tg-dir", str(tg), "--backup-dir", str(tmp_path / "bk"), "--no-service", "--apply"]
    tool.main(["17:00-22:00", "--days", "6"] + base)
    s = json.loads((tg / "workhours.json").read_text())["schedule"]
    assert s["6"]["shifts"] == [{"from": "17:00", "to": "22:00"}] and s["0"]["open"] and s["0"]["shifts"][0]["from"] == "11:00"
    tool.main(["11:00-14:00", "--days", "0", "--close", "6"] + base)
    assert json.loads((tg / "workhours.json").read_text())["schedule"]["6"] == {"open": False, "shifts": []}
