"""ویس ← متن: OpenAI اگر کلید هست، وگرنه Gemini، وگرنه None (ربات مثل قبل ویس را به همکار می‌دهد)."""
import asyncio

import httpx

from app import config, voice


def _run(transport):
    return asyncio.run(voice.transcribe(b"OggS-fake", transport=transport))


def test_openai_then_gemini_then_none(monkeypatch):
    seen = []

    def handler(req):
        seen.append(req.url.host)
        if "openai" in req.url.host:
            assert b"gpt-4o-mini-transcribe" in req.content and b'name="language"' in req.content
            return httpx.Response(200, json={"text": " قیمت آیفون ۱۳ چنده "})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "آدرس فروشگاه کجاست"}]}}]})
    t = httpx.MockTransport(handler)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-x", raising=False)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "g-x", raising=False)
    assert _run(t) == "قیمت آیفون ۱۳ چنده"
    monkeypatch.setattr(config, "OPENAI_API_KEY", "", raising=False)
    assert _run(t) == "آدرس فروشگاه کجاست"
    monkeypatch.setattr(config, "GEMINI_API_KEY", "", raising=False)
    assert _run(t) is None and voice.available() == ""
    assert seen == ["api.openai.com", "generativelanguage.googleapis.com"]


def test_too_big_is_skipped(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-x", raising=False)
    assert asyncio.run(voice.transcribe(b"x" * (voice.MAX_BYTES + 1))) is None


def test_local_llm_check_refuses_remote_url():
    """ابزار سنجش مدل محلی فقط 127.0.0.1/localhost را می‌پذیرد."""
    import importlib.util, pathlib
    p = pathlib.Path(__file__).resolve().parent.parent / "tools" / "local_llm_check.py"
    spec = importlib.util.spec_from_file_location("llc", p); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    assert m.main(["--url", "https://example.com/v1"]) == 2
