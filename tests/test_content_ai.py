"""دستیار محتوا: آمار واقعی پیج در پرامپت، لینک ربات به دایرکت اضافه می‌شود، هزینه لاگ می‌شود."""
import asyncio
import json

import pytest

from app import ai, config, content_ai, db, insights
from tests.test_insights import FakeSource


class Fake:
    def __init__(self, out):
        self.out, self.seen = out, None

    async def complete(self, model, system, messages, effort, schema=None, hint=None):
        self.seen = (system, messages, schema)
        return json.dumps(self.out, ensure_ascii=False), {"input_tokens": 100, "output_tokens": 50}, "end_turn"


IDEA = {"title": "حافظه پر شده؟", "why": "ریلزهای حل مشکل ذخیره‌ی بیشتری گرفته‌اند", "hook": "حافظه‌ت پره؟", "scenes": ["a", "b", "c"],
        "caption": "بنویس «حافظه»", "keyword": "حافظه", "dm_text": "آموزش کامل اینجاست", "public_reply": "دایرکت رو ببین"}


def test_ideas_use_page_stats_and_add_bot_link(tmp_path, monkeypatch):
    tg = tmp_path / "tg"
    tg.mkdir()
    (tg / "status.json").write_text(json.dumps({"username": "support_test_bot"}))
    monkeypatch.setattr(config, "TG_DATA_DIR", str(tg))
    db.init()
    fake = Fake({"ideas": [IDEA]})
    ai.set_client(fake)
    try:
        with db.connect() as c:
            asyncio.run(insights.collect_media(c, FakeSource()))
            ai.save_settings(c, {"business_info": "فروشگاه در قم"})
            out = asyncio.run(content_ai.ideas(c, "حافظه"))
            assert out["has_stats"] and out["ideas"][0]["dm_text"] == "آموزش کامل اینجاست\nhttps://t.me/support_test_bot?start=insta"
            sys_text = fake.seen[0][0]["text"]
            assert "حل مشکل همراه‌بانک" in sys_text and "ریچ 10000" in sys_text and "فروشگاه در قم" in sys_text
            assert "هیچ قیمت" in sys_text and fake.seen[2] is content_ai.SCHEMA and "حافظه" in fake.seen[1][0]["content"]
            row = c.execute("SELECT channel, is_test, input_tokens FROM ai_log").fetchone()
            assert tuple(row) == ("content", 1, 100)
    finally:
        ai.set_client(None)


def test_ideas_errors_are_readable():
    db.init()
    ai.set_client(Fake({"ideas": []}))
    try:
        with db.connect() as c, pytest.raises(RuntimeError, match="ایده‌ای برنگشت"):
            asyncio.run(content_ai.ideas(c))
    finally:
        ai.set_client(None)
