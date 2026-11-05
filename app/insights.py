"""تحلیل محتوا: آمار استوری‌ها، ریلزها و پست‌ها.

آمار هر استوری فقط تا ۲۴ ساعت (تا وقتی زنده است) از اینستاگرام گرفته می‌شود و بعد برای همیشه از دست
می‌رود؛ برای همین هر چند ساعت از استوری‌های زنده عکس فوری گرفته و آخرین عددها نگه داشته می‌شود.

منبع داده (فقط خواندن؛ هیچ انتشار یا پاسخی از این ماژول نمی‌رود):
  ۱. اپ Meta خود پروژه، اگر IG_ACCESS_TOKEN تنظیم شده باشد؛
  ۲. وگرنه Composio (پل موقت)، اگر COMPOSIO_API_KEY تنظیم شده باشد (کلید فقط در ‎.env‎):
     کلید حساب کاربری ‎ck_…‎ (dashboard.composio.dev) از راه سرور MCP همان حساب، یا کلید پروژه‌ی ‎ak_…‎ از راه API توسعه‌دهنده.
"""
import json
import os
import statistics
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from . import config

TEHRAN = ZoneInfo("Asia/Tehran")
STORY_METRICS = ["views", "reach", "replies", "shares", "follows", "profile_visits", "navigation", "total_interactions"]
REEL_METRICS = ["views", "reach", "saved", "shares", "likes", "comments", "total_interactions",
                "ig_reels_avg_watch_time", "reels_skip_rate"]
POST_METRICS = ["views", "reach", "saved", "shares", "likes", "comments", "total_interactions"]
NAV_KEYS = ("tap_forward", "tap_back", "tap_exit", "swipe_forward")

SCHEMA = """
CREATE TABLE IF NOT EXISTS story_stats (
  story_id TEXT PRIMARY KEY,
  posted_at REAL NOT NULL,
  media_type TEXT NOT NULL DEFAULT '',
  permalink TEXT NOT NULL DEFAULT '',
  metrics TEXT NOT NULL DEFAULT '{}',
  nav TEXT NOT NULL DEFAULT '{}',
  captured_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS media_stats (
  media_id TEXT PRIMARY KEY,
  posted_at REAL NOT NULL,
  kind TEXT NOT NULL DEFAULT '',
  caption TEXT NOT NULL DEFAULT '',
  permalink TEXT NOT NULL DEFAULT '',
  metrics TEXT NOT NULL DEFAULT '{}',
  captured_at REAL NOT NULL
);
"""


def ensure(c) -> None:
    c.executescript(SCHEMA)


def _env(name: str) -> str:
    return (getattr(config, name, "") or os.environ.get(name, "") or "").strip()


def _ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("+0000", "+00:00")).timestamp()


def parse_metrics(payload) -> dict:
    """پاسخ insights (هم Graph و هم Composio) ← {نام: عدد}."""
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(rows, dict):                       # Composio: {"data": {"data": [...]}}
        rows = rows.get("data")
    out = {}
    for x in rows or []:
        if x.get("values"):
            v = x["values"][0].get("value")
        else:
            v = (x.get("total_value") or {}).get("value")
        if isinstance(v, (int, float)):
            out[x.get("name")] = v
    return out


def parse_breakdown(payload) -> dict:
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(rows, dict):
        rows = rows.get("data")
    out = {}
    for x in rows or []:
        for b in (x.get("total_value") or {}).get("breakdowns") or []:
            for r in b.get("results") or []:
                key = (r.get("dimension_values") or [""])[0]
                if isinstance(r.get("value"), (int, float)):
                    out[key] = r["value"]
    return out


def _list(payload) -> list:
    d = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(d, dict):
        d = d.get("data")
    return d or []


class GraphSource:
    """اپ Meta خود پروژه (graph.instagram.com)."""
    name = "اپ Meta"

    def __init__(self, ig):
        self.ig = ig

    async def stories(self) -> list[dict]:
        return _list(await self.ig._get(f"{self.ig.user_id}/stories", fields="id,media_type,permalink,timestamp"))

    async def media(self, since: float) -> list[dict]:
        return _list(await self.ig._get(f"{self.ig.user_id}/media", since=int(since), limit=100,
                                        fields="id,caption,media_type,media_product_type,permalink,timestamp"))

    async def insights(self, media_id: str, metrics: list[str], breakdown: str = "") -> dict:
        kw = {"metric": ",".join(metrics)}
        if breakdown:
            kw["breakdown"] = breakdown
        return await self.ig._get(f"{media_id}/insights", **kw)


class ComposioSource:
    """پل موقت Composio؛ همان ابزارهای خواندنی که در نشست هم به کار رفت."""
    name = "Composio (API پروژه)"
    URL = "https://backend.composio.dev/api/v3/tools/execute/"

    def __init__(self, transport=None):
        self.http = httpx.AsyncClient(timeout=30, transport=transport)

    async def _run(self, slug: str, arguments: dict):
        body = {"arguments": arguments, "version": _env("COMPOSIO_TOOLKIT_VERSION") or "latest"}
        if _env("COMPOSIO_ACCOUNT_ID"):
            body["connected_account_id"] = _env("COMPOSIO_ACCOUNT_ID")
        if _env("COMPOSIO_USER_ID"):
            body["user_id"] = _env("COMPOSIO_USER_ID")
        r = await self.http.post(self.URL + slug, json=body, headers={"x-api-key": _env("COMPOSIO_API_KEY")})
        try:
            d = r.json()
        except ValueError:
            d = {}
        if r.status_code >= 400 or d.get("successful") is False or d.get("error"):
            err = d.get("error") or d.get("message") or r.text[:200]
            raise RuntimeError(f"Composio {r.status_code}: {str(err)[:200]}")
        return d.get("data", d)

    async def stories(self) -> list[dict]:
        return _list(await self._run("INSTAGRAM_GET_IG_USER_STORIES", {"fields": "id,media_type,permalink,timestamp"}))

    async def media(self, since: float) -> list[dict]:
        return _list(await self._run("INSTAGRAM_GET_IG_USER_MEDIA", {
            "ig_user_id": "me", "limit": 100, "since": int(since),
            "fields": "id,caption,media_type,media_product_type,permalink,timestamp"}))

    async def insights(self, media_id: str, metrics: list[str], breakdown: str = "") -> dict:
        a = {"ig_media_id": media_id, "metric": metrics}
        if breakdown:
            a["breakdown"] = breakdown
        return await self._run("INSTAGRAM_GET_IG_MEDIA_INSIGHTS", a)


class ComposioConnectSource(ComposioSource):
    """کلید حساب کاربری Composio (‎ck_…‎ از dashboard.composio.dev): از راه سرور MCP همان حساب
    (connect.composio.dev) و ابزار COMPOSIO_MULTI_EXECUTE_TOOL؛ اتصال اینستاگرامِ پیش‌فرض همان حساب به کار می‌رود."""
    name = "Composio"
    URL = "https://connect.composio.dev/mcp"

    def __init__(self, transport=None):
        super().__init__(transport)
        self.session = ""
        self._id = 0

    def _headers(self) -> dict:
        h = {"x-consumer-api-key": _env("COMPOSIO_API_KEY"), "Accept": "application/json, text/event-stream",
             "Content-Type": "application/json"}
        if self.session:
            h["Mcp-Session-Id"] = self.session
        return h

    @staticmethod
    def _body(r: httpx.Response) -> dict:
        """پاسخ MCP یا JSON است یا رویدادهای SSE (‎data: {...}‎)."""
        if "text/event-stream" in r.headers.get("content-type", ""):
            msg = {}
            for ln in r.text.splitlines():
                if ln.startswith("data:"):
                    try:
                        msg = json.loads(ln[5:].strip())
                    except ValueError:
                        continue
            return msg
        try:
            return r.json()
        except ValueError:
            return {}

    async def _rpc(self, method: str, params: dict, notify: bool = False) -> dict:
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notify:
            self._id += 1
            payload["id"] = self._id
        r = await self.http.post(self.URL, json=payload, headers=self._headers())
        if r.headers.get("mcp-session-id"):
            self.session = r.headers["mcp-session-id"]
        if r.status_code >= 400:
            raise RuntimeError(f"Composio {r.status_code}: {r.text[:200]}")
        if notify:
            return {}
        d = self._body(r)
        if d.get("error"):
            raise RuntimeError(f"Composio: {str(d['error'])[:200]}")
        return d.get("result") or {}

    async def _start(self) -> None:
        if self.session:
            return
        await self._rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                       "clientInfo": {"name": "igbot-insights", "version": "1"}})
        await self._rpc("notifications/initialized", {}, notify=True)

    @staticmethod
    def _unwrap(result: dict, slug: str):
        """content[0].text (JSON) ← خروجی همان ابزار، هر جا که در پاسخ چندابزاری باشد."""
        text = "".join(x.get("text", "") for x in result.get("content") or [] if x.get("type") == "text")
        try:
            d = json.loads(text) if text else (result.get("structuredContent") or {})
        except ValueError:
            raise RuntimeError(f"Composio: پاسخ نامفهوم ({text[:120]})")
        if d.get("successful") is False or d.get("error"):
            raise RuntimeError(f"Composio: {str(d.get('error'))[:200]}")
        data = d.get("data", d)
        for item in (data.get("results") or []) if isinstance(data, dict) else []:
            resp = item.get("response", item)
            if resp.get("successful") is False or resp.get("error"):
                raise RuntimeError(f"Composio {slug}: {str(resp.get('error'))[:200]}")
            return resp.get("data", resp)
        return data

    async def _run(self, slug: str, arguments: dict):
        await self._start()
        try:
            res = await self._rpc("tools/call", {"name": "COMPOSIO_MULTI_EXECUTE_TOOL", "arguments": {
                "tools": [{"tool_slug": slug, "arguments": arguments}], "sync_response_to_workbench": False,
                "thought": "read Instagram insights for the content report"}})
        except RuntimeError as e:
            if "404" in str(e) and self.session:            # نشست MCP منقضی شد: یک بار از نو
                self.session = ""
                await self._start()
                res = await self._rpc("tools/call", {"name": "COMPOSIO_MULTI_EXECUTE_TOOL", "arguments": {
                    "tools": [{"tool_slug": slug, "arguments": arguments}], "sync_response_to_workbench": False}})
            else:
                raise
        if res.get("isError"):
            raise RuntimeError(f"Composio: {self._unwrap_text(res)[:200]}")
        return self._unwrap(res, slug)

    @staticmethod
    def _unwrap_text(res: dict) -> str:
        return "".join(x.get("text", "") for x in res.get("content") or [])


def source(ig=None):
    if _env("IG_ACCESS_TOKEN") and ig is not None:
        return GraphSource(ig)
    key = _env("COMPOSIO_API_KEY")
    if key.startswith("ck_"):
        return ComposioConnectSource()
    if key:
        return ComposioSource()
    return None


async def collect_stories(c, src) -> int:
    """عکس فوری از همه‌ی استوری‌های زنده؛ آخرین عکس جای قبلی را می‌گیرد."""
    ensure(c)
    n = 0
    for s in await src.stories():
        m = parse_metrics(await src.insights(s["id"], STORY_METRICS))
        try:
            nav = parse_breakdown(await src.insights(s["id"], ["navigation"], "story_navigation_action_type"))
        except Exception:  # noqa: BLE001  (شکست ریزجزئیات نباید عکس اصلی را خراب کند)
            nav = {}
        c.execute("""INSERT INTO story_stats(story_id, posted_at, media_type, permalink, metrics, nav, captured_at)
                     VALUES(?,?,?,?,?,?,?) ON CONFLICT(story_id) DO UPDATE SET
                     metrics=excluded.metrics, nav=excluded.nav, captured_at=excluded.captured_at""",
                  (s["id"], _ts(s["timestamp"]), s.get("media_type", ""), s.get("permalink", ""),
                   json.dumps(m), json.dumps(nav), time.time()))
        n += 1
    return n


async def collect_media(c, src, days: int = 45) -> int:
    ensure(c)
    n = 0
    for m in await src.media(time.time() - days * 86400):
        kind = "REEL" if m.get("media_product_type") == "REELS" else (m.get("media_type") or "")
        try:
            met = parse_metrics(await src.insights(m["id"], REEL_METRICS if kind == "REEL" else POST_METRICS))
        except Exception:  # noqa: BLE001
            continue
        cap = (m.get("caption") or "").strip().split("\n")[0][:120]
        c.execute("""INSERT INTO media_stats(media_id, posted_at, kind, caption, permalink, metrics, captured_at)
                     VALUES(?,?,?,?,?,?,?) ON CONFLICT(media_id) DO UPDATE SET
                     caption=excluded.caption, metrics=excluded.metrics, captured_at=excluded.captured_at""",
                  (m["id"], _ts(m["timestamp"]), kind, cap, m.get("permalink", ""), json.dumps(met), time.time()))
        n += 1
    return n


def _rate(part, whole, per=1000):
    return round(per * part / whole, 1) if whole else 0


def _median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def summary(c, days: int = 14) -> dict:
    ensure(c)
    since = time.time() - days * 86400
    stories = []
    for r in c.execute("SELECT * FROM story_stats WHERE posted_at>=? ORDER BY posted_at DESC", (since,)):
        m, nav = json.loads(r["metrics"]), json.loads(r["nav"])
        views = m.get("views") or 0
        t = datetime.fromtimestamp(r["posted_at"], TEHRAN)
        stories.append({
            "id": r["story_id"], "posted_at": r["posted_at"], "day": t.strftime("%Y-%m-%d"), "hour": t.hour,
            "type": r["media_type"], "permalink": r["permalink"], "captured_at": r["captured_at"],
            "final": r["captured_at"] - r["posted_at"] >= 20 * 3600,
            **{k: m.get(k, 0) for k in STORY_METRICS},
            **{k: nav.get(k, 0) for k in NAV_KEYS},
            "exit_pct": _rate(nav.get("tap_exit", 0), views, 100),
            "skip_pct": _rate(nav.get("tap_forward", 0) + nav.get("swipe_forward", 0), views, 100),
        })
    by_day = {}
    for s in sorted(stories, key=lambda x: x["posted_at"]):
        by_day.setdefault(s["day"], []).append(s)
    days_out = [{"day": d, "count": len(v), "views": sum(x["views"] for x in v), "replies": sum(x["replies"] for x in v),
                 "first_reach": v[0]["reach"], "last_reach": v[-1]["reach"],
                 "keep_pct": _rate(v[-1]["reach"], v[0]["reach"], 100) if len(v) > 1 else None}
                for d, v in sorted(by_day.items(), reverse=True)]
    hours = {}
    for s in stories:
        if s["final"]:
            hours.setdefault(s["hour"], []).append(s["reach"])
    st_tot = {k: sum(s[k] for s in stories) for k in ("views", "reach", "replies", "shares", "profile_visits", "follows")}

    media = []
    for r in c.execute("SELECT * FROM media_stats WHERE posted_at>=? ORDER BY posted_at DESC", (since,)):
        m = json.loads(r["metrics"])
        media.append({"id": r["media_id"], "posted_at": r["posted_at"], "kind": r["kind"], "caption": r["caption"],
                      "permalink": r["permalink"], **m,
                      "hour": datetime.fromtimestamp(r["posted_at"], TEHRAN).hour,
                      "value_per_1k": _rate((m.get("saved") or 0) + (m.get("shares") or 0), m.get("reach") or 0)})
    kinds = {}
    for k in sorted({x["kind"] for x in media}):
        g = [x for x in media if x["kind"] == k]
        reach = sum(x.get("reach") or 0 for x in g)
        kinds[k] = {"count": len(g), "median_reach": _median([x.get("reach") for x in g]),
                    "saves_per_1k": _rate(sum(x.get("saved") or 0 for x in g), reach),
                    "shares_per_1k": _rate(sum(x.get("shares") or 0 for x in g), reach),
                    "median_skip": _median([x.get("reels_skip_rate") for x in g]),
                    "median_watch_s": (lambda v: round(v / 1000, 1) if v else None)(
                        _median([x.get("ig_reels_avg_watch_time") for x in g]))}
    top = sorted(media, key=lambda x: -(x.get("reach") or 0))[:5]
    valuable = sorted([x for x in media if (x.get("reach") or 0) >= 1000], key=lambda x: -x["value_per_1k"])[:5]
    last = c.execute("SELECT MAX(captured_at) FROM story_stats").fetchone()[0]
    return {
        "days": days,
        "stories": stories,
        "story_days": days_out,
        "story_totals": st_tot,
        "story_hours": {h: {"count": len(v), "median_reach": _median(v)} for h, v in sorted(hours.items())},
        "story_avg": {"views": round(st_tot["views"] / len(stories)) if stories else 0,
                      "exit_pct": _median([s["exit_pct"] for s in stories]),
                      "skip_pct": _median([s["skip_pct"] for s in stories]),
                      "replies_per_1k": _rate(st_tot["replies"], st_tot["views"])},
        "media": media[:60],
        "kinds": kinds,
        "top": top,
        "valuable": valuable,
        "last_capture": last,
    }


async def run(c, ig=None, what: str = "stories") -> dict:
    src = source(ig)
    if src is None:
        raise RuntimeError("منبع آمار تنظیم نیست: توکن اپ Meta یا کلید Composio را در «مغز مرکزی ← کلید سرویس‌ها» ثبت کنید")
    n = await (collect_stories(c, src) if what == "stories" else collect_media(c, src))
    return {"source": src.name, "count": n}
