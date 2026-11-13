"""فرم‌ساز دایرکت و منوی ثابت: سؤال‌ها به ترتیب، اعتبارسنجی، ذخیره، و کار حتی با جواب خودکار خاموش."""
import json

import pytest

from app import comment_poll, config, db, dm_menu, forms, tg_notify, worker

T0 = 1_800_000_000.0
FORM = {"name": "مشاوره خرید", "done_text": "ثبت شد 🌸", "questions": [
    {"label": "اسمتون؟", "kind": "text"},
    {"label": "شماره‌تون؟", "kind": "phone"},
    {"label": "نقد یا قسط؟", "kind": "choice", "options": ["نقد", "قسط"]}]}


@pytest.fixture
def wenv(monkeypatch):
    from tests.test_instagram_features import IG
    monkeypatch.setattr(config, "SEND_DELAY_MIN", 0)
    monkeypatch.setattr(config, "SEND_DELAY_MAX", 0)
    sent = []
    monkeypatch.setattr(tg_notify, "send", lambda text, *a, **k: sent.append(text) or True)
    db.init()
    ig = IG()
    ig.tg = sent
    return ig


def test_save_validates():
    db.init()
    with db.connect() as c:
        with pytest.raises(ValueError):
            forms.save(c, {"name": "", "questions": FORM["questions"]})
        with pytest.raises(ValueError):
            forms.save(c, {"name": "x", "questions": [{"label": "؟", "kind": "choice", "options": ["تنها"]}]})
        fid = forms.save(c, FORM)
        assert forms.get(c, fid)["questions"][2]["options"] == ["نقد", "قسط"]


def test_flow_validation_and_entry():
    db.init()
    with db.connect() as c:
        fid = forms.save(c, FORM)
        assert forms.start(c, fid, "u1", now=T0) == ("اسمتون؟", None)
        assert forms.answer(c, "u1", "ali", "علی", now=T0 + 1)["text"] == "شماره‌تون؟"
        bad = forms.answer(c, "u1", "ali", "۱۲۳", now=T0 + 2)
        assert "درست نیست" in bad["text"] and bad["done"] is None
        r = forms.answer(c, "u1", "ali", "۰۹۱۲ ۱۲۳ ۴۵۶۷", now=T0 + 3)
        assert r["quick_replies"] == ["نقد", "قسط"]
        assert "دکمه" in forms.answer(c, "u1", "ali", "شاید", now=T0 + 4)["text"]
        done = forms.answer(c, "u1", "ali", "قسط", now=T0 + 5)
        assert done["text"] == "ثبت شد 🌸" and done["phone"] == "09121234567" and done["done"]
        assert forms.answer(c, "u1", "ali", "سلام", now=T0 + 6) is None          # فرم تمام شده
        e = forms.entries(c, fid)[0]
        assert [a["value"] for a in e["answers"]] == ["علی", "09121234567", "قسط"]


def test_cancel_and_expiry():
    db.init()
    with db.connect() as c:
        fid = forms.save(c, FORM)
        forms.start(c, fid, "u1", now=T0)
        assert "بسته شد" in forms.answer(c, "u1", "", "لغو", now=T0 + 1)["text"]
        assert not forms.active(c, "u1", now=T0 + 2)
        forms.start(c, fid, "u2", now=T0)
        assert forms.answer(c, "u2", "", "علی", now=T0 + forms.SESSION_TTL + 1) is None
        assert forms.entries(c, fid) == []


def _dm(mid, text, uid="u1"):
    return {"sender": {"id": uid, "username": "ali"}, "timestamp": int(T0 * 1000),
            "message": {"mid": mid, "text": text}, "_via": "poll"}


async def _run(ig, c, eid, kind, payload):
    db.add_event(c, eid, kind, payload)
    row = [r for r in db.pending_events(c) if r["id"] == eid][0]
    return await worker.handle_event(ig, row, c)


@pytest.mark.asyncio
async def test_comment_rule_starts_form_and_dm_answers_continue_with_auto_reply_off(wenv):
    with db.connect() as c:
        fid = forms.save(c, FORM)
        db.upsert_rule(c, {"name": "فرم", "channels": ["comment"], "triggers": [{"match": "contains", "value": "مشاوره"}],
                           "actions": {"private_replies": ["سلام! چند سؤال کوتاه:"], "form_id": fid}})
        assert not comment_poll.dm_reply_enabled(c)
        com = {"id": "c1", "text": "مشاوره", "from": {"id": "u1", "username": "ali"}, "media": {"id": "m1"}, "_via": "poll"}
        assert await _run(wenv, c, "c:c1", "comment", com) == "done"
        assert ("private", "c1", "سلام! چند سؤال کوتاه:\n\nاسمتون؟") in wenv.calls
        assert await _run(wenv, c, "m:1", "message", _dm("1", "علی")) == "done"
        assert await _run(wenv, c, "m:2", "message", _dm("2", "09121234567")) == "done"
        assert wenv.qr.get("نقد یا قسط؟") == ["نقد", "قسط"]
        assert await _run(wenv, c, "m:3", "message", _dm("3", "نقد")) == "done"
        assert c.execute("SELECT phone FROM customers WHERE id='ig:u1'").fetchone()[0] == "09121234567"
        assert len(forms.entries(c, fid)) == 1
        # بعد از فرم، دایرکت عادی دوباره فقط صندوق است (جواب خودکار خاموش)
        assert await _run(wenv, c, "m:4", "message", _dm("4", "مرسی")) == "skipped"
    assert wenv.tg and "مشاوره خرید" in wenv.tg[-1] and "0912" not in wenv.tg[-1]   # خبر بدون اطلاعات مشتری


@pytest.mark.asyncio
async def test_menu_text_button(wenv):
    with db.connect() as c:
        dm_menu.save(c, [{"title": "ساعت کاری", "type": "text", "value": "شنبه تا پنجشنبه ۱۱ تا ۱۴"},
                         {"title": "ربات", "type": "url", "value": "https://t.me/Poshtibani_stland_bot"}])
        assert await _run(wenv, c, "m:9", "message", _dm("9", "ساعت کاری")) == "done"
        pb = {"sender": {"id": "u2"}, "timestamp": int(T0 * 1000), "postback": {"mid": "p1", "title": "x", "payload": "MENU:0"}}
        assert await _run(wenv, c, "p:1", "postback", pb) == "done"
    assert [x[2] for x in wenv.calls if x[0] == "dm"] == ["شنبه تا پنجشنبه ۱۱ تا ۱۴"] * 2


def test_menu_validation():
    db.init()
    with db.connect() as c:
        with pytest.raises(ValueError):
            dm_menu.save(c, [{"title": "سایت", "type": "url", "value": "http://x"}])
        with pytest.raises(ValueError):
            dm_menu.save(c, [{"title": "", "type": "text", "value": "متن"}])
        assert dm_menu.save(c, [{"title": "", "value": ""}]) == []
        assert json.loads(db.kv_get(c, dm_menu.KEY)) == []
