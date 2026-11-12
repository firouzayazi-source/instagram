"""فروش در دایرکت: کارت ویترین، گرفتن سفارش، رسید، دستورهای تازه، مخاطبین، وبهوک و تنظیم با حرف."""
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import ai, ai_admin, auth, config, crm, db, orders, reports, webhook, worker
from app.main import create_app
from tests.test_instagram_features import IG, msg, run

TG = Path(__file__).resolve().parent.parent / "tgbot"
SAMPLE = [("آیفون 13 پرو 256", "iPhone 13 Pro", "256 گیگابایت", "Gold", "کارکرده", 190_000_000),
          ("آیفون 13 128 گیگ", "iPhone 13", "128 گیگابایت", "Midnight", "کارکرده", 125_000_000)]


@pytest.fixture(scope="module")
def tg_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("tgsales")
    code = ("import os,sys,json; os.environ.setdefault('BOT_TOKEN','0:x'); os.environ.setdefault('ADMIN_ID','1');"
            f"sys.path.insert(0,{str(TG)!r}); import bot;"
            "json.dump(bot.DEFAULT_INTENTS, open('faq.json','w',encoding='utf-8'), ensure_ascii=False)")
    subprocess.run([sys.executable, "-c", code], cwd=d, check=True, timeout=120)
    sys.path.insert(0, str(TG))
    import catalog
    items = [catalog.normalize({"id": i + 100, "name": n, "permalink": f"https://stland.ir/p/{i}", "is_in_stock": True,
                                "images": [{"src": f"https://stland.ir/img/{i}.jpg"}],
                                "prices": {"price": str(p), "currency_minor_unit": 0}, "categories": [{"name": "آیفون کارکرده"}],
                                "attributes": [{"name": k, "terms": [{"name": v}]} for k, v in
                                               (("مدل", m), ("حافظه", g), ("رنگ", c), ("وضعیت", s)) if v]})
             for i, (n, m, g, c, s, p) in enumerate(SAMPLE)]
    (d / "catalog.json").write_text(json.dumps({"updated": time.time(), "items": items}, ensure_ascii=False), encoding="utf-8")
    (d / "data.json").write_text(json.dumps({"3": "اقساط ۶ ماهه"}, ensure_ascii=False), encoding="utf-8")
    return d


class SalesIG(IG):
    def __init__(self, cards_fail=False):
        super().__init__()
        self.cards, self.cards_fail = [], cards_fail

    async def send_cards(self, uid, cards):
        if self.cards_fail:
            raise RuntimeError("IG 400: template not allowed")
        self.cards.append((uid, cards))
        self.calls.append(("cards", uid, len(cards)))
        return f"c{len(self.calls)}"


@pytest.fixture
def env(tg_dir, tmp_path, monkeypatch):
    for f in ("inbox", "notify"):
        p = tg_dir / f
        if p.exists():
            for x in p.iterdir():
                x.unlink()
    monkeypatch.setattr(config, "TG_DATA_DIR", str(tg_dir))
    monkeypatch.setattr(config, "IG_USER_ID", "me")
    monkeypatch.setattr(config, "SEND_DELAY_MIN", 0)
    monkeypatch.setattr(config, "SEND_DELAY_MAX", 0)
    monkeypatch.setattr(config, "PANEL_PASSWORD", "pw")
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    monkeypatch.setattr(config, "WEB_DIST", str(tmp_path / "nodist"))
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    auth._fails.clear()
    db.init()
    ai.set_client(None)
    with db.connect() as c:
        ai.save_settings(c, {"brain_enabled": True, "typing_indicator": False})
    yield tg_dir
    ai.set_client(None)


def notes(d):
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted((d / "notify").glob("*.json"))]


def postback(mid, payload, title="🛒 سفارش", sender="u9"):
    return {"sender": {"id": sender}, "recipient": {"id": "me"}, "timestamp": 1, "postback": {"mid": mid, "title": title,
                                                                                             "payload": payload}}


def last_dm(ig):
    return [x for x in ig.calls if x[0] == "dm"][-1][2]


@pytest.mark.asyncio
async def test_showcase_cards_for_stock_questions(env):
    ig = SalesIG()
    with db.connect() as c:
        assert await run(ig, c, "e1", "message", msg("m1", "قیمت آیفون ۱۳ پرو چنده؟")) == "done"
        uid, cards = ig.cards[0]
        assert uid == "u9" and cards[0]["id"] == "100" and cards[0]["image"].startswith("https://")
        assert "۱۹۰" in cards[0]["subtitle"] and cards[0]["url"] == "https://stland.ir/?p=100"
        intro = last_dm(ig).split("\n")       # سرخط و حداکثر یک اشاره به مدل نزدیک؛ فهرست کامل در کارت‌هاست
        assert len(intro) <= 2 and "stland.ir" not in last_dm(ig) and all(x.startswith("💡") for x in intro[1:])
        assert c.execute("SELECT text FROM messages WHERE direction='out' ORDER BY created_at DESC").fetchone()[0].startswith("🛍")
        ai.save_settings(c, {"showcase_cards": False})
        await run(ig, c, "e2", "message", msg("m2", "قیمت آیفون ۱۳ پرو چنده؟"))
        assert len(ig.cards) == 1 and "190" in last_dm(ig).replace("۱۹۰", "190")


@pytest.mark.asyncio
async def test_cards_fall_back_to_text(env):
    ig = SalesIG(cards_fail=True)
    with db.connect() as c:
        await run(ig, c, "e1", "message", msg("m1", "قیمت آیفون ۱۳ پرو چنده؟"))
        assert "stland.ir/?p=100" in last_dm(ig)


def test_card_payload_shape():
    from app.instagram import Instagram
    sent = {}

    class I(Instagram):
        async def _post(self, path, **kw):
            sent.update(kw["json"])
            return {"message_id": "x"}
    asyncio.run(I("t", "me").send_cards("u1", [{"id": "5", "title": "آیفون", "subtitle": "۱", "image": "https://i/1.jpg",
                                               "url": "https://stland.ir/?p=5"}]))
    el = sent["message"]["attachment"]["payload"]["elements"][0]
    assert sent["message"]["attachment"]["payload"]["template_type"] == "generic"
    assert el["image_url"] == "https://i/1.jpg" and el["buttons"][1] == {"type": "postback", "title": "🛒 سفارش",
                                                                         "payload": "ORDER:5"}


@pytest.mark.asyncio
async def test_order_flow_from_card_button_and_receipt(env):
    ig = SalesIG()
    with db.connect() as c:
        ai.save_settings(c, {"order_payment_text": "کارت ۶۰۳۷-۰۰۰۰ به نام فروشگاه"})
        assert await run(ig, c, "p1", "postback", postback("pb1", "ORDER:100")) == "done"
        assert "آیفون 13 پرو 256" in last_dm(ig) and "نام و نام خانوادگی" in last_dm(ig)
        await run(ig, c, "e1", "message", msg("m1", "ع"))
        assert "با حروف" in last_dm(ig)
        await run(ig, c, "e2", "message", msg("m2", "علی رضایی"))
        assert "موبایل" in last_dm(ig)
        await run(ig, c, "e3", "message", msg("m3", "۱۲۳"))
        assert "درست نیست" in last_dm(ig)
        # سؤال وسط کار: جواب عادی، سفارش منتظر می‌ماند
        await run(ig, c, "e4", "message", msg("m4", "شرایط اقساط چیه؟"))
        assert orders.active(c, "u9")
        await run(ig, c, "e5", "message", msg("m5", "۰۹۱۲۱۲۳۴۵۶۷"))
        await run(ig, c, "e6", "message", msg("m6", "تهران"))
        await run(ig, c, "e7", "message", msg("m7", "خیابان آزادی، کوچه ۵، پلاک ۱۲، کد پستی ۱۲۳۴۵"))
        assert "خلاصه‌ی سفارش" in last_dm(ig) and "۰۹۱۲۱۲۳۴۵۶۷" in last_dm(ig) or "09121234567" in last_dm(ig)
        await run(ig, c, "e8", "message", msg("m8", "بله"))
        assert "ثبت شد" in last_dm(ig) and "۶۰۳۷" in last_dm(ig) or "6037" in last_dm(ig)
        o = c.execute("SELECT * FROM orders").fetchone()
        assert o["status"] == "awaiting_payment" and o["product_id"] == "100" and o["price"] == 190_000_000
        assert o["phone"] == "09121234567" and o["name"] == "علی رضایی" and not orders.active(c, "u9")
        cust = crm.get(c, "ig:u9")
        assert cust["name"] == "علی رضایی" and cust["phone"] == "09121234567" and "قصد خرید" in cust["tags"]
        assert "سفارش تازه #1" in notes(env)[-1]["text"]
        # عکس رسید
        img = msg("m9", attachments=[{"type": "image", "payload": {"url": "https://cdn.ig/receipt.jpg"}}])
        assert await run(ig, c, "e9", "message", img) == "done"
        assert "رسید" in last_dm(ig)
        o = c.execute("SELECT * FROM orders").fetchone()
        assert o["status"] == "receipt" and o["receipt_url"] == "https://cdn.ig/receipt.jpg"
        assert notes(env)[-1]["photo"] == "https://cdn.ig/receipt.jpg"
        # عکس بعدی که رسید نیست: برای همکار
        assert await run(ig, c, "e10", "message", msg("m10", attachments=[{"type": "image", "payload": {"url": "https://x/2.jpg"}}])) == "skipped"


@pytest.mark.asyncio
async def test_order_from_text_skips_known_fields_and_cancel(env):
    ig = SalesIG()
    with db.connect() as c:
        crm.touch(c, "ig", "u9", "ali", "message", "شماره‌ام ۰۹۳۵۱۱۱۲۲۳۳")
        crm.update(c, "ig:u9", {"name": "علی"})
        assert await run(ig, c, "e1", "message", msg("m1", "می‌خوام بخرم آیفون ۱۳ ۱۲۸")) == "done"
        assert "آیفون 13 128 گیگ" in last_dm(ig) and "شهر" in last_dm(ig)    # نام و شماره را دارد
        await run(ig, c, "e2", "message", msg("m2", "لغو"))
        assert "لغو شد" in last_dm(ig) and not orders.active(c, "u9")
        # حافظه‌ی گفتگو: «ثبت سفارش» برای همان مدلی که قبلاً گفته بود
        await run(ig, c, "e3a", "message", msg("m3a", "ثبت سفارش"))
        assert "آیفون 13 128 گیگ" in last_dm(ig)
        await run(ig, c, "e3b", "message", msg("m3b", "لغو"))
        c.execute("DELETE FROM conv_memo")
        # بدون پیام پرداخت: همکار هماهنگ می‌کند
        await run(ig, c, "e3", "message", msg("m3", "ثبت سفارش"))
        assert "کدوم محصول" in last_dm(ig)
        for i, t in enumerate(["۱۳ پرو", "کرج", "کرج، خیابان اصلی، پلاک ۴۴", "بله"]):
            await run(ig, c, f"f{i}", "message", msg(f"n{i}", t))
        assert "همکارم برای هماهنگی" in last_dm(ig)
        assert c.execute("SELECT status, product FROM orders").fetchone()[:] == ("new", "آیفون 13 پرو 256")
        ai.save_settings(c, {"order_enabled": False})
        await run(ig, c, "e4", "message", msg("m4", "ثبت سفارش"))
        assert not orders.active(c, "u9")


@pytest.mark.asyncio
async def test_rule_pause_ai_handoff_and_story_scope(env):
    ig = SalesIG()
    with db.connect() as c:
        db.upsert_rule(c, {"name": "حضوری", "channels": ["dm"], "triggers": [{"match": "contains", "value": "حضوری"}],
                           "actions": {"dm_replies": ["همکارم الان باهاتون هماهنگ می‌کنه"]},
                           "advanced": {"pause_ai_minutes": 60, "handoff": True}})
        db.upsert_rule(c, {"name": "استوری خاص", "channels": ["story_reply"], "post_scope": ["st1"],
                           "triggers": [{"match": "any"}], "actions": {"dm_replies": ["این استوری مخصوص جشنواره است"]}})
        await run(ig, c, "e1", "message", msg("m1", "میخوام حضوری بیام"))
        assert db.human_until(c, "u9") > time.time() + 50 * 60
        assert c.execute("SELECT reason FROM handoffs").fetchone()[0] == "دستور «حضوری»"
        await run(ig, c, "e2", "message", msg("m2", "قیمت؟", sender="u2", reply_to={"story": {"id": "st2"}}))
        assert "جشنواره" not in last_dm(ig)
        await run(ig, c, "e3", "message", msg("m3", "قیمت؟", sender="u3", reply_to={"story": {"id": "st1"}}))
        assert "جشنواره" in last_dm(ig)


@pytest.mark.asyncio
async def test_bulk_and_lost_opportunities(env):
    ig = SalesIG()
    now = time.time()
    with db.connect() as c:
        for uid, ago in (("a", 5 * 3600), ("b", 30 * 3600)):
            crm.touch(c, "ig", uid, uid, "message", "قیمت ۱۳ پرو")
            db.add_message(c, f"in-{uid}", uid, "in", "قیمت ۱۳ پرو", created_at=now - ago)
            c.execute("UPDATE customers SET last_seen=? WHERE user_id=?", (now - ago, uid))
            c.execute("INSERT INTO ai_log(created_at,channel,user_id,input,action,intent) VALUES (?,?,?,?,?,?)",
                      (now - ago, "dm", uid, "قیمت ۱۳ پرو", "reply", "price"))
        lost = {x["user_id"]: x for x in reports.lost(c, 14, 3)}
        assert set(lost) == {"a", "b"} and lost["a"]["window_left"] > 0 and lost["b"]["window_left"] == 0
        assert [x["user_id"] for x in crm.search(c, window="open")] == ["a"]
        r = crm.bulk(c, ["ig:a", "ig:b"], "message", "هنوز ۱۳ پرو رو می‌خواید؟ موجوده 🙏")
        assert r == {"queued": 1, "window_closed": 1}
        assert await worker.process_followups(ig, c, now + 60) == 1 and ig.calls[-1][1] == "a"
        assert crm.bulk(c, ["ig:a", "ig:b"], "tag_add", "پیگیری")["changed"] == 2
        assert len(crm.search(c, tag="پیگیری")) == 2
        c.execute("INSERT INTO orders(user_id,status,created_at,updated_at) VALUES ('a','new',?,?)", (now, now))
        assert [x["user_id"] for x in reports.lost(c, 14, 3)] == ["b"]
        assert [x["user_id"] for x in crm.search(c, ordered="yes")] == ["a"]


def test_webhook_signature_and_lead(env, monkeypatch):
    got = []

    def handler(request):
        got.append(request)
        return httpx.Response(200)
    ok = asyncio.run(webhook.deliver("https://crm.example/hook", "s3cret", "lead", {"phone": "09120000000"},
                                     transport=httpx.MockTransport(handler)))
    assert ok and got[0].headers["X-Igbot-Signature"] == webhook.sign("s3cret", got[0].content)
    assert json.loads(got[0].content)["data"]["phone"] == "09120000000"
    with db.connect() as c:
        with pytest.raises(ValueError):
            webhook.save(c, {"url": "http://insecure"})
        pub = webhook.save(c, {"url": "https://crm.example/hook", "secret": "s3cret"})
        assert pub["secret_set"] and "secret" not in pub and pub["log"][0]["ok"]
    fired = []
    monkeypatch.setattr(webhook, "fire", lambda c, ev, data: fired.append((ev, data)) or True)
    with db.connect() as c:
        crm.touch(c, "ig", "u5", "x", "message", "شماره‌م ۰۹۱۲۰۰۰۰۰۰۰")
        crm.touch(c, "ig", "u5", "x", "message", "دوباره ۰۹۱۲۰۰۰۰۰۰۰")
    assert [e for e, _ in fired] == ["lead"] and fired[0][1]["phone"] == "09120000000"


class AdminFake:
    def __init__(self, out):
        self.out, self.seen = out, None

    async def complete(self, model, system, messages, effort, schema=None, hint=None, max_tokens=2048):
        self.seen = (system, messages, schema)
        return json.dumps(self.out, ensure_ascii=False), {"input_tokens": 10, "output_tokens": 5}, "end_turn"


def test_admin_chat_proposes_and_applies(env):
    out = {"reply": "پیام خوش‌آمد و جواب گارانتی عوض می‌شود",
           "ops": [{"op": "setting", "id": "", "keys": [], "examples": [], "answer": "", "action": "", "key": "welcome_text",
                    "text": "", "value_json": "\"سلام به استوک لند خوش اومدی 🌸\""},
                   {"op": "setting", "id": "", "keys": [], "examples": [], "answer": "", "action": "", "key": "provider",
                    "text": "", "value_json": "\"openai\""},
                   {"op": "intent_upsert", "id": "", "keys": ["گارانتی"], "examples": ["گارانتی دارید؟"],
                    "answer": "۱۸ ماه گارانتی داریم", "action": "", "key": "", "text": "", "value_json": ""}]}
    fake = AdminFake(out)
    ai.set_client(fake)
    with TestClient(create_app(SalesIG())) as cl:
        cl.post("/api/login", json={"password": "pw"})
        r = cl.post("/api/ai/admin-chat", json={"text": "به کسی که گارانتی پرسید بگو ۱۸ ماه"})
        assert r.status_code == 200, r.text
        ops = r.json()["ops"]
        assert [o["op"] for o in ops] == ["setting", "intent_upsert"]      # تنظیم سرویس هوش مصنوعی حذف شد
        assert "گارانتی" in fake.seen[0][0]["text"] and fake.seen[2] is ai_admin.SCHEMA
        with db.connect() as c:
            assert ai.settings(c)["welcome_text"] == ""                     # هنوز چیزی اعمال نشده
        res = cl.post("/api/ai/admin-apply", json={"ops": ops}).json()["results"]
        assert all(x.startswith("✅") for x in res), res
        with db.connect() as c:
            assert ai.settings(c)["welcome_text"].startswith("سلام به استوک لند")
        queued = [json.loads(f.read_text(encoding="utf-8")) for f in (env / "inbox").glob("*.json")]
        assert queued[0]["op"] == "intent_upsert" and queued[0]["item"]["answer"] == "۱۸ ماه گارانتی داریم"
        bad = cl.post("/api/ai/admin-apply", json={"ops": [{"op": "intent_delete", "id": "i_price"}]}).json()["results"]
        assert bad[0].startswith("❌")
    ai.set_client(None)
    with TestClient(create_app(SalesIG())) as cl:
        cl.post("/api/login", json={"password": "pw"})
        r = cl.post("/api/ai/admin-chat", json={"text": "سلام"})
        assert r.status_code == 422 and "کلید" in r.json()["detail"]


def test_orders_api_and_rule_copy(env):
    with TestClient(create_app(SalesIG())) as cl:
        cl.post("/api/login", json={"password": "pw"})
        now = time.time()
        with db.connect() as c:
            crm.touch(c, "ig", "u1", "ali", "message", "سلام")
            c.execute("INSERT INTO orders(user_id,product,name,phone,status,created_at,updated_at) "
                      "VALUES ('u1','آیفون','علی','09120000000','receipt',?,?)", (now, now))
        d = cl.get("/api/orders").json()
        assert d["items"][0]["status_label"] == "رسید رسیده" and d["stats"]["receipt"]["count"] == 1
        assert cl.put("/api/orders/1", json={"status": "bogus"}).status_code == 422
        assert cl.put("/api/orders/1", json={"status": "done", "note": "تحویل حضوری"}).json()["status"] == "done"
        with db.connect() as c:
            assert "خرید کرده" in crm.get(c, "ig:u1")["tags"]
        rid = cl.post("/api/rules", json={"name": "قیمت", "channels": ["dm"], "triggers": [{"match": "contains", "value": "قیمت"}],
                                          "actions": {"dm_replies": ["سلام"]}}).json()["id"]
        new = cl.post(f"/api/rules/{rid}/copy", json={"channels": ["comment"]}).json()["id"]
        r = next(x for x in cl.get("/api/rules").json() if x["id"] == new)
        assert r["channels"] == ["comment"] and r["name"] == "قیمت (کپی)" and not r["enabled"]
        ok = cl.post("/api/rules", json={"name": "فقط توقف", "channels": ["dm"], "triggers": [{"match": "contains", "value": "x"}],
                                         "actions": {}, "advanced": {"pause_ai_minutes": 30}})
        assert ok.status_code == 200, ok.text
        assert cl.get("/api/reports/lost").status_code == 200
        assert cl.get("/api/customers?window=open&phone=no").status_code == 200


def test_telegram_orders_through_core(env):
    from app import internal
    with TestClient(create_app(SalesIG())) as cl:
        key = internal.key_path().read_text().strip()
        H = {"X-Internal-Key": key}

        def say(**kw):
            r = cl.post("/internal/order", headers=H, json={"channel": "telegram", "user_id": "555", "username": "ali", **kw})
            assert r.status_code == 200, r.text
            return r.json()
        assert say(text="قیمت ۱۳ پرو چنده؟")["reply"] is None             # به سفارش ربطی ندارد
        assert "آیفون 13 پرو 256" in say(product_id="100")["reply"]           # «رزرو می‌کنم» زیر کارت
        for t in ("علی رضایی", "۰۹۱۲۱۲۳۴۵۶۷", "قم", "خیابان عمار یاسر، کوچه ۳، پلاک ۸"):
            say(text=t)
        done = say(text="بله")
        assert "ثبت شد" in done["reply"] and done["order_id"] and not done["receipt"]
        with db.connect() as c:
            o = c.execute("SELECT * FROM orders").fetchone()
            assert (o["channel"], o["user_id"], o["product_id"]) == ("tg", "555", "100")
            assert crm.get(c, "tg:555")["phone"] == "09121234567"
            assert not orders.active(c, "555") and not orders.active(c, "555", "tg")
        n = notes(env)[-1]
        assert n["topic"] == "orders" and "از تلگرام" in n["text"]
        rec = say(image=True)
        assert rec["receipt"] and rec["order_id"] == done["order_id"] and "رسید" in rec["reply"]
        assert notes(env)[-1]["topic"] == "orders" and "photo" not in notes(env)[-1]
        assert say(image=True)["reply"] is None                                # عکس بعدی رسید نیست
        # «ثبت سفارش» با مدلی که درباره‌اش حرف می‌زد
        r = say(text="ثبت سفارش", hint="آیفون ۱۳")
        assert "شهر" in r["reply"] or "کدوم آیفون ۱۳" in r["reply"] or "آیفون 13 128" in r["reply"]
        assert cl.post("/internal/order", json={"channel": "telegram", "user_id": "1"}).status_code == 403


@pytest.mark.asyncio
async def test_conversation_memory_budget_and_model(env):
    from app import memory
    ig = SalesIG()
    with db.connect() as c:
        ai.save_settings(c, {"showcase_cards": False})
        await run(ig, c, "e1", "message", msg("m1", "بودجه‌ام ۱۵۰ میلیونه"))
        assert memory.recall(c, "u9")["budget"] == 150_000_000
        # بعداً بدون گفتن بودجه: فقط تا ۱۵۰ میلیون (۱۳ پرو ۱۹۰ نمی‌آید)
        await run(ig, c, "e2", "message", msg("m2", "یه گوشی کارکرده میخوام"))
        assert "آیفون 13 128" in last_dm(ig) and "آیفون 13 پرو 256" not in last_dm(ig)
        # مدل مشخص: بودجه‌ی قبلی جلوی جوابش را نمی‌گیرد
        await run(ig, c, "e3", "message", msg("m3", "قیمت ۱۳ پرو چنده؟"))
        assert "آیفون 13 پرو 256" in last_dm(ig)
        assert "«ثبت سفارش»" in last_dm(ig).split("\n")[-1]                    # دعوت به خرید، خط آخر
        ai.save_settings(c, {"order_enabled": False})
        await run(ig, c, "e4", "message", msg("m4", "قیمت ۱۳ پرو چنده؟"))
        assert "ثبت سفارش" not in last_dm(ig)
        ai.save_settings(c, {"order_enabled": True})
        assert memory.recall(c, "u9") == {"product": "آیفون ۱۳ پرو", "budget": 150_000_000}
        assert "۱۵۰ میلیون" in memory.note(memory.recall(c, "u9"))
        c.execute("UPDATE conv_memo SET updated_at=updated_at-7*3600")
        assert memory.recall(c, "u9") == {}                                   # بعد از ۶ ساعت فراموش می‌شود


@pytest.mark.asyncio
async def test_auto_followup_once_for_silent_interested_customer(env):
    ig = SalesIG()
    now = time.time()
    with db.connect() as c:
        await run(ig, c, "e1", "message", msg("m1", "قیمت ۱۳ پرو چنده؟"))
        await run(ig, c, "e2", "message", msg("m2", "قیمت ۱۳ پرو چنده؟", sender="u8"))
        c.execute("UPDATE messages SET created_at=? WHERE direction='in'", (now - 4 * 3600,))
        c.execute("UPDATE ai_log SET created_at=?", (now - 4 * 3600,))
        assert await worker.auto_followups(ig, c) == 0                         # پیش‌فرض خاموش
        ai.save_settings(c, {"auto_followup_enabled": True, "auto_followup_hours": 3})
        db.set_human(c, "u8", 60)                                             # همکار با u8 در گفتگوست
        n = len(ig.calls)
        assert await worker.auto_followups(ig, c) == 1
        assert ig.calls[n][1] == "u9" and "آیفون ۱۳ پرو" in ig.calls[n][2]
        assert await worker.auto_followups(ig, c) == 0                         # فقط یک بار
        db.clear_human(c, "u8")
        c.execute("INSERT INTO orders(user_id,status,created_at,updated_at) VALUES ('u8','new',?,?)", (now, now))
        assert await worker.auto_followups(ig, c) == 0                         # سفارش داده
        # پنجره‌ی ۲۴ ساعته بسته
        c.execute("DELETE FROM auto_followups"); c.execute("DELETE FROM orders")
        c.execute("UPDATE messages SET created_at=? WHERE direction='in'", (now - 25 * 3600,))
        assert await worker.auto_followups(ig, c) == 0


GOOD = {"action": "reply", "reply": "برای سفرهای طولانی مدل‌های پرو مکس به‌خاطر باتری بزرگ‌تر انتخاب بهتری هستن 🙂",
        "public_reply": "", "intent": "other", "confidence": 0.9, "handoff_reason": ""}


def _queued(d):
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted((d / "inbox").glob("*.json"))]


@pytest.mark.asyncio
async def test_customer_satisfaction_teaches_offline_brain(env):
    from tests.test_ai import FakeClaude
    from app import learning
    ai.set_client(FakeClaude(GOOD))
    ig = SalesIG()
    q = "برای سفر زیاد کدوم آیفون باتریش بهتر جواب میده"
    with db.connect() as c:
        ai.save_settings(c, {"enabled": True})
        await run(ig, c, "e1", "message", msg("m1", q))
        assert ig.qr[GOOD["reply"]][:2] == ["👍 مفید بود", "👎 نه"]       # فقط زیر جواب هوش مصنوعی
        await run(ig, c, "e2", "message", msg("m2", "👍 مفید بود"))
        assert "ممنون از نظرت" in last_dm(ig)
        assert c.execute("SELECT customer_vote FROM ai_log WHERE input=?", (q,)).fetchone()[0] == "up"
        op = _queued(env)[-1]
        assert op["op"] == "intent_upsert" and op["item"]["examples"] == [q] and op["item"]["answer"] == GOOD["reply"]
        assert learning.stats(c)["learned"] == 1
        # همان سؤال دوباره پسندیده شود: تکراری یاد گرفته نمی‌شود
        await run(ig, c, "e3", "message", msg("m3", q))
        await run(ig, c, "e4", "message", msg("m4", "👍 مفید بود"))
        assert learning.stats(c)["learned"] == 1 and len(_queued(env)) == 1
        # جواب قیمت‌دار (کهنه می‌شود) یاد گرفته نمی‌شود
        ai.set_client(FakeClaude({**GOOD, "reply": "۱۳ پرو الان ۱۹۰ میلیون تومانه"}))
        await run(ig, c, "e5", "message", msg("m5", "یه سؤال دیگه درباره‌ی گوشی دارم راستش"))
        await run(ig, c, "e6", "message", msg("m6", "👍 مفید بود"))
        assert learning.stats(c)["learned"] == 1
        # ناپسند: به همکار
        ai.set_client(FakeClaude(GOOD))
        await run(ig, c, "e7", "message", msg("m7", q, sender="u5"))
        await run(ig, c, "e8", "message", msg("m8", "👎 نه", sender="u5"))
        assert "همکارم" in last_dm(ig) and db.human_until(c, "u5")
        assert c.execute("SELECT reason FROM handoffs WHERE user_id='u5'").fetchone()[0].startswith("مشتری جواب")
        # برگرداندن آموخته از پنل
        lid = learning.items(c)[0]["id"]
        c.execute("UPDATE events SET status='done'")      # کارگر پس‌زمینه‌ی برنامه‌ی پنل دوباره پردازششان نکند
    with TestClient(create_app(SalesIG())) as cl:
        cl.post("/api/login", json={"password": "pw"})
        d = cl.get("/api/ai/learned").json()
        assert d["stats"] == {"up": 3, "down": 1, "learned": 1} and d["items"][0]["question"] == q
        assert cl.delete(f"/api/ai/learned/{lid}").status_code == 200
        assert cl.delete(f"/api/ai/learned/{lid}").status_code == 404
    ai.set_client(None)


def test_telegram_feedback_through_core(env):
    from tests.test_ai import FakeClaude
    from app import internal
    ai.set_client(FakeClaude(GOOD))
    with TestClient(create_app(SalesIG())) as cl:
        H = {"X-Internal-Key": internal.key_path().read_text().strip()}
        with db.connect() as c:
            ai.save_settings(c, {"enabled": True})
        t = cl.post("/internal/think", headers=H, json={"channel": "telegram", "user_id": "77", "text": "سفر زیاد میرم چی بخرم"}).json()
        assert t["ask_feedback"] and t["log_id"]
        bad = cl.post("/internal/feedback", headers=H, json={"channel": "telegram", "user_id": "78", "log_id": t["log_id"], "vote": "up"})
        assert bad.json() == {"ok": False, "learned": False}                    # جواب دیگری را نمی‌شود رأی داد
        ok = cl.post("/internal/feedback", headers=H, json={"channel": "telegram", "user_id": "77", "log_id": t["log_id"], "vote": "up"})
        assert ok.json() == {"ok": True, "learned": True}
        assert _queued(env)[-1]["item"]["examples"] == ["سفر زیاد میرم چی بخرم"]
    ai.set_client(None)
