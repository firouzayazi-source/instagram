"""خوانش کامنت با Composio: فقط کامنت‌های تازه در صف، بدون تکرار؛ فقط دستورها جواب می‌دهند؛ کلاینت از راه Composio می‌فرستد."""
import asyncio
import json
from datetime import datetime, timezone

import pytest

from app import comment_poll, config, db, worker
from app.instagram import Instagram

T0 = 1_800_000_000.0


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")


class PollIG:
    """جواب‌های ساختگی Graph برای poll_once."""

    def __init__(self):
        self.user_id = "me"
        self.posts = [{"id": "p1", "comments_count": 2, "timestamp": iso(T0 - 86400)}]
        self.comments = {"p1": [{"id": "old1", "text": "قیمت", "timestamp": iso(T0 - 3600), "from": {"id": "u1", "username": "a"}},
                                {"id": "old2", "text": "عالی", "timestamp": iso(T0 - 60), "from": {"id": "u2", "username": "b"}}]}
        self.gets = []

    def via_composio(self):
        return True

    async def _get(self, path, **params):
        self.gets.append(path)
        if path == "me":
            return {"username": "stock_land.ir"}
        if path == "me/media":
            return {"data": self.posts}
        if path.endswith("/comments"):
            return {"data": self.comments.get(path.split("/")[0], [])}
        return {"comments_count": len(self.comments.get(path, []))}


def events(c):
    return {r["id"]: json.loads(r["payload"]) for r in c.execute("SELECT * FROM events")}


def test_baseline_then_only_new_comments():
    ig = PollIG()
    db.init()
    with db.connect() as c:
        assert asyncio.run(comment_poll.poll_once(ig, c, now=T0)) == {"queued": 0, "checked": 0}   # کامنت‌های قدیمی جواب نمی‌گیرند
        assert not events(c) and "p1/comments" not in ig.gets
        assert asyncio.run(comment_poll.poll_once(ig, c, now=T0 + 60))["checked"] == 0              # تعداد عوض نشده: کامنتی خوانده نمی‌شود
        ig.comments["p1"].insert(0, {"id": "n1", "text": "قیمت", "timestamp": iso(T0 + 90), "from": {"id": "u3", "username": "c"}})
        ig.comments["p1"].insert(0, {"id": "own", "text": "ممنون", "timestamp": iso(T0 + 95),
                                     "from": {"id": "u0", "username": "stock_land.ir"}})
        ig.posts[0]["comments_count"] = 4
        assert asyncio.run(comment_poll.poll_once(ig, c, now=T0 + 120)) == {"queued": 1, "checked": 1}
        ev = events(c)
        assert list(ev) == ["c:n1"] and ev["c:n1"]["media"] == {"id": "p1"} and ev["c:n1"]["_via"] == "poll"
        assert asyncio.run(comment_poll.poll_once(ig, c, now=T0 + 180))["queued"] == 0              # تکراری نمی‌شود


def test_new_post_after_start_gets_all_its_comments_old_watched_post_does_not():
    ig = PollIG()
    db.init()
    with db.connect() as c:
        asyncio.run(comment_poll.poll_once(ig, c, now=T0))
        ig.posts.insert(0, {"id": "p2", "comments_count": 1, "timestamp": iso(T0 + 30)})
        ig.comments["p2"] = [{"id": "x1", "text": "قیمت", "timestamp": iso(T0 + 40), "from": {"id": "u5", "username": "d"}}]
        db.upsert_rule(c, {"name": "قدیمی", "channels": ["comment"], "post_scope": ["old9"], "triggers": [{"match": "any"}],
                           "actions": {"public_replies": ["x"]}})
        ig.comments["old9"] = [{"id": "z1", "text": "سلام", "timestamp": iso(T0 - 9999), "from": {"id": "u6", "username": "e"}}]
        assert asyncio.run(comment_poll.poll_once(ig, c, now=T0 + 60))["queued"] == 1
        assert list(events(c)) == ["c:x1"]


@pytest.fixture
def wenv(monkeypatch):
    from tests.test_webhook import FakeIG
    monkeypatch.setattr(config, "SEND_DELAY_MIN", 0)
    monkeypatch.setattr(config, "SEND_DELAY_MAX", 0)
    db.init()
    return FakeIG()


@pytest.mark.asyncio
async def test_polled_comment_answered_only_by_rules(wenv):
    with db.connect() as c:
        db.upsert_rule(c, {"name": "قیمت پست", "channels": ["comment"], "post_scope": ["p1"],
                           "triggers": [{"match": "contains", "value": "قیمت"}],
                           "actions": {"public_replies": ["دایرکت رو ببین 🙏"], "private_replies": ["لینک ربات: t.me/x"]}})
        base = {"from": {"id": "u3", "username": "c"}, "media": {"id": "p1"}, "_via": "poll"}
        db.add_event(c, "c:n1", "comment", {"id": "n1", "text": "قیمت چنده", **base})
        db.add_event(c, "c:n2", "comment", {"id": "n2", "text": "عالی بود", **base})
        r1, r2 = db.pending_events(c)
        assert await worker.handle_event(wenv, r1, c) == "done"
        assert await worker.handle_event(wenv, r2, c) == "ignored"        # بی‌دستور: هوش مصنوعی جواب عمومی نمی‌دهد
        assert c.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 2   # هر دو در صندوق
    assert wenv.calls == [("private", "n1", "لینک ربات: t.me/x"), ("public", "n1", "دایرکت رو ببین 🙏")]


def test_instagram_client_routes_through_composio(monkeypatch):
    sent = []

    class Fake:
        async def graph(self, method, url, body=None, params=None):
            sent.append((method, url, body, params))
            return (200, {"message_id": "mid1"}) if url.endswith("/messages") else (200, {"id": "r9"})
    monkeypatch.setattr(config, "IG_ACCESS_TOKEN", "")
    monkeypatch.setattr(config, "IG_USER_ID", "")
    monkeypatch.setattr(config, "COMPOSIO_API_KEY", "ck_test", raising=False)
    ig = Instagram()
    ig._composio = Fake()
    assert ig.via_composio() and ig.user_id == "me"
    assert asyncio.run(ig.private_reply("c1", "سلام")) == "mid1"
    assert asyncio.run(ig.reply_comment("c1", "ممنون")) == "r9"
    assert sent[0] == ("POST", f"https://graph.instagram.com/{config.GRAPH_VERSION}/me/messages",
                       {"recipient": {"comment_id": "c1"}, "message": {"text": "سلام"}}, None)
    assert sent[1][1].endswith("/c1/replies") and sent[1][2] == {"message": "ممنون"}

    async def bad(*a, **k):
        return 400, {"error": {"message": "outside window", "code": 10}}
    ig._composio.graph = bad
    with pytest.raises(RuntimeError, match="IG 400"):
        asyncio.run(ig.reply_comment("c1", "x"))
    monkeypatch.setattr(config, "IG_ACCESS_TOKEN", "t")
    assert not Instagram().via_composio()                                      # اپ Meta خود پروژه مقدم است


def test_composio_graph_unwraps_proxy_response(monkeypatch):
    import httpx
    from app import insights
    monkeypatch.setattr(config, "COMPOSIO_API_KEY", "ck_test", raising=False)
    calls = []

    def handler(req):
        body = json.loads(req.content)
        calls.append(body)
        if body["method"] == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {}}, headers={"mcp-session-id": "s1"})
        if body["method"] == "notifications/initialized":
            return httpx.Response(202)
        inner = {"successful": True, "data": {"data": {"id": "r1"}, "status": 200, "headers": {"x": "y"}}}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"],
                                         "result": {"content": [{"type": "text", "text": json.dumps(inner)}]}})
    src = insights.ComposioConnectSource(transport=httpx.MockTransport(handler))
    assert asyncio.run(src.graph("POST", "https://graph.instagram.com/v21.0/c1/replies", body={"message": "x"})) == (200, {"id": "r1"})
    call = calls[-1]["params"]
    assert call["name"] == "COMPOSIO_PROXY_EXECUTE" and call["arguments"]["toolkit_slug"] == "instagram"
