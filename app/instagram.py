"""Instagram API with Instagram Login: webhook parsing and the few Graph calls the bot needs."""

import hashlib
import hmac
from dataclasses import dataclass

import httpx


def verify_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    """Check Meta's X-Hub-Signature-256 header (sha256=<hex hmac of the raw body>)."""
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


@dataclass
class Event:
    kind: str           # 'comment' | 'dm'
    ext_id: str         # comment id / message mid
    sender_id: str
    username: str
    text: str
    media_id: str = ""
    timestamp: float | None = None


def parse_webhook(payload: dict, own_id: str) -> list[Event]:
    """Turn a webhook payload into comment/DM events, skipping our own comments and echoes."""
    events: list[Event] = []
    if payload.get("object") != "instagram":
        return events
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "comments":
                continue
            value = change.get("value", {})
            sender = value.get("from", {})
            if not value.get("id") or sender.get("id") in (own_id, entry.get("id")):
                continue
            events.append(Event(
                kind="comment",
                ext_id=value["id"],
                sender_id=sender.get("id", ""),
                username=sender.get("username", ""),
                text=value.get("text", ""),
                media_id=value.get("media", {}).get("id", ""),
            ))
        for msg in entry.get("messaging", []):
            message = msg.get("message")
            if not message or message.get("is_echo") or message.get("is_deleted"):
                continue
            sender_id = msg.get("sender", {}).get("id", "")
            if not message.get("mid") or sender_id in (own_id, entry.get("id")):
                continue
            text = message.get("text") or ""
            if not text and message.get("attachments"):
                kinds = ", ".join(a.get("type", "?") for a in message["attachments"])
                text = f"[پیام بدون متن – پیوست: {kinds}]"
            ts = msg.get("timestamp")
            events.append(Event(
                kind="dm",
                ext_id=message["mid"],
                sender_id=sender_id,
                username="",
                text=text,
                timestamp=ts / 1000 if ts else None,
            ))
    return events


class InstagramError(Exception):
    pass


class InstagramClient:
    def __init__(self, *, token_getter, user_id: str, api_version: str, base_url: str,
                 http: httpx.AsyncClient | None = None):
        self._token = token_getter
        self.user_id = user_id
        self._base = f"{base_url.rstrip('/')}/{api_version}"
        self._root = base_url.rstrip("/")
        self._http = http or httpx.AsyncClient(timeout=20)

    async def _call(self, method: str, path: str, *, params: dict | None = None,
                    json: dict | None = None, versioned: bool = True) -> dict:
        url = f"{self._base if versioned else self._root}/{path.lstrip('/')}"
        resp = await self._http.request(method, url, params=params, json=json,
                                        headers={"Authorization": f"Bearer {self._token()}"})
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400 or "error" in data:
            err = data.get("error", {})
            raise InstagramError(err.get("message") or f"HTTP {resp.status_code}")
        return data

    async def reply_to_comment(self, comment_id: str, text: str) -> str:
        data = await self._call("POST", f"{comment_id}/replies", params={"message": text})
        return data.get("id", "")

    async def hide_comment(self, comment_id: str) -> None:
        await self._call("POST", comment_id, params={"hide": "true"})

    async def send_dm(self, recipient_id: str, text: str) -> str:
        data = await self._call("POST", f"{self.user_id}/messages",
                                json={"recipient": {"id": recipient_id}, "message": {"text": text}})
        return data.get("message_id", "")

    async def get_username(self, user_id: str) -> str:
        try:
            data = await self._call("GET", user_id, params={"fields": "username"})
            return data.get("username", "")
        except (InstagramError, httpx.HTTPError):
            return ""

    async def get_media_caption(self, media_id: str) -> str:
        try:
            data = await self._call("GET", media_id, params={"fields": "caption"})
            return data.get("caption", "")
        except (InstagramError, httpx.HTTPError):
            return ""

    async def refresh_token(self) -> tuple[str, int]:
        """Refresh the long-lived token. Returns (new_token, expires_in_seconds)."""
        data = await self._call("GET", "refresh_access_token", versioned=False,
                                params={"grant_type": "ig_refresh_token", "access_token": self._token()})
        return data["access_token"], int(data.get("expires_in", 0))
