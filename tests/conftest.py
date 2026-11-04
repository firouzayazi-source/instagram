"""ایمنی تست‌ها: هیچ تستی به داده‌ی واقعی سرور (پایگاه داده‌ی igbot و داده‌ی ربات تلگرام) دست نمی‌زند.

روی سرور `.env` واقعی بارگذاری می‌شود و مسیرهای پیش‌فرض به داده‌ی زنده اشاره می‌کنند؛ این فیکسچر پیش از
هر تست آن‌ها را به پوشه‌ی موقت می‌برد. فیکسچرهای خود تست‌ها بعد از این اجرا می‌شوند و می‌توانند عوضشان کنند.
"""
import pytest

from app import config


@pytest.fixture(autouse=True)
def _isolate_data(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "isolated.db"))
    monkeypatch.setattr(config, "TG_DATA_DIR", str(tmp_path / "no-telegram-data"))
    monkeypatch.setenv("IGBOT_ENV_FILE", str(tmp_path / "isolated.env"))   # هیچ تستی در ‎.env‎ واقعی نمی‌نویسد
