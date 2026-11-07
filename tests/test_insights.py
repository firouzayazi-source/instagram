"""تحلیل محتوا: عکس فوری استوری، آمار پست، خلاصه، پل Composio و کلیدهای پنل (بدون شبکه‌ی واقعی)."""
import asyncio
import json
import time

import httpx
import pytest

from app import config, db, insights, secrets_env

NOW = time.time()


def iso(ts):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")


def metrics(**kw):
    return {"data": [{"name": k, "values": [{"value": v}]} for k, v in kw.items()]}


def nav(**kw):
    return {"data": [{"name": "navigation", "total_value": {"value": sum(kw.values()), "breakdowns": [
        {"dimension_keys": ["story_navigation_action_type"],
         "results": [{"dimension_values": [k], "value": v} for k, v in kw.items()]}]}}]}


class FakeSource:
    name = "آزمایشی"

    def __init__(self):
        self.stories_list = [
            {"id": "s1", "media_type": "VIDEO", "permalink": "https://x/s1", "timestamp": iso(NOW - 22 * 3600)},
            {"id": "s2", "media_type": "IMAGE", "permalink": "https://x/s2", "timestamp": iso(NOW - 21 * 3600)},
        ]
        self.calls = []

    async def stories(self):
        return self.stories_list

    async def media(self, since):
        return [{"id": "m1", "media_type": "VIDEO", "media_product_type": "REELS", "caption": "حل مشکل همراه‌بانک\nادامه",
                 "permalink": "https://x/m1", "timestamp": iso(NOW - 3 * 86400)},
                {"id": "m2", "media_type": "IMAGE", "caption": "خبر", "permalink": "https://x/m2",
                 "timestamp": iso(NOW - 2 * 86400)}]

    async def insights(self, media_id, mets, breakdown=""):
        self.calls.append((media_id, tuple(mets), breakdown))
        if breakdown:
            return nav(tap_forward=80, tap_exit=10, tap_back=5) if media_id == "s1" else nav(tap_forward=40, tap_exit=2)
        if media_id == "s1":
            return metrics(views=100, reach=90, replies=2, shares=1, follows=0, profile_visits=3, navigation=95)
        if media_id == "s2":
            return metrics(views=50, reach=45, replies=0, shares=0, follows=0, profile_visits=0, navigation=42)
        if media_id == "m1":
            return metrics(views=12000, reach=10000, saved=300, shares=200, likes=150, comments=20,
                           ig_reels_avg_watch_time=14000, reels_skip_rate=45.5)
        return metrics(views=6000, reach=5000, saved=5, shares=10, likes=80, comments=3)


def test_collect_and_summary():
    src = FakeSource()
    db.init()
    with db.connect() as c:
        assert asyncio.run(insights.collect_stories(c, src)) == 2
        assert asyncio.run(insights.collect_media(c, src)) == 2
        # عکس دوم جای اولی را می‌گیرد (تکراری ساخته نمی‌شود)
        asyncio.run(insights.collect_stories(c, src))
        assert c.execute("SELECT COUNT(*) FROM story_stats").fetchone()[0] == 2
        s = insights.summary(c, 7)
    by = {x["id"]: x for x in s["stories"]}
    assert by["s1"]["views"] == 100 and by["s1"]["tap_exit"] == 10
    assert by["s1"]["exit_pct"] == 10.0 and by["s1"]["skip_pct"] == 80.0
    assert by["s1"]["final"] is True
    assert s["story_totals"]["replies"] == 2
    day = s["story_days"][0]
    assert day["count"] == 2 and day["first_reach"] == 90 and day["last_reach"] == 45 and day["keep_pct"] == 50.0
    assert s["kinds"]["REEL"]["saves_per_1k"] == 30.0 and s["kinds"]["REEL"]["median_watch_s"] == 14.0
    assert s["kinds"]["IMAGE"]["median_skip"] is None
    assert s["top"][0]["id"] == "m1" and s["valuable"][0]["value_per_1k"] == 50.0
    assert s["media"][1]["caption"] == "حل مشکل همراه‌بانک"          # فقط خط اول کپشن
    # ریلز با معیارهای ریلز، عکس بدون معیارهای مخصوص ریلز
    assert any(m == "m1" and "reels_skip_rate" in mets for m, mets, _ in src.calls)
    assert not any(m == "m2" and "reels_skip_rate" in mets for m, mets, _ in src.calls)


def test_nav_failure_keeps_main_snapshot():
    src = FakeSource()

    async def bad(media_id, mets, breakdown=""):
        if breakdown:
            raise RuntimeError("no breakdown")
        return metrics(views=10, reach=9)
    src.insights = bad
    db.init()
    with db.connect() as c:
        assert asyncio.run(insights.collect_stories(c, src)) == 2
        assert insights.summary(c, 7)["stories"][0]["views"] == 10


def test_parse_composio_shape():
    wrapped = {"data": metrics(views=7, reach=5)}
    assert insights.parse_metrics(wrapped) == {"views": 7, "reach": 5}
    assert insights.parse_breakdown({"data": nav(tap_exit=3)}) == {"tap_exit": 3}


def test_composio_request(monkeypatch):
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["key"] = req.headers.get("x-api-key")
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"successful": True, "error": None,
                                         "data": {"data": [{"id": "s9", "timestamp": iso(NOW)}]}})
    monkeypatch.setenv("COMPOSIO_API_KEY", "ck-test-123456")
    monkeypatch.setenv("COMPOSIO_ACCOUNT_ID", "ca_abc")
    src = insights.ComposioSource(transport=httpx.MockTransport(handler))
    out = asyncio.run(src.stories())
    assert out[0]["id"] == "s9"
    assert seen["url"].endswith("/api/v3/tools/execute/INSTAGRAM_GET_IG_USER_STORIES")
    assert seen["key"] == "ck-test-123456"
    assert seen["body"]["connected_account_id"] == "ca_abc" and "fields" in seen["body"]["arguments"]


def test_composio_error_is_raised(monkeypatch):
    monkeypatch.setenv("COMPOSIO_API_KEY", "ck-test-123456")
    src = insights.ComposioSource(transport=httpx.MockTransport(
        lambda r: httpx.Response(401, json={"error": {"message": "bad key"}})))
    with pytest.raises(RuntimeError, match="Composio 401"):
        asyncio.run(src.stories())


def test_source_selection(monkeypatch):
    monkeypatch.setattr(config, "IG_ACCESS_TOKEN", "")
    monkeypatch.delenv("IG_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("COMPOSIO_API_KEY", raising=False)
    assert insights.source(object()) is None
    monkeypatch.setenv("COMPOSIO_API_KEY", "ck-test-123456")
    assert isinstance(insights.source(object()), insights.ComposioSource)
    monkeypatch.setattr(config, "IG_ACCESS_TOKEN", "tok")
    assert isinstance(insights.source(object()), insights.GraphSource)     # اپ Meta خود پروژه مقدم است


def test_run_without_source_explains(monkeypatch):
    monkeypatch.setattr(config, "IG_ACCESS_TOKEN", "")
    monkeypatch.delenv("COMPOSIO_API_KEY", raising=False)
    db.init()
    with db.connect() as c, pytest.raises(RuntimeError, match="منبع آمار تنظیم نیست"):
        asyncio.run(insights.run(c, None))


def test_composio_keys_allowed_and_validated(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("IG_ACCESS_TOKEN=keep\n", encoding="utf-8")
    monkeypatch.setenv("IGBOT_ENV_FILE", str(env))
    names = secrets_env.allowed()
    assert {"COMPOSIO_API_KEY", "COMPOSIO_ACCOUNT_ID", "COMPOSIO_USER_ID"} <= set(names)
    assert "IG_ACCESS_TOKEN" not in names
    secrets_env.set_value("COMPOSIO_ACCOUNT_ID", "ca_abc-123")
    with pytest.raises(ValueError):
        secrets_env.set_value("COMPOSIO_ACCOUNT_ID", "bad id with spaces")
    secrets_env.set_value("COMPOSIO_API_KEY", "ak_secretvalue99")
    st = {x["name"]: x for x in secrets_env.status()}
    assert st["COMPOSIO_API_KEY"]["secret"] and st["COMPOSIO_API_KEY"]["hint"] == "…ue99"
    assert st["COMPOSIO_ACCOUNT_ID"]["hint"] == "ca_abc-123"
    text = env.read_text(encoding="utf-8")
    assert "IG_ACCESS_TOKEN=keep" in text and "COMPOSIO_API_KEY=ak_secretvalue99" in text
    for k in ("COMPOSIO_API_KEY", "COMPOSIO_ACCOUNT_ID"):
        monkeypatch.delenv(k, raising=False)
        monkeypatch.setattr(config, k, "", raising=False)


def test_api_insights(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import auth
    from app.main import create_app
    from tests.test_instagram_features import IG
    monkeypatch.setattr(config, "PANEL_PASSWORD", "pw")
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    monkeypatch.setattr(config, "WEB_DIST", str(tmp_path / "nodist"))
    monkeypatch.setattr(config, "IG_ACCESS_TOKEN", "")
    auth._fails.clear()
    db.init()
    with db.connect() as c:
        asyncio.run(insights.collect_stories(c, FakeSource()))
    with TestClient(create_app(IG())) as cl:
        assert cl.get("/api/insights").status_code == 401
        cl.post("/api/login", json={"password": "pw"})
        d = cl.get("/api/insights?days=7").json()
        assert d["source"] == "" and len(d["stories"]) == 2 and d["story_avg"]["views"] == 75
        r = cl.post("/api/insights/collect")
        assert r.status_code == 502 and "منبع آمار تنظیم نیست" in r.json()["detail"]


def test_composio_connect_mcp(monkeypatch):
    """کلید ck_ حساب کاربری: initialize ← initialized ← tools/call با COMPOSIO_MULTI_EXECUTE_TOOL (پاسخ SSE)."""
    seen = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append((body["method"], req.headers.get("x-consumer-api-key"), req.headers.get("mcp-session-id")))
        if body["method"] == "initialize":
            return httpx.Response(200, headers={"mcp-session-id": "sess-1", "content-type": "text/event-stream"},
                                  text='event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-03-26"}}\n\n')
        if body["method"] == "notifications/initialized":
            return httpx.Response(202)
        assert body["params"]["name"] == "COMPOSIO_MULTI_EXECUTE_TOOL"
        call = body["params"]["arguments"]["tools"][0]
        assert call["tool_slug"] == "INSTAGRAM_GET_IG_MEDIA_INSIGHTS" and call["arguments"]["ig_media_id"] == "m1"
        inner = {"successful": True, "data": {"results": [{"tool_slug": call["tool_slug"], "response": {
            "successful": True, "data": metrics(views=11, reach=9)}}]}}
        msg = {"jsonrpc": "2.0", "id": body["id"], "result": {"content": [{"type": "text", "text": json.dumps(inner)}]}}
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, text="data: " + json.dumps(msg) + "\n\n")

    monkeypatch.setenv("COMPOSIO_API_KEY", "ck_test_consumer_key")
    monkeypatch.setattr(config, "IG_ACCESS_TOKEN", "")
    src = insights.source(object())
    assert isinstance(src, insights.ComposioConnectSource)
    src.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    out = asyncio.run(src.insights("m1", ["views", "reach"]))
    assert insights.parse_metrics(out) == {"views": 11, "reach": 9}
    assert [m for m, _, _ in seen] == ["initialize", "notifications/initialized", "tools/call"]
    assert all(k == "ck_test_consumer_key" for _, k, _ in seen)
    assert seen[-1][2] == "sess-1"                       # نشست MCP در درخواست‌های بعدی


def test_composio_connect_tool_error(monkeypatch):
    def handler(req):
        body = json.loads(req.content)
        if body["method"] == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})
        if body["method"] == "notifications/initialized":
            return httpx.Response(202)
        inner = {"successful": True, "data": {"results": [{"response": {"successful": False, "error": "no connection"}}]}}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"],
                                         "result": {"content": [{"type": "text", "text": json.dumps(inner)}]}})
    monkeypatch.setenv("COMPOSIO_API_KEY", "ck_test_consumer_key")
    src = insights.ComposioConnectSource(transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError, match="no connection"):
        asyncio.run(src.stories())


def test_media_parallel_and_all_failed():
    """آمار پست‌ها هم‌زمان (حداکثر MEDIA_PARALLEL) گرفته می‌شود؛ اگر هیچ‌کدام نیامد خطا دیده شود، نه «۰ پست» بی‌صدا."""
    src, live, peak = FakeSource(), [0], [0]
    orig = src.insights

    async def slow(media_id, mets, breakdown=""):
        live[0] += 1
        peak[0] = max(peak[0], live[0])
        await asyncio.sleep(0.01)
        live[0] -= 1
        return await orig(media_id, mets, breakdown)
    src.insights = slow
    db.init()
    with db.connect() as c:
        assert asyncio.run(insights.collect_media(c, src)) == 2
    assert peak[0] == 2

    async def bad(media_id, mets, breakdown=""):
        raise RuntimeError("rate limit")
    src.insights = bad
    with db.connect() as c, pytest.raises(RuntimeError, match="هیچ‌کدام از ۲|هیچ‌کدام از 2"):
        asyncio.run(insights.collect_media(c, src))


def test_api_collect_media_in_background(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import auth
    from app.main import create_app
    from tests.test_instagram_features import IG
    monkeypatch.setattr(config, "PANEL_PASSWORD", "pw")
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    monkeypatch.setattr(config, "WEB_DIST", str(tmp_path / "nodist"))
    monkeypatch.setattr(insights, "source", lambda ig=None: FakeSource())
    auth._fails.clear()
    db.init()
    with TestClient(create_app(IG())) as cl:
        cl.post("/api/login", json={"password": "pw"})
        r = cl.post("/api/insights/collect").json()
        assert r["stories"]["count"] == 2 and r["media"] == {"running": True}
        for _ in range(50):
            st = cl.get("/api/insights?days=7").json()
            if st["status"]["media"]:
                break
            time.sleep(0.05)
        assert st["status"]["media"]["ok"] and st["status"]["media"]["count"] == 2 and "REEL" in st["kinds"]
