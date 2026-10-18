"""Minimal Telegram Bot API client used for the approval flow."""

import httpx


class TelegramClient:
    def __init__(self, token: str, http: httpx.AsyncClient | None = None):
        self._base = f"https://api.telegram.org/bot{token}"
        self._http = http or httpx.AsyncClient(timeout=20)

    async def _call(self, method: str, **params) -> dict:
        resp = await self._http.post(f"{self._base}/{method}", json=params)
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method} failed: {data.get('description')}")
        return data.get("result", {})

    async def send_message(self, chat_id: int, text: str, buttons: list[list[dict]] | None = None,
                           force_reply: bool = False) -> int:
        params: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                        "disable_web_page_preview": True}
        if buttons:
            params["reply_markup"] = {"inline_keyboard": buttons}
        elif force_reply:
            params["reply_markup"] = {"force_reply": True}
        result = await self._call("sendMessage", **params)
        return result.get("message_id", 0)

    async def edit_message(self, chat_id: int, message_id: int, text: str,
                           buttons: list[list[dict]] | None = None) -> None:
        params: dict = {"chat_id": chat_id, "message_id": message_id, "text": text,
                        "parse_mode": "HTML", "disable_web_page_preview": True,
                        "reply_markup": {"inline_keyboard": buttons or []}}
        try:
            await self._call("editMessageText", **params)
        except RuntimeError as e:
            if "message is not modified" not in str(e):
                raise

    async def answer_callback(self, callback_id: str, text: str = "") -> None:
        await self._call("answerCallbackQuery", callback_query_id=callback_id, text=text)

    async def set_webhook(self, url: str, secret: str) -> None:
        await self._call("setWebhook", url=url, secret_token=secret,
                         allowed_updates=["message", "callback_query"])
