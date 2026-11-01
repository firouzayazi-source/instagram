import io
import json
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import ai, auth, config, db, knowledge, worker
from app.main import create_app
from tests.test_webhook import COMMENT, MESSAGE, FakeIG


class FakeClaude:
    def __init__(self, out=None, stop="end_turn", raise_exc=None):
        self.out = out or {"action": "reply", "reply": "سلام! ۱۳ پرومکس ۲۵ میلیون 🙂", "public_reply": "",
                           "intent": "price", "confidence": 0.9, "handoff_reason": ""}
        self.stop, self.raise_exc, self.calls = stop, raise_exc, []

    async def complete(self, model, system, messages, effort):
        self.calls.append({"model": model, "system": system, "messages": messages, "effort": effort})
        if self.raise_exc:
            raise self.raise_exc
        usage = {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 2000, "cache_creation_input_tokens": 0}
        return json.dumps(self.out, ensure_ascii=False), usage, self.stop


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "IG_USER_ID", "me")
    monkeypatch.setattr(config, "SEND_DELAY_MIN", 0)
    monkeypatch.setattr(config, "SEND_DELAY_MAX", 0)
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(config, "PANEL_PASSWORD", "pw")
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    monkeypatch.setattr(config, "WEB_DIST", str(tmp_path / "nodist"))
    auth._fails.clear()
    db.init()
    fake = FakeClaude()
    ai.set_client(fake)
    yield fake
    ai.set_client(None)


def enable(c, **kw):
    ai.save_settings(c, {"enabled": True, **kw})


# ---------- پایگاه دانش ----------

def test_extract_txt_docx_and_chunk():
    assert knowledge.extract_text("a.txt", "سلام\nدنیا".encode()) == "سلام\nدنیا"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml",
                   '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                   '<w:p><w:r><w:t>گارانتی ۱۸ ماهه</w:t></w:r></w:p><w:p><w:r><w:t>ارسال رایگان</w:t></w:r></w:p>'
                   '</w:body></w:document>')
    assert knowledge.extract_text("a.docx", buf.getvalue()) == "گارانتی ۱۸ ماهه\nارسال رایگان"
    with pytest.raises(ValueError):
        knowledge.extract_text("a.exe", b"x")
    with pytest.raises(ValueError):
        knowledge.extract_text("a.docx", b"not a zip")
    parts = knowledge.chunk("الف" * 10 + "\n" + "ب" * 2500, size=1000)
    assert all(len(p) <= 1000 for p in parts) and len(parts) == 4


def test_retrieval_and_products(env):
    with db.connect() as c:
        knowledge.add_doc(c, "شرایط.txt", "شرایط اقساط: پیش‌پرداخت ۳۰ درصد و ۶ قسط.\n\nارسال به همه‌ی شهرها با پست پیشتاز.".encode())
        hits = knowledge.relevant_chunks(c, "اقساط دارید؟")
        assert hits and "اقساط" in hits[0]["text"]
        assert knowledge.relevant_chunks(c, "سلام") == []
        n = knowledge.import_products(c, "نام,حافظه,رنگ,وضعیت,قیمت,موجودی\n"
                                         "iPhone 13 Pro Max,256,آبی,کارکرده,۴۵٬۵۰۰٬۰۰۰,بله\n"
                                         "iPhone 18 Pro,512,,نو,,ناموجود")
        assert n == 2
        ps = knowledge.list_products(c)
        assert ps[0]["price"] == 45500000 and ps[0]["condition"] == "used"
        assert ps[1]["price"] is None and ps[1]["in_stock"] == 0
        text = knowledge.products_text(c)
        assert "45,500,000 تومان" in text and "قیمت: استعلام" in text and "ناموجود" in text


# ---------- تصمیم ----------

@pytest.mark.asyncio
async def test_decide_disabled_emoji_budget(env):
    with db.connect() as c:
        d = await ai.decide(c, channel="dm", text="قیمت؟", user_id="u")
        assert d.action == "skip" and d.skip_reason == "disabled" and not env.calls
        enable(c)
        d = await ai.decide(c, channel="comment", text="❤️🔥", user_id="u")
        assert d.skip_reason == "emoji" and not env.calls
        ai.save_settings(c, {"monthly_budget_usd": 0.000001})
        c.execute("INSERT INTO ai_log(created_at,channel,input,action,cost) VALUES (?,?,?,?,?)", (time.time(), "dm", "x", "reply", 1))
        d = await ai.decide(c, channel="dm", text="قیمت؟", user_id="u")
        assert d.skip_reason == "budget" and not env.calls


@pytest.mark.asyncio
async def test_decide_reply_builds_prompt_and_costs(env):
    with db.connect() as c:
        enable(c, business_info="آدرس: تهران، خیابان ولیعصر")
        knowledge.save_faq(c, {"question": "گارانتی دارید؟", "keywords": "گارانتی", "answer": "بله ۱۸ ماه"})
        knowledge.save_product(c, {"name": "iPhone 13 Pro Max", "price": 25000000})
        db.add_message(c, "m0", "u2", "in", "سلام")
        db.add_message(c, "m1", "u2", "out", "سلام، در خدمتم")
        db.add_message(c, "m2", "u2", "in", "گارانتی ۱۳ پرومکس چطوره؟")
        d = await ai.decide(c, channel="dm", text="گارانتی ۱۳ پرومکس چطوره؟", user_id="u2", username="ali")
        assert d.action == "reply" and d.reply.startswith("سلام")
        call = env.calls[0]
        system = call["system"][0]["text"]
        assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert "ولیعصر" in system and "بله ۱۸ ماه" in system and "25,000,000" in system
        user = call["messages"][0]["content"]
        assert "<message>\nگارانتی ۱۳ پرومکس چطوره؟\n</message>" in user and "پیج: سلام، در خدمتم" in user
        assert user.count("گارانتی ۱۳ پرومکس") == 1  # پیام فعلی در سابقه تکرار نشده
        row = c.execute("SELECT * FROM ai_log WHERE id=?", (d.log_id,)).fetchone()
        assert row["cost"] == pytest.approx((100 * 4 + 50 * 20 + 2000 * 0.2) / 1e6)
        assert c.execute("SELECT hits FROM faq").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_low_confidence_refusal_and_bad_output_become_safe(env):
    with db.connect() as c:
        enable(c)
        env.out = {**env.out, "confidence": 0.3}
        d = await ai.decide(c, channel="dm", text="قیمت؟", user_id="u")
        assert d.action == "handoff" and "اطمینان" in d.handoff_reason
        env.stop = "refusal"
        d = await ai.decide(c, channel="dm", text="قیمت؟", user_id="u")
        assert d.action == "handoff" and d.reply == ai.DEFAULTS["handoff_message"]
        # خروجی ناقص: بدون confidence یعنی اطمینان صفر، پس ارجاع (نه جواب)
        env.stop, env.out = "end_turn", {"action": "reply", "reply": "x"}
        d = await ai.decide(c, channel="dm", text="قیمت؟", user_id="u")
        assert d.action == "handoff"
        env.out = {"action": "dance"}
        d = await ai.decide(c, channel="dm", text="قیمت؟", user_id="u")
        assert d.action == "error"
        env.raise_exc = RuntimeError("boom")
        d = await ai.decide(c, channel="dm", text="قیمت؟", user_id="u")
        assert d.action == "error"


@pytest.mark.asyncio
async def test_comment_modes(env):
    with db.connect() as c:
        enable(c)
        d = await ai.decide(c, channel="comment", text="قیمت ۱۳ پرومکس؟", user_id="u")
        assert d.reply and d.public_reply in ai.DEFAULTS["public_ack"]
        ai.save_settings(c, {"comment_mode": "public_only"})
        d = await ai.decide(c, channel="comment", text="قیمت ۱۳ پرومکس؟", user_id="u")
        assert d.reply == "" and d.public_reply.startswith("سلام")


@pytest.mark.asyncio
async def test_no_api_key_with_real_client(env):
    ai.set_client(None)
    with db.connect() as c:
        enable(c)
        d = await ai.decide(c, channel="dm", text="قیمت؟", user_id="u")
        assert d.action == "error" and d.skip_reason == "no_api_key"


# ---------- چند سرویس ----------

def _openai_transport(responses, seen):
    """پاسخ‌های پشت‌سرهم یک سرویس سازگار با OpenAI."""
    import httpx

    def handler(request):
        seen.append(json.loads(request.content))
        status, body = responses.pop(0)
        return httpx.Response(status, json=body)
    return httpx.MockTransport(handler)


def _chat(content, finish="stop"):
    return {"choices": [{"message": {"content": content}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 100}}


@pytest.mark.asyncio
async def test_openai_compatible_client_schema_then_json_object():
    seen = []
    out = {"action": "reply", "reply": "سلام", "public_reply": "", "intent": "greeting", "confidence": 0.9, "handoff_reason": ""}
    tr = _openai_transport([(200, _chat(json.dumps(out)))], seen)
    cl = ai.OpenAICompatClient("https://x.test/v1", "k", transport=tr)
    raw, usage, stop = await cl.complete("m", [{"type": "text", "text": "SYS"}], [{"role": "user", "content": "hi"}], "low")
    assert json.loads(raw)["reply"] == "سلام" and usage["input_tokens"] == 1000 and stop == "stop"
    assert seen[0]["response_format"]["type"] == "json_schema" and seen[0]["messages"][0] == {"role": "system", "content": "SYS"}

    # سرویسی که طرح JSON را نمی‌شناسد: یک بار ۴۰۰، بعد حالت ساده؛ دفعه‌ی بعد مستقیم حالت ساده
    seen.clear()
    tr = _openai_transport([(400, {"error": "json_schema unsupported"}), (200, _chat("```json\n" + json.dumps(out) + "\n```")),
                            (200, _chat(json.dumps(out)))], seen)
    cl = ai.OpenAICompatClient("https://x.test/v1", "k", transport=tr)
    raw, _, _ = await cl.complete("m", [{"type": "text", "text": "SYS"}], [{"role": "user", "content": "hi"}], "low")
    assert ai.parse_output(raw)["intent"] == "greeting"
    assert seen[1]["response_format"] == {"type": "json_object"} and "JSON" in seen[1]["messages"][0]["content"]
    await cl.complete("m", [{"type": "text", "text": "SYS"}], [{"role": "user", "content": "hi"}], "low")
    assert len(seen) == 3 and seen[2]["response_format"] == {"type": "json_object"}

    tr = _openai_transport([(401, {"error": "bad key sk-secret-9"})], [])
    with pytest.raises(RuntimeError) as e:
        await ai.OpenAICompatClient("https://x.test/v1", "sk-secret-9", transport=tr).complete("m", [], [], "low")
    assert "sk-secret-9" not in str(e.value)


def test_parse_output_tolerates_wrapping():
    assert ai.parse_output('بفرمایید:\n{"action": "ignore"}\nتمام')["action"] == "ignore"
    with pytest.raises(ValueError):
        ai.parse_output("بدون JSON")


@pytest.mark.asyncio
async def test_fallback_provider_and_custom_price(env, monkeypatch):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "")
    ai.set_client(None)
    ai.set_client(FakeClaude(raise_exc=RuntimeError("overloaded")), "anthropic")
    backup = FakeClaude()
    ai.set_client(backup, "openai")
    with db.connect() as c:
        enable(c, fallback_provider="openai", price_in=1.0, price_out=2.0)
        s = ai.settings(c)
        assert s["fallback_model"] == ai.PROVIDERS["openai"]["models"][0]
        d = await ai.decide(c, channel="dm", text="قیمت؟", user_id="u")
        assert d.action == "reply" and backup.calls[0]["model"] == s["fallback_model"]
        row = c.execute("SELECT model, cost, error FROM ai_log WHERE id=?", (d.log_id,)).fetchone()
        assert row["model"] == f"openai:{s['fallback_model']}" and "overloaded" in row["error"]
        assert row["cost"] == pytest.approx((100 * 1.0 + 50 * 2.0 + 2000 * 1.0) / 1e6)

        # سرویس بدون کلید و بدون پشتیبان: no_api_key
        ai.save_settings(c, {"provider": "deepseek", "model": "", "fallback_provider": ""})
        assert ai.settings(c)["model"] == "deepseek-chat"
        d = await ai.decide(c, channel="dm", text="قیمت؟", user_id="u")
        assert d.action == "error" and d.skip_reason == "no_api_key"


def test_providers_info_never_leaks_keys(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-secret-123")
    monkeypatch.setattr(config, "CUSTOM_AI_BASE_URL", "https://ai.example.ir/v1")
    monkeypatch.setattr(config, "CUSTOM_AI_NAME", "واسط داخلی")
    info = {p["id"]: p for p in ai.providers_info()}
    assert info["openai"]["configured"] and info["custom"]["configured"] and info["custom"]["label"] == "واسط داخلی"
    assert "sk-secret-123" not in json.dumps(info)


# ---------- worker ----------

@pytest.mark.asyncio
async def test_worker_ai_comment_and_handoff(env, monkeypatch):
    sent = []

    async def fake_notify(title, body, url="/"):
        sent.append((title, url))
    monkeypatch.setattr(worker.push, "notify_all", fake_notify)
    ig = FakeIG()
    with db.connect() as c:
        enable(c)
        env.out = {**env.out, "action": "handoff", "intent": "purchase", "handoff_reason": "قصد خرید"}
        db.add_event(c, "c:c100", "comment", {**COMMENT["entry"][0]["changes"][0]["value"], "text": "میخوام بخرم"})
        assert await worker.handle_event(ig, db.pending_events(c)[0], c) == "done"
        import asyncio
        await asyncio.sleep(0)
        assert [k for k, *_ in ig.calls] == ["private", "public"]
        h = c.execute("SELECT * FROM handoffs").fetchone()
        assert h["status"] == "open" and h["comment_id"] == "c100" and h["reason"] == "قصد خرید"
        assert c.execute("SELECT status FROM ai_log").fetchone()[0] == "sent"
    assert sent and sent[0][1] == "/#/ai/handoffs"


@pytest.mark.asyncio
async def test_worker_blocked_rules_first_and_ignore(env):
    ig = FakeIG()
    with db.connect() as c:
        enable(c)
        knowledge.block(c, "u2", "spammer")
        db.add_event(c, "m:mid1", "message", MESSAGE["entry"][0]["messaging"][0])
        assert await worker.handle_event(ig, db.pending_events(c)[0], c) == "ignored"
        knowledge.unblock(c, "u2")
        db.upsert_rule(c, {"name": "قیمت", "channels": ["dm"], "triggers": [{"match": "exact", "value": "قیمت"}],
                           "actions": {"dm_replies": ["قانون"]}})
        db.add_event(c, "m:mid2", "message", {**MESSAGE["entry"][0]["messaging"][0], "message": {"mid": "mid2", "text": "قیمت"}})
        row = [r for r in db.pending_events(c) if r["id"] == "m:mid2"][0]
        assert await worker.handle_event(ig, row, c) == "done"
        assert ig.calls[-1] == ("dm", "u2", "قانون") and not env.calls
        env.out = {**env.out, "action": "ignore"}
        db.add_event(c, "m:mid3", "message", {**MESSAGE["entry"][0]["messaging"][0], "message": {"mid": "mid3", "text": "تبلیغ پیج ما"}})
        row = [r for r in db.pending_events(c) if r["id"] == "m:mid3"][0]
        assert await worker.handle_event(ig, row, c) == "ignored"


# ---------- API ----------

def test_api_flow(env):
    with TestClient(create_app(FakeIG())) as cl:
        assert cl.get("/api/ai/settings").status_code == 401
        cl.post("/api/login", json={"password": "pw"})
        s = cl.get("/api/ai/settings").json()
        assert s["settings"]["enabled"] is False and s["settings"]["provider"] == "anthropic"
        claude = next(p for p in s["providers"] if p["id"] == "anthropic")
        assert "claude-haiku-5-5" in claude["models"] and claude["configured"] is False
        assert all("sk-" not in json.dumps(p) for p in s["providers"])
        assert cl.put("/api/ai/settings", json={"model": "bad model!"}).status_code == 422
        assert cl.put("/api/ai/settings", json={"provider": "nope"}).status_code == 422
        assert cl.put("/api/ai/settings", json={"enabled": True, "tone": "formal"}).json()["settings"]["tone"] == "formal"

        fid = cl.post("/api/ai/faq", json={"question": "ساعت کاری؟", "keywords": "ساعت", "answer": "۱۰ تا ۲۲"}).json()["id"]
        assert cl.get("/api/ai/faq").json()[0]["id"] == fid
        assert cl.post("/api/ai/faq", json={"question": "", "answer": ""}).status_code == 422

        r = cl.post("/api/ai/docs?name=info.txt", content="گارانتی همه‌ی گوشی‌ها ۱۸ ماه است و ارسال رایگان.".encode())
        did = r.json()["id"]
        assert "گارانتی" in cl.get(f"/api/ai/docs/{did}").json()["preview"]
        assert cl.post("/api/ai/docs?name=x.exe", content=b"abc").status_code == 422

        assert cl.post("/api/ai/products/import", json={"text": "iPhone 15\t128\tمشکی\tنو\t50000000\t1"}).json()["imported"] == 1
        pid = cl.get("/api/ai/products").json()[0]["id"]
        cl.put(f"/api/ai/products/{pid}", json={"name": "iPhone 15", "price": "51,000,000"})
        assert cl.get("/api/ai/products").json()[0]["price"] == 51000000

        t = cl.post("/api/ai/test", json={"channel": "dm", "text": "قیمت آیفون ۱۵؟"}).json()
        assert t["action"] == "reply" and t["reply"]
        assert cl.get("/api/ai/log").json() == []  # تست در لاگ اصلی نمی‌آید
        lid = cl.get("/api/ai/log?filter=test").json()[0]["id"]
        r = cl.post(f"/api/ai/log/{lid}/feedback", json={"feedback": "bad", "correct_answer": "۵۱ میلیون", "keywords": "آیفون ۱۵"}).json()
        assert r["faq_id"]
        assert len(cl.get("/api/ai/faq").json()) == 2

        cl.post("/api/ai/blocked", json={"user_id": "u9", "username": "spam"})
        assert cl.get("/api/ai/blocked").json()[0]["user_id"] == "u9"
        cl.delete("/api/ai/blocked/u9")
        assert cl.get("/api/ai/blocked").json() == []

        with db.connect() as c:
            c.execute("INSERT INTO handoffs(created_at,channel,user_id,text) VALUES (?,?,?,?)", (time.time(), "dm", "u1", "خرید"))
        hs = cl.get("/api/ai/handoffs").json()
        assert len(hs) == 1
        cl.post(f"/api/ai/handoffs/{hs[0]['id']}/resolve", json={"done": True})
        assert cl.get("/api/ai/handoffs").json() == []
        st = cl.get("/api/stats").json()
        assert st["ai"]["handoffs_open"] == 0 and "auto_answered_24h" in st
