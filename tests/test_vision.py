"""فهم عکس: OpenAI یا Gemini اگر کلید هست؛ بی کلید خاموش (None) و هیچ درخواستی بیرون نمی‌رود."""
import asyncio

import httpx

from app import config, vision


def _run(transport, cap=""):
    return asyncio.run(vision.describe(b"\xff\xd8fake", cap, transport=transport))


def test_providers_and_off_without_key(monkeypatch):
    seen = []
    answers = iter(["«قیمت آیفون ۱۳ پرو»\nتوضیح اضافه", "RECEIPT", "NONE."])

    def handler(req):
        seen.append(req.url.host)
        if "openai" in req.url.host:
            assert b"gpt-4o-mini" in req.content and b"image_url" in req.content
            return httpx.Response(200, json={"choices": [{"message": {"content": next(answers)}}]})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": next(answers)}]}}]})
    t = httpx.MockTransport(handler)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-x", raising=False)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "g-x", raising=False)
    assert _run(t, "این چنده") == "قیمت آیفون ۱۳ پرو"
    assert _run(t) == "RECEIPT"
    monkeypatch.setattr(config, "OPENAI_API_KEY", "", raising=False)
    assert _run(t) == "NONE"
    monkeypatch.setattr(config, "GEMINI_API_KEY", "", raising=False)
    assert _run(t) is None and vision.available() == ""
    assert seen == ["api.openai.com", "api.openai.com", "generativelanguage.googleapis.com"]


def test_internal_vision_off_without_key(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(config, "OPENAI_API_KEY", "", raising=False)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "", raising=False)
    from app import internal
    called = []
    monkeypatch.setattr(internal, "_check", lambda *a: called.append(1))
    from fastapi import FastAPI
    a = FastAPI(); a.include_router(internal.router)
    r = TestClient(a).post("/internal/vision", content=b"x")
    assert r.status_code == 200 and r.json() == {"text": "", "provider": ""} and called
