"""کلاینت Instagram API with Instagram Login (graph.instagram.com)."""
import hashlib
import hmac

import httpx

from . import config


def verify_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[7:])


class Instagram:
    def __init__(self, token: str | None = None, user_id: str | None = None):
        self.token = token or config.IG_ACCESS_TOKEN
        self.user_id = user_id or config.IG_USER_ID
        self.base = f"https://graph.instagram.com/{config.GRAPH_VERSION}"
        self.http = httpx.AsyncClient(timeout=20)

    async def _post(self, path: str, **kw) -> dict:
        r = await self.http.post(f"{self.base}/{path}", params={"access_token": self.token}, **kw)
        data = r.json()
        if r.status_code >= 400 or "error" in data:
            raise RuntimeError(f"IG {r.status_code}: {data.get('error', data)}")
        return data

    async def _get(self, path: str, **params) -> dict:
        r = await self.http.get(f"{self.base}/{path}", params={"access_token": self.token, **params})
        data = r.json()
        if r.status_code >= 400 or "error" in data:
            raise RuntimeError(f"IG {r.status_code}: {data.get('error', data)}")
        return data

    async def reply_comment(self, comment_id: str, text: str) -> str:
        """پاسخ عمومی زیر کامنت."""
        d = await self._post(f"{comment_id}/replies", data={"message": text})
        return d["id"]

    async def private_reply(self, comment_id: str, text: str) -> str:
        """دایرکت خصوصی به کامنت‌گذار؛ تا ۷ روز بعد از کامنت مجاز است."""
        d = await self._post(
            f"{self.user_id}/messages",
            json={"recipient": {"comment_id": comment_id}, "message": {"text": text}},
        )
        return d.get("message_id", "")

    async def send_dm(self, recipient_id: str, text: str) -> str:
        """پاسخ دایرکت؛ تا ۲۴ ساعت بعد از آخرین پیام کاربر مجاز است."""
        d = await self._post(
            f"{self.user_id}/messages",
            json={"recipient": {"id": recipient_id}, "message": {"text": text}},
        )
        return d.get("message_id", "")

    async def is_follower(self, igsid: str) -> bool | None:
        try:
            d = await self._get(igsid, fields="is_user_follow_business")
            return bool(d.get("is_user_follow_business"))
        except RuntimeError:
            return None

    async def refresh_token(self) -> tuple[str, int]:
        """توکن بلندمدت ۶۰ روزه را تمدید می‌کند. (token, expires_in_seconds)"""
        d = await self._get("refresh_access_token", grant_type="ig_refresh_token")
        return d["access_token"], int(d.get("expires_in", 0))
