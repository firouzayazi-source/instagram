"""تکمیل اینستاگرام: استوری، دکمه‌ی پاسخ سریع، شروع گفتگو و خوش‌آمد، نظارت کامنت، پرونده‌ی مشتری."""
import json

import pytest
from fastapi.testclient import TestClient

from app import ai, auth, config, crm, db, worker
from app.main import create_app, extract_events
from app.rules import Incoming, rule_matches
from tests.test_ai import FakeClaude
from tests.test_webhook import FakeIG


class IG(FakeIG):
    def __init__(self):
        super().__init__()
        self.actions, self.qr, self.hidden, self.ice = [], {}, [], None

    async def send_dm(self, uid, text, quick_replies=None):
        self.calls.append(("dm", uid, text))
        if quick_replies:
            self.qr[text] = quick_replies
        return f"d{len(self.calls)}"

    async def sender_action(self, uid, action):
        self.actions.append(action)

    async def hide_comment(self, cid, hide=True):
        self.hidden.append((cid, hide))

    async def set_ice_breakers(self, qs):
        self.ice = qs


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "IG_USER_ID", "me")
    monkeypatch.setattr(config, "SEND_DELAY_MIN", 0)
    monkeypatch.setattr(config, "SEND_DELAY_MAX", 0)
    monkeypatch.setattr(config, "PANEL_PASSWORD", "pw")
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    monkeypatch.setattr(config, "WEB_DIST", str(tmp_path / "nodist"))
    auth._fails.clear()
    db.init()
    fake = FakeClaude()
    ai.set_client(fake)
    yield fake
    ai.set_client(None)


def msg(mid, text=None, sender="u9", **extra):
    m = {"mid": mid, **({"text": text} if text is not None else {}), **extra}
    return {"sender": {"id": sender}, "recipient": {"id": "me"}, "timestamp": 1_700_000_000_000, "message": m}


async def run(ig, c, eid, kind, payload):
    db.add_event(c, eid, kind, payload)
    row = c.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
    return await worker.handle_event(ig, row, c)


def test_extract_and_parse_new_events():
    body = {"entry": [{"messaging": [
        msg("m1", attachments=[{"type": "story_mention", "payload": {"url": "https://x"}}]),
        msg("m2", "قیمتش چنده؟", reply_to={"story": {"id": "s1", "url": "https://x"}}),
        {"sender": {"id": "u9"}, "recipient": {"id": "me"}, "postback": {"mid": "pb1", "title": "شرایط اقساط چیه؟", "payload": "شرایط اقساط چیه؟"}},
        msg("m3", is_deleted=True),
    ]}]}
    ev = extract_events(body)
    assert [k for _, k, _ in ev] == ["message", "message", "postback", "message"]
    incs = [worker.parse_event(k, p) for _, k, p in ev]
    assert incs[0].source == "mention" and incs[1].source == "story_reply" and incs[1].text == "قیمتش چنده؟"
    assert incs[2].source == "icebreaker" and incs[2].text == "شرایط اقساط چیه؟" and incs[3] is None


def test_rule_channels_for_story():
    base = {"post_scope": "all", "triggers": [{"match": "any"}], "advanced": {}}
    mention = Incoming("dm", "u", "", source="mention")
    story = Incoming("dm", "u", "سلام", source="story_reply")
    assert not rule_matches({**base, "channels": ["dm"]}, mention, None)      # دستور دایرکت به منشن نمی‌خورد
    assert rule_matches({**base, "channels": ["mention"]}, mention, None)
    assert rule_matches({**base, "channels": ["dm"]}, story, None)
    assert rule_matches({**base, "channels": ["story_reply"]}, story, None)
    assert not rule_matches({**base, "channels": ["story_reply"]}, Incoming("dm", "u", "سلام"), None)


@pytest.mark.asyncio
async def test_mention_reply_and_story_context(env):
    ig = IG()
    with db.connect() as c:
        mention = msg("m1", attachments=[{"type": "story_mention", "payload": {}}])
        assert await run(ig, c, "e1", "message", mention) == "ignored"          # پیش‌فرض خاموش
        ai.save_settings(c, {"mention_reply_enabled": True})
        assert await run(ig, c, "e2", "message", msg("m2", attachments=[{"type": "story_mention"}])) == "done"
        assert ig.calls[-1][2] in ai.DEFAULTS["mention_replies"]
        assert "منشن" in c.execute("SELECT text FROM messages WHERE id='m1'").fetchone()[0]

        ai.save_settings(c, {"enabled": True})
        assert await run(ig, c, "e3", "message", msg("m3", "اینو دارید؟", reply_to={"story": {"id": "s"}})) == "done"
        sent_prompt = env.calls[-1]["messages"][0]["content"]
        assert "استوری" in sent_prompt and "## زمینه" in sent_prompt
        assert "↩️" in c.execute("SELECT text FROM messages WHERE id='m3'").fetchone()[0]


@pytest.mark.asyncio
async def test_welcome_quick_replies_typing(env):
    ig = IG()
    with db.connect() as c:
        ai.save_settings(c, {"enabled": True, "welcome_text": "خوش اومدی به استوک لند 🌸", "quick_replies_enabled": True})
        assert await run(ig, c, "e1", "message", msg("m1", "قیمت ۱۳ پرو؟")) == "done"
        texts = [t for _, _, t in ig.calls]
        assert texts[0] == "خوش اومدی به استوک لند 🌸" and texts[1] == env.out["reply"]
        assert ig.qr[env.out["reply"]] == ["👍 مفید بود", "👎 نه"] + ai.DEFAULTS["dm_quick_replies"]   # رضایت + منو
        assert "typing_on" in ig.actions and "mark_seen" in ig.actions
        await run(ig, c, "e2", "message", msg("m2", "یه سؤال دیگه"))
        assert [t for _, _, t in ig.calls].count("خوش اومدی به استوک لند 🌸") == 1       # فقط اولین پیام

        # دکمه‌ی پاسخ سریع روی دستور کلمه‌ای
        db.upsert_rule(c, {"name": "اقساط", "channels": ["dm"], "triggers": [{"match": "contains", "value": "اقساط"}],
                           "actions": {"dm_replies": ["اقساط ۶ ماهه داریم"], "quick_replies": ["📄 مدارک لازم"]}})
        await run(ig, c, "e3", "message", msg("m3", "اقساط دارید؟"))
        assert ig.qr["اقساط ۶ ماهه داریم"] == ["📄 مدارک لازم"]


@pytest.mark.asyncio
async def test_comment_moderation(env):
    ig = IG()
    com = lambda i, t: {"id": i, "text": t, "from": {"id": "u5", "username": "x"}, "media": {"id": "m1"}}  # noqa: E731
    with db.connect() as c:
        db.upsert_rule(c, {"name": "همه", "channels": ["comment"], "triggers": [{"match": "any"}],
                           "actions": {"public_replies": ["دایرکت رو ببین"]}})
        assert await run(ig, c, "c1", "comment", com("c1", "کثافت آشغال")) == "hidden"
        assert ig.hidden == [("c1", True)] and ig.calls == []
        assert c.execute("SELECT hidden, hidden_reason FROM comments WHERE id='c1'").fetchone()[1] == "توهین"
        assert await run(ig, c, "c2", "comment", com("c2", "ارزون‌تر از ما بخرید www.rival.ir")) == "done"   # لینک: پیش‌فرض خاموش
        ai.save_settings(c, {"mod_links": True, "mod_words": ["رقیب"]})
        assert await run(ig, c, "c3", "comment", com("c3", "بیا پیج www.rival.ir")) == "hidden"
        assert await run(ig, c, "c4", "comment", com("c4", "پیج رقیب ارزون‌تره")) == "hidden"
        assert await run(ig, c, "c5", "comment", com("c5", "@ali اینو ببین 😍")) == "done"                 # منشن دوست مشکلی ندارد


@pytest.mark.asyncio
async def test_crm_profile(env):
    ig = IG()
    with db.connect() as c:
        ai.save_settings(c, {"enabled": True})
        env.out = {**env.out, "action": "handoff", "intent": "purchase", "handoff_reason": "قصد خرید"}
        await run(ig, c, "e1", "message", msg("m1", "می‌خوام بخرم، شماره‌م ۰۹۱۲ ۳۴۵ ۶۷۸۹ هست"))
        await run(ig, c, "c1", "comment", {"id": "c1", "text": "قیمت؟", "from": {"id": "u9", "username": "ali"}, "media": {"id": "m"}})
        p = crm.get(c, "ig:u9")
        assert p["phone"] == "09123456789" and "قصد خرید" in p["tags"] and p["messages"] == 1 and p["comments"] == 1
        kinds = {e["kind"] for e in p["timeline"]}
        assert {"dm_in", "dm_out", "comment", "handoff"} <= kinds
        with pytest.raises(ValueError):
            crm.update(c, "ig:u9", {"phone": "123"})
        p = crm.update(c, "ig:u9", {"tags": ["VIP", "VIP", "اقساطی"], "notes": "مشتری قدیمی", "name": "علی"})
        assert p["tags"] == ["VIP", "اقساطی"] and p["name"] == "علی"
        assert [x["id"] for x in crm.search(c, tag="VIP")] == ["ig:u9"] and crm.search(c, q="علی")


def test_api_ice_breakers_hide_customers(env, monkeypatch):
    ig = IG()
    with TestClient(create_app(ig)) as cl:
        cl.post("/api/login", json={"password": "pw"})
        r = cl.post("/api/instagram/ice-breakers", json={"questions": ["قیمت؟", "اقساط؟"]})
        assert r.status_code == 409 and ig.ice is None                    # هنوز وصل نیست؛ ولی ذخیره شد
        assert cl.get("/api/ai/settings").json()["settings"]["ice_breakers"] == ["قیمت؟", "اقساط؟"]
        monkeypatch.setattr(config, "IG_ACCESS_TOKEN", "t")
        monkeypatch.setattr(config, "IG_USER_ID", "me")
        assert cl.post("/api/instagram/ice-breakers", json={"questions": ["قیمت؟"]}).json()["ok"] and ig.ice == ["قیمت؟"]

        with db.connect() as c:
            db.add_comment(c, "c9", "m", "u1", "x", "متن", None)
            crm.touch(c, "ig", "u1", "x", "comment")
        assert cl.post("/api/comments/c9/hide", json={"hide": True}).json()["hidden"] and ig.hidden[-1] == ("c9", True)
        assert cl.post("/api/comments/c9/hide", json={"hide": False}).json()["hidden"] is False
        lst = cl.get("/api/customers").json()
        assert lst["items"][0]["id"] == "ig:u1" and "VIP" in lst["tags"]
        assert cl.put("/api/customers/ig:u1", json={"phone": "09121112233"}).json()["phone"] == "09121112233"
        assert cl.get("/api/customers/ig:nope").status_code == 404
