import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.bot import Bot
from app.config import Settings
from app.drafter import Draft
from app.instagram import parse_webhook, verify_signature
from app.main import create_app
from app.store import Store

ADMIN = 111
OWN_ID = "17841400000000000"


class FakeIG:
    def __init__(self):
        self.replies, self.dms, self.hidden = [], [], []

    async def reply_to_comment(self, comment_id, text):
        self.replies.append((comment_id, text))

    async def send_dm(self, recipient_id, text):
        self.dms.append((recipient_id, text))

    async def hide_comment(self, comment_id):
        self.hidden.append(comment_id)

    async def get_username(self, user_id):
        return "sara"

    async def get_media_caption(self, media_id):
        return "۵ اشتباه رایج در قیمت‌گذاری"

    async def refresh_token(self):
        return "new-token", 5184000


class FakeTG:
    def __init__(self):
        self.sent, self.edits, self.answers = [], [], []
        self._next = 100

    async def send_message(self, chat_id, text, buttons=None, force_reply=False):
        self._next += 1
        self.sent.append({"chat_id": chat_id, "text": text, "buttons": buttons, "id": self._next})
        return self._next

    async def edit_message(self, chat_id, message_id, text, buttons=None):
        self.edits.append({"id": message_id, "text": text, "buttons": buttons})

    async def answer_callback(self, callback_id, text=""):
        self.answers.append(text)

    async def set_webhook(self, url, secret):
        pass


class FakeDrafter:
    def __init__(self):
        self.calls = []
        self.result = Draft("question", True, "قیمت رو بر اساس ارزش بذار، نه ساعت.", "سؤال پرتکرار")

    async def draft(self, **kw):
        self.calls.append(kw)
        return self.result


def make_settings(**over):
    base = dict(ig_access_token="tok", ig_user_id=OWN_ID, ig_app_secret="appsecret", ig_verify_token="verify",
                telegram_bot_token="tg", telegram_admin_chat_id=ADMIN, telegram_webhook_secret="tgsecret",
                anthropic_api_key="sk", _env_file=None)
    base.update(over)
    return Settings(**base)


@pytest.fixture
def env():
    s = make_settings()
    bot = Bot(s, Store(":memory:"), FakeIG(), FakeTG(), FakeDrafter())
    client = TestClient(create_app(bot, background=False))
    with client:
        yield bot, client


def comment_payload(cid="c1", text="قیمت رو چطور تعیین کنم؟", from_id="999"):
    return {"object": "instagram", "entry": [{"id": OWN_ID, "time": 1, "changes": [{
        "field": "comments",
        "value": {"id": cid, "text": text, "from": {"id": from_id, "username": "ali"},
                  "media": {"id": "m1", "media_product_type": "REELS"}}}]}]}


def dm_payload(mid="mid1", text="سلام، دوره کی شروع میشه؟", sender="555", ts=None):
    return {"object": "instagram", "entry": [{"id": OWN_ID, "time": 1, "messaging": [{
        "sender": {"id": sender}, "recipient": {"id": OWN_ID},
        "timestamp": int((ts or time.time()) * 1000), "message": {"mid": mid, "text": text}}]}]}


def post_ig(client, payload, secret="appsecret"):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/instagram/webhook", content=body,
                       headers={"x-hub-signature-256": sig, "content-type": "application/json"})


def press(client, data, chat=ADMIN):
    return client.post("/telegram/webhook", headers={"x-telegram-bot-api-secret-token": "tgsecret"},
                       json={"callback_query": {"id": "cb", "data": data, "from": {"id": chat},
                                                "message": {"chat": {"id": chat}, "message_id": 1}}})


def say(client, text, chat=ADMIN):
    return client.post("/telegram/webhook", headers={"x-telegram-bot-api-secret-token": "tgsecret"},
                       json={"message": {"chat": {"id": chat}, "text": text}})


# ---------- unit ----------

def test_signature():
    body = b'{"a":1}'
    good = "sha256=" + hmac.new(b"s", body, hashlib.sha256).hexdigest()
    assert verify_signature("s", body, good)
    assert not verify_signature("s", body, "sha256=00")
    assert not verify_signature("s", body, None)


def test_parse_skips_own_comments_and_echoes():
    own = comment_payload(from_id=OWN_ID)
    echo = dm_payload()
    echo["entry"][0]["messaging"][0]["message"]["is_echo"] = True
    assert parse_webhook(own, OWN_ID) == []
    assert parse_webhook(echo, OWN_ID) == []
    [c] = parse_webhook(comment_payload(), OWN_ID)
    assert (c.kind, c.ext_id, c.username, c.media_id) == ("comment", "c1", "ali", "m1")


# ---------- webhooks ----------

def test_verify_endpoint(env):
    _, client = env
    q = {"hub.mode": "subscribe", "hub.verify_token": "verify", "hub.challenge": "42"}
    assert client.get("/instagram/webhook", params=q).text == "42"
    q["hub.verify_token"] = "wrong"
    assert client.get("/instagram/webhook", params=q).status_code == 403


def test_bad_signature_rejected(env):
    bot, client = env
    assert post_ig(client, comment_payload(), secret="nope").status_code == 401
    assert bot.tg.sent == []


def test_telegram_secret_required(env):
    _, client = env
    r = client.post("/telegram/webhook", json={"message": {"chat": {"id": ADMIN}, "text": "/start"}})
    assert r.status_code == 401


# ---------- approval flow ----------

def test_comment_draft_then_approve(env):
    bot, client = env
    assert post_ig(client, comment_payload()).status_code == 200
    [card] = bot.tg.sent
    assert card["chat_id"] == ADMIN
    assert "قیمت رو بر اساس ارزش" in card["text"] and "@ali" in card["text"]
    assert bot.drafter.calls[0]["media_caption"] == "۵ اشتباه رایج در قیمت‌گذاری"
    assert bot.ig.replies == []  # nothing is sent before approval

    press(client, "ap:1")
    assert bot.ig.replies == [("c1", "قیمت رو بر اساس ارزش بذار، نه ساعت.")]
    assert "ارسال شد" in bot.tg.edits[-1]["text"] and bot.tg.edits[-1]["buttons"] == []

    press(client, "ap:1")  # double tap does not send twice
    assert len(bot.ig.replies) == 1


def test_duplicate_webhook_ignored(env):
    bot, client = env
    post_ig(client, comment_payload())
    post_ig(client, comment_payload())
    assert len(bot.tg.sent) == 1


def test_edit_with_own_text(env):
    bot, client = env
    post_ig(client, dm_payload())
    press(client, "ed:1")
    say(client, "سلام سارا، ۱۵ آبان شروع میشه.")
    assert "۱۵ آبان" in bot.tg.sent[-1]["text"]
    press(client, "ap:1")
    assert bot.ig.dms == [("555", "سلام سارا، ۱۵ آبان شروع میشه.")]


def test_edit_with_instruction_redrafts(env):
    bot, client = env
    post_ig(client, comment_payload())
    press(client, "ed:1")
    say(client, "!کوتاه‌تر")
    assert bot.drafter.calls[-1]["instruction"] == "کوتاه‌تر"
    assert len(bot.tg.sent) == 3  # first card, edit prompt, new card


def test_skip_and_hide(env):
    bot, client = env
    post_ig(client, comment_payload("c1"))
    post_ig(client, comment_payload("c2", text="فالو کن فالوت کنم"))
    press(client, "sk:1")
    press(client, "hd:2")
    assert bot.ig.hidden == ["c2"] and bot.ig.replies == []
    assert bot.store.get_item(1).status == "skipped"
    assert bot.store.get_item(2).status == "hidden"


def test_placeholder_blocks_send(env):
    bot, client = env
    bot.drafter.result = Draft("lead", True, "قیمتش {{قیمت دوره}} هست.", "قیمت را وارد کنید")
    post_ig(client, comment_payload())
    press(client, "ap:1")
    assert bot.ig.replies == []
    assert bot.store.get_item(1).status == "failed"


def test_dm_outside_window_not_sent(env):
    bot, client = env
    post_ig(client, dm_payload(ts=time.time() - 30 * 3600))
    press(client, "ap:1")
    assert bot.ig.dms == []
    assert "۲۴" in bot.store.get_item(1).error or "24" in bot.store.get_item(1).error


def test_dm_history_passed_to_drafter(env):
    bot, client = env
    post_ig(client, dm_payload("m1", "سلام"))
    press(client, "ap:1")
    post_ig(client, dm_payload("m2", "قیمتش چنده؟"))
    history = bot.drafter.calls[-1]["history"]
    assert history == [("them", "سلام"), ("me", "قیمت رو بر اساس ارزش بذار، نه ساعت.")]


def test_strangers_cannot_approve(env):
    bot, client = env
    post_ig(client, comment_payload())
    press(client, "ap:1", chat=222)
    assert bot.ig.replies == []
    say(client, "/start", chat=222)
    assert len(bot.tg.sent) == 1  # no reply to strangers once an admin is configured


def test_token_refresh(env):
    bot, client = env
    say(client, "/token")
    assert bot.store.get("ig_token") == "new-token"
    assert "تمدید شد" in bot.tg.sent[-1]["text"]


# ---------- without Claude ----------

@pytest.fixture
def manual():
    bot = Bot(make_settings(anthropic_api_key=""), Store(":memory:"), FakeIG(), FakeTG(), None)
    with TestClient(create_app(bot, background=False)) as client:
        yield bot, client


def test_manual_mode_card_has_no_draft(manual):
    bot, client = manual
    post_ig(client, comment_payload())
    card = bot.tg.sent[0]
    labels = [b["text"] for row in card["buttons"] for b in row]
    assert "✏️ خودم می‌نویسم" in labels and "⚡ جواب آماده" in labels
    assert "🔄 دوباره بنویس" not in labels and "✅ ارسال" not in labels
    press(client, "ed:1")
    say(client, "!این متن خود منه")
    press(client, "ap:1")
    assert bot.ig.replies == [("c1", "!این متن خود منه")]


def test_quick_replies(manual):
    bot, client = manual
    say(client, "/qradd قیمت | سلام {name}، قیمت‌ها توی هایلایت هست.")
    say(client, "/qr")
    assert "قیمت" in bot.tg.sent[-1]["text"]
    post_ig(client, comment_payload())
    press(client, "qr:1")
    assert bot.tg.sent[-1]["buttons"][0][0]["callback_data"] == "qp:1:1"
    press(client, "qp:1:1")
    assert "سلام ali، قیمت‌ها" in bot.tg.sent[-1]["text"]
    press(client, "ap:1")
    assert bot.ig.replies == [("c1", "سلام ali، قیمت‌ها توی هایلایت هست.")]
    say(client, "/qrdel 1")
    assert bot.store.quick_replies() == []


def test_empty_app_secret_rejects_everything():
    assert not verify_signature("", b"{}", "sha256=" + hmac.new(b"", b"{}", hashlib.sha256).hexdigest())


def test_ig_check_command(env):
    bot, client = env

    async def me():
        return {"user_id": OWN_ID, "username": "stockland", "account_type": "BUSINESS",
                "followers_count": 1200, "media_count": 85}
    bot.ig.me = me
    say(client, "/ig")
    assert "@stockland" in bot.tg.sent[-1]["text"] and "یکیه" in bot.tg.sent[-1]["text"]
