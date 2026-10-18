import asyncio
import hmac
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from .bot import Bot
from .config import Settings
from .drafter import Drafter
from .instagram import InstagramClient, verify_signature
from .store import Store
from .telegram import TelegramClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")
# httpx logs full request URLs, and the Telegram Bot API puts the bot token in the URL.
logging.getLogger("httpx").setLevel(logging.WARNING)


def build_bot(settings: Settings) -> Bot:
    store = Store(settings.data_dir / "bot.db")
    # local_address 0.0.0.0 makes every outbound connection use IPv4.
    transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=2) if settings.force_ipv4 else None
    http = httpx.AsyncClient(timeout=20, transport=transport)
    # A refreshed token is kept in the database and wins over the one in the environment.
    ig = InstagramClient(token_getter=lambda: store.get("ig_token") or settings.ig_access_token,
                         user_id=settings.ig_user_id, api_version=settings.ig_api_version,
                         base_url=settings.ig_graph_url, http=http)
    tg = TelegramClient(settings.telegram_bot_token, http=http)
    drafter = (Drafter(settings.anthropic_api_key, settings.claude_model, settings.voice)
               if settings.anthropic_api_key else None)
    return Bot(settings, store, ig, tg, drafter)


async def _register_webhook(bot: Bot) -> None:
    if not bot.s.public_url:
        log.warning("PUBLIC_URL is not set; Telegram webhook not registered")
        return
    for attempt in range(5):
        try:
            await bot.tg.set_webhook(f"{bot.s.public_url.rstrip('/')}/telegram/webhook",
                                     bot.s.telegram_webhook_secret)
            log.info("Telegram webhook registered")
            return
        except Exception as e:
            log.warning("could not register Telegram webhook (attempt %d): %r", attempt + 1, e)
            await asyncio.sleep(10 * (attempt + 1))


async def _token_loop(bot: Bot) -> None:
    while True:
        msg = await bot.refresh_ig_token()
        if msg.startswith("⚠️") and bot.admin:
            try:
                await bot.tg.send_message(bot.admin, msg)
            except Exception:
                log.exception("could not notify admin")
        await asyncio.sleep(12 * 3600)


def create_app(bot: Bot | None = None, *, background: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.bot is None:
            app.state.bot = build_bot(Settings())
        b: Bot = app.state.bot
        tasks = []
        if background:
            # Don't block startup on network calls.
            tasks = [asyncio.create_task(_register_webhook(b)), asyncio.create_task(_token_loop(b))]
        yield
        for t in tasks:
            t.cancel()

    app = FastAPI(title="Instagram reply bot", lifespan=lifespan)
    app.state.bot = bot

    @app.get("/")
    async def health():
        return {"ok": True}

    @app.get("/instagram/webhook")
    async def ig_verify(request: Request,
                        mode: str = Query("", alias="hub.mode"),
                        token: str = Query("", alias="hub.verify_token"),
                        challenge: str = Query("", alias="hub.challenge")):
        b: Bot = request.app.state.bot
        if mode == "subscribe" and hmac.compare_digest(token, b.s.ig_verify_token):
            return PlainTextResponse(challenge)
        raise HTTPException(403)

    @app.post("/instagram/webhook")
    async def ig_webhook(request: Request, tasks: BackgroundTasks):
        b: Bot = request.app.state.bot
        body = await request.body()
        if not verify_signature(b.s.ig_app_secret, body, request.headers.get("x-hub-signature-256")):
            raise HTTPException(401, "bad signature")
        tasks.add_task(b.handle_instagram, await request.json())
        return {"ok": True}

    @app.post("/telegram/webhook")
    async def tg_webhook(request: Request, tasks: BackgroundTasks):
        b: Bot = request.app.state.bot
        secret = request.headers.get("x-telegram-bot-api-secret-token", "")
        if not hmac.compare_digest(secret, b.s.telegram_webhook_secret):
            raise HTTPException(401)
        tasks.add_task(b.handle_telegram, await request.json())
        return {"ok": True}

    return app


app = create_app()
