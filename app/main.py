"""ورودی وب: وبهوک اینستاگرام و بررسی سلامت."""
import asyncio
import contextlib
import json
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse

from . import api, api_ai, comment_poll, config, db, internal, site_sync, worker
from .instagram import Instagram, verify_signature


def extract_events(body: dict) -> list[tuple[str, str, dict]]:
    """(event_id, kind, payload) از ساختار وبهوک Instagram Login."""
    out = []
    for entry in body.get("entry", []):
        for ch in entry.get("changes", []):
            if ch.get("field") == "comments":
                v = ch.get("value", {})
                if v.get("id"):
                    out.append((f"c:{v['id']}", "comment", v))
        for m in entry.get("messaging", []):
            mid = m.get("message", {}).get("mid")
            if mid:
                out.append((f"m:{mid}", "message", m))
            elif (m.get("postback") or {}).get("mid"):
                # لمس یکی از سؤال‌های آماده‌ی شروع گفتگو (Ice Breaker)
                out.append((f"p:{m['postback']['mid']}", "postback", m))
    return out


def create_app(ig: Instagram | None = None) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        db.init()
        internal.ensure_key()
        with db.connect() as c:
            saved = db.kv_get(c, "access_token")
        if saved:
            app.state.ig.token = saved
        stop = asyncio.Event()
        tasks = [
            asyncio.create_task(worker.run_forever(app.state.ig, stop)),
            asyncio.create_task(worker.refresh_token_loop(app.state.ig, stop)),
            asyncio.create_task(worker.insights_loop(app.state.ig, stop)),
            asyncio.create_task(comment_poll.poll_loop(app.state.ig, stop)),
            asyncio.create_task(site_sync.sync_loop(stop)),
        ]
        yield
        stop.set()
        for t in tasks:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t

    app = FastAPI(title="instagram-bot", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.ig = ig or Instagram()

    @app.get("/health")
    async def health():
        with db.connect() as c:
            pending = c.execute("SELECT COUNT(*) FROM events WHERE status='pending'").fetchone()[0]
        return {"ok": True, "pending": pending}

    @app.get("/webhook")
    async def verify(
        mode: str = Query("", alias="hub.mode"),
        token: str = Query("", alias="hub.verify_token"),
        challenge: str = Query("", alias="hub.challenge"),
    ):
        if mode == "subscribe" and token and token == config.IG_VERIFY_TOKEN:
            return Response(challenge, media_type="text/plain")
        raise HTTPException(403)

    @app.post("/webhook")
    async def receive(request: Request, x_hub_signature_256: str | None = Header(None)):
        body = await request.body()
        if not verify_signature(config.IG_APP_SECRET, body, x_hub_signature_256):
            raise HTTPException(403, "bad signature")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(400, "bad json")
        added = 0
        with db.connect() as c:
            for event_id, kind, payload in extract_events(data):
                added += db.add_event(c, event_id, kind, payload)
        return {"queued": added}

    app.include_router(api.router)
    app.include_router(api.protected)
    app.include_router(api_ai.router)
    app.include_router(internal.router)

    dist = Path(config.WEB_DIST)
    if dist.is_dir():
        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            """فایل‌های پنل؛ هر مسیر ناشناخته به index.html می‌رود (SPA)."""
            target = (dist / path).resolve()
            if path and target.is_file() and dist.resolve() in target.parents:
                headers = {"Cache-Control": "no-cache"} if path in ("sw.js", "index.html", "manifest.webmanifest") else {}
                return FileResponse(target, headers=headers)
            return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
