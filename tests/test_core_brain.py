"""مغز مرکزی (۵ آذر ۱۴۰۵): هسته‌ی حقیقت، فروشنده‌ی هوشمند با ابزار و وارسی، بازبینی شبانه."""
import json

import pytest

from app import agent, ai, brain_engine, db, facts, review
from tests.test_brain_engine import env, tg_data  # noqa: F401  (همان فهرست کالا و دانش نمونه)


# ---------- هسته‌ی حقیقت ----------

def test_truth_core_search_installment_info(env):
    r = facts.search_products("۱۳ پرو")
    assert r["ok"] and r["items"] and all("price_toman" in x and x["link"] for x in r["items"])
    pid, price = r["items"][0]["id"], r["items"][0]["price_toman"]
    q = facts.installment_quote(product_id=pid)
    assert q["ok"] and q["cash_price"] == price and q["down_payment_min"] >= price // 3
    assert [p["months"] for p in q["plans"]][-1] == 10
    assert "خیابان نمونه" in " ".join(facts.store_info("address")["facts"])
    h = facts.store_info("hours")
    assert h["ok"] and "ساعت کاری" in h["facts"][0]
    assert facts.search_products("سلام")["items"] == []


def test_verify_amounts_and_links():
    trace = [{"tool": "search_products", "result": {"items": [
        {"price_toman": 74_900_000, "price_text": "۷۴٬۹۰۰٬۰۰۰ تومان", "link": "https://stland.ir/?p=101"}]}}]
    assert agent.verify("آیفون ۱۳ پرو ۲۵۶ موجوده، ۷۵ میلیون 🙂 https://stland.ir/?p=101", trace) == []
    assert agent.verify("۷۴٬۹۰۰٬۰۰۰ تومان", trace) == []
    probs = agent.verify("قیمتش ۶۰ میلیونه", trace)
    assert probs and "60,000,000" in probs[0]
    assert agent.verify("بیا اینجا https://bit.ly/x", trace)
    assert agent.verify("مدل ۱۳ با حافظه‌ی ۱۲۸ و ۶ ماه قسط", []) == []      # عدد کوچک بی‌واحد مبلغ نیست
    assert agent.is_hard("۱۳ پرو بهتره یا ۱۴؟") and not agent.is_hard("قیمت ۱۳ پرو")


# ---------- فروشنده‌ی هوشمند ----------

class FakeClaude:
    """هر نوبت یک پاسخ از پیش نوشته؛ نوبت‌ها و مدل‌ها ثبت می‌شوند."""
    def __init__(self, script):
        self.script, self.calls = list(script), []

    async def tool_turn(self, model, system, messages, tools, effort="low", max_tokens=4096):
        self.calls.append({"model": model, "messages": list(messages)})
        return self.script.pop(0), {"input_tokens": 1000, "output_tokens": 100}, "tool_use"

    async def complete(self, *a, **k):
        raise AssertionError("مسیر قدیمی نباید صدا زده شود")


def _use(name, inp, i="t1"):
    return [{"type": "tool_use", "id": i, "name": name, "input": inp}]


@pytest.mark.asyncio
async def test_agent_answers_from_tools_only(env, monkeypatch):
    monkeypatch.setattr(ai.config, "ANTHROPIC_API_KEY", "x")
    r = facts.search_products("۱۳ پرو")
    item = r["items"][0]
    good = f"{item['name']} موجوده: {item['price_text']} 🙂 {item['link']}"
    fake = FakeClaude([_use("search_products", {"query": "۱۳ پرو"}),
                       _use("reply_to_customer", {"text": good, "intent": "price", "confidence": 0.9}, "t2")])
    ai.set_client(fake, "anthropic")
    with db.connect() as c:
        ai.save_settings(c, {"enabled": True, "provider": "anthropic", "model": "claude-opus-5-5"})
        d = await ai.decide(c, channel="telegram", text="یه چیز خاص می‌خوام که موتور نفهمه", user_id="tg:5", skip_brain=True)
        assert d.action == "reply" and d.reply == good
        row = c.execute("SELECT model, trace, cost FROM ai_log WHERE id=?", (d.log_id,)).fetchone()
        assert row["model"] == "agent:claude-haiku-5-5" and "search_products" in row["trace"] and row["cost"] > 0
    assert [x["model"] for x in fake.calls] == ["claude-haiku-5-5", "claude-haiku-5-5"]
    # نتیجه‌ی ابزار در نوبت دوم به مدل برگشته
    assert fake.calls[1]["messages"][-1]["content"][0]["type"] == "tool_result"


@pytest.mark.asyncio
async def test_agent_invented_price_is_blocked(env, monkeypatch):
    monkeypatch.setattr(ai.config, "ANTHROPIC_API_KEY", "x")
    bad = _use("reply_to_customer", {"text": "۱۳ پرو فقط ۱۲ میلیون 😍", "intent": "price", "confidence": 0.9})
    fake = FakeClaude([_use("search_products", {"query": "۱۳ پرو"}), bad,          # مدل سریع: عدد ساختگی
                       _use("search_products", {"query": "۱۳ پرو"}), bad])         # مدل قوی هم: باز ساختگی
    ai.set_client(fake, "anthropic")
    with db.connect() as c:
        ai.save_settings(c, {"enabled": True, "provider": "anthropic", "model": "claude-opus-5-5"})
        d = await ai.decide(c, channel="telegram", text="قیمت؟", user_id="tg:6", skip_brain=True)
    assert d.action == "handoff" and "۱۲ میلیون" not in d.reply and "وارسی داده" in d.handoff_reason
    assert [x["model"] for x in fake.calls] == ["claude-haiku-5-5"] * 2 + ["claude-opus-5-5"] * 2
    assert "وارسی دور قبل" in fake.calls[2]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_agent_hard_question_goes_to_strong_model_and_handoff(env, monkeypatch):
    monkeypatch.setattr(ai.config, "ANTHROPIC_API_KEY", "x")
    fake = FakeClaude([_use("handoff_to_human", {"reason": "می‌خواهد امروز بخرد", "text_for_customer": "همکارم الان پیام می‌ده 🙏"})])
    ai.set_client(fake, "anthropic")
    with db.connect() as c:
        ai.save_settings(c, {"enabled": True, "provider": "anthropic", "model": "claude-opus-5-5"})
        d = await ai.decide(c, channel="telegram", text="۱۳ پرو بهتره یا ۱۴؟ قسطی هم میدید؟", user_id="tg:7", skip_brain=True)
    assert d.action == "handoff" and d.reply.startswith("همکارم") and d.handoff_reason == "می‌خواهد امروز بخرد"
    assert [x["model"] for x in fake.calls] == ["claude-opus-5-5"]


# ---------- بازبینی شبانه ----------

def test_review_clean_rejects_unsafe():
    out = {"summary": "روز خوبی بود", "leads": [], "gaps": ["هزینه‌ی ارسال"], "suggestions": [
        {"question": "قصطی میدین", "kind": "example", "intent_id": "i_install", "answer": "", "why": "غلط تایپی"},
        {"question": "x", "kind": "example", "intent_id": "i_install", "answer": "", "why": ""},          # کوتاه
        {"question": "چیزی", "kind": "example", "intent_id": "ناشناخته", "answer": "", "why": ""},
        {"question": "تعمیر دارید", "kind": "new_answer", "intent_id": "", "answer": "بله، ۵۰۰ هزار تومان", "why": ""},
        {"question": "تعمیر دارید؟", "kind": "new_answer", "intent_id": "", "answer": "بله، گوشی رو بیارید فروشگاه 🔧", "why": ""}]}
    r = review.clean(out, {"i_install"})
    assert [x["q"] for x in r["suggestions"]] == ["قصطی میدین", "تعمیر دارید؟"] and r["gaps"] == ["هزینه‌ی ارسال"]


@pytest.mark.asyncio
async def test_review_run_queues_for_owner(env, monkeypatch, tmp_path):
    monkeypatch.setattr(ai.config, "ANTHROPIC_API_KEY", "x")
    (tmp_path / "faq.json").write_text(json.dumps(brain_engine.intents(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(ai.config, "TG_DATA_DIR", str(tmp_path))
    brain_engine._cache.clear()

    class FakeReview:
        async def complete(self, model, system, messages, effort, schema=None, hint=None, max_tokens=2048):
            assert "<data>" in messages[0]["content"] and schema is review.SCHEMA
            return json.dumps({"summary": "۳ سؤال اقساط بی‌جواب ماند", "leads": [{"channel": "dm", "who": "@sara", "why": "اقساط پرسید"}],
                               "gaps": [], "suggestions": [{"question": "قصطی میدین", "kind": "example",
                                                            "intent_id": "i_install", "answer": "", "why": "غلط تایپی"}]},
                              ensure_ascii=False), {"input_tokens": 5000, "output_tokens": 300}, "end_turn"
    ai.set_client(FakeReview(), "anthropic")
    with db.connect() as c:
        ai.save_settings(c, {"enabled": True, "provider": "anthropic", "model": "claude-opus-5-5"})
        c.execute("INSERT INTO ai_log(created_at,channel,user_id,input,action,status,is_test) VALUES (strftime('%s','now'),'dm','u1','قصطی میدین','handoff','sent',0)")
        rep = await review.run(c, force=True)
        assert rep and rep["suggestions"][0]["iid"] == "i_install" and rep["cost"] > 0
        assert review.last(c)["summary"].startswith("۳ سؤال")
        assert c.execute("SELECT COUNT(*) FROM ai_log WHERE channel='review'").fetchone()[0] == 1
    ops = [json.loads(f.read_text(encoding="utf-8")) for f in (tmp_path / "inbox").glob("*.json")]
    assert ops and ops[0]["op"] == "review_suggest" and ops[0]["items"][0]["q"] == "قصطی میدین"


def test_panel_endpoints_and_think_context(env, monkeypatch, tmp_path):
    """پنل: سلامت هسته‌ی حقیقت در آمار و آخرین بازبینی؛ ربات تلگرام گفتگوی اخیر را به مغز مرکزی می‌دهد."""
    from fastapi.testclient import TestClient
    from app import config, internal
    from app.main import create_app
    monkeypatch.setattr(config, "PANEL_PASSWORD", "pw123")
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    monkeypatch.setattr(config, "WEB_DIST", str(tmp_path / "nodist"))
    seen = {}

    async def fake_decide(c, **k):
        seen.update(k)
        return ai.Decision("reply", reply="سلام 🙂")
    monkeypatch.setattr(ai, "decide", fake_decide)
    internal.ensure_key()
    key = internal.key_path().read_text().strip()
    with TestClient(create_app(None)) as cl:
        assert cl.post("/api/login", json={"password": "pw123"}).status_code == 200
        st = cl.get("/api/ai/stats").json()
        assert isinstance(st["truth"], list)
        assert cl.get("/api/ai/review").json() == {"review": None}
        assert cl.post("/api/ai/review/run", json={}).status_code == 422        # هوش مصنوعی خاموش
        r = cl.post("/internal/think", headers={"X-Internal-Key": key},
                    json={"channel": "telegram", "user_id": "9", "text": "همون آبیش", "context": [["مشتری", "۱۳ پرو"], ["ربات", "۱۳ پرو موجوده"]]})
        assert r.status_code == 200 and "مشتری: ۱۳ پرو" in seen["note"] and "ربات: ۱۳ پرو موجوده" in seen["note"]


def test_review_distills_agent_answers(env):
    """انتقال دانش: سؤالی که فقط فروشنده‌ی هوشمند جواب داد نامزد جمله‌ی نمونه است؛
    آنچه ربات آفلاین خودش می‌فهمد، رأی منفی خورده یا به همکار رفته کنار می‌رود."""
    with db.connect() as c:
        for q, act, vote in (("گوشیای شما تو جعبه‌ی خودشونه یا نه", "reply", 0),
                             ("گارانتی دارن؟", "reply", 0),                 # ربات آفلاین خودش می‌فهمد
                             ("یه سؤال عجیب دیگه درباره‌ی کارتن", "reply", -1),    # مشتری گفت بد بود
                             ("سؤال سخت درباره‌ی قطعات", "handoff", 0)):
            c.execute("INSERT INTO ai_log(created_at,channel,user_id,input,action,reply,model,customer_vote,status,is_test) "
                      "VALUES (strftime('%s','now'),'dm','u1',?,?,'جواب',?,?,'sent',0)",
                      (q, act, "agent:claude-haiku-5-5", "down" if vote < 0 else ""))
        c.execute("INSERT INTO ai_log(created_at,channel,user_id,input,action,reply,model,status,is_test) "
                  "VALUES (strftime('%s','now'),'dm','u1','سؤال آزمایشی پنل','reply','x','agent:m','sent',1)")
        wins = review.agent_wins(c)
    assert [w["question"] for w in wins] == ["گوشیای شما تو جعبه‌ی خودشونه یا نه"]
    assert wins[0]["ai_reply"] == "جواب"


def test_agent_apple_specs_tool(env):
    """ابزار مشخصات اپل: داده‌ی دانشنامه بی منبع و نام‌های جایگزین؛ مدل ناشناخته «پیدا نشد»."""
    r = agent.run_tool("apple_specs", {"query": "مک‌بوک ایر M2"})
    assert r["ok"] and r["models"][0]["name"].startswith("MacBook Air") and "sources" not in r["models"][0]
    assert agent.run_tool("apple_specs", {"query": "نوکیا ۳۳۱۰"})["ok"] is False
    assert any(t["name"] == "apple_specs" for t in agent.TOOLS)
