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


def _composio_key() -> str:
    import os
    return (getattr(config, "COMPOSIO_API_KEY", "") or os.environ.get("COMPOSIO_API_KEY", "") or "").strip()


class Instagram:
    """بدون توکن اپ Meta خود پروژه، اگر کلید حساب Composio (‎ck_…‎) ثبت باشد، همین درخواست‌ها از راه اتصال
    اینستاگرامِ Composio می‌روند (همان مسیرها و همان بدنه‌ها؛ آزموده‌شده: جواب کامنت و دایرکت به کامنت‌گذار)."""

    def __init__(self, token: str | None = None, user_id: str | None = None):
        self.token = token or config.IG_ACCESS_TOKEN
        self._user_id = user_id or ""
        self.base = f"https://graph.instagram.com/{config.GRAPH_VERSION}"
        self.http = httpx.AsyncClient(timeout=20)
        self._composio = None

    @property
    def user_id(self) -> str:
        return self._user_id or config.IG_USER_ID or ("me" if self.via_composio() else "")

    @user_id.setter
    def user_id(self, v: str) -> None:
        self._user_id = v

    def via_composio(self) -> bool:
        return not self.token and _composio_key().startswith("ck_")

    async def _composio_call(self, method: str, path: str, body: dict | None = None, params: dict | None = None) -> dict:
        if self._composio is None:
            from .insights import ComposioConnectSource
            self._composio = ComposioConnectSource()
        status, data = await self._composio.graph(method, f"{self.base}/{path}", body=body, params=params)
        if status >= 400 or "error" in data:
            raise RuntimeError(f"IG {status}: {data.get('error', data)}")
        return data

    async def _post(self, path: str, **kw) -> dict:
        if self.via_composio():
            return await self._composio_call("POST", path, body=kw.get("json") or kw.get("data") or {})
        r = await self.http.post(f"{self.base}/{path}", params={"access_token": self.token}, **kw)
        data = r.json()
        if r.status_code >= 400 or "error" in data:
            raise RuntimeError(f"IG {r.status_code}: {data.get('error', data)}")
        return data

    async def _get(self, path: str, **params) -> dict:
        if self.via_composio():
            return await self._composio_call("GET", path, params=params)
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

    async def send_dm(self, recipient_id: str, text: str, quick_replies: list[str] | None = None) -> str:
        """پاسخ دایرکت؛ تا ۲۴ ساعت بعد از آخرین پیام کاربر مجاز است.
        quick_replies: دکمه‌های پاسخ سریع زیر پیام (حداکثر ۱۳، هر کدام تا ۲۰ نویسه)؛ لمسش همان متن را می‌فرستد."""
        message = {"text": text}
        if quick_replies:
            message["quick_replies"] = [{"content_type": "text", "title": t[:20], "payload": t[:20]}
                                        for t in quick_replies[:13]]
        d = await self._post(f"{self.user_id}/messages", json={"recipient": {"id": recipient_id}, "message": message})
        return d.get("message_id", "")

    async def send_cards(self, recipient_id: str, cards: list[dict]) -> str:
        """کارت‌های ویترین (generic template): عکس، عنوان، قیمت و دکمه‌های «مشاهده در سایت» و «سفارش».
        حداکثر ۱۰ کارت؛ لمس «سفارش» یک postback با ORDER:<شناسه> برمی‌گرداند."""
        elements = []
        for x in cards[:10]:
            buttons = []
            if x.get("url"):
                buttons.append({"type": "web_url", "url": x["url"], "title": "مشاهده در سایت"})
            if x.get("id"):
                buttons.append({"type": "postback", "title": "🛒 سفارش", "payload": f"ORDER:{x['id']}"})
            el = {"title": x["title"][:80], "subtitle": x.get("subtitle", "")[:80], "buttons": buttons[:3]}
            if x.get("image"):
                el["image_url"] = x["image"]
            elements.append(el)
        d = await self._post(f"{self.user_id}/messages", json={
            "recipient": {"id": recipient_id},
            "message": {"attachment": {"type": "template", "payload": {"template_type": "generic", "elements": elements}}}})
        return d.get("message_id", "")

    async def sender_action(self, recipient_id: str, action: str) -> None:
        """typing_on (در حال نوشتن) یا mark_seen (دیده شد)."""
        await self._post(f"{self.user_id}/messages", json={"recipient": {"id": recipient_id}, "sender_action": action})

    async def hide_comment(self, comment_id: str, hide: bool = True) -> None:
        """مخفی کردن کامنت روی پست خود پیج (فقط برای کامنت‌گذار و دوستانش دیده می‌شود؛ برگشت‌پذیر)."""
        await self._post(comment_id, data={"hide": "true" if hide else "false"})

    async def _delete_profile(self, field: str) -> None:
        if self.via_composio():
            await self._composio_call("DELETE", f"{self.user_id}/messenger_profile", body={"fields": [field]})
            return
        r = await self.http.request("DELETE", f"{self.base}/{self.user_id}/messenger_profile",
                                    params={"access_token": self.token}, json={"fields": [field]})
        if r.status_code >= 400:
            raise RuntimeError(f"IG {r.status_code}: {r.text[:300]}")

    async def set_ice_breakers(self, questions: list[str]) -> None:
        """سؤال‌های آماده‌ی شروع گفتگو (حداکثر ۴). فهرست خالی یعنی حذف."""
        if not questions:
            return await self._delete_profile("ice_breakers")
        await self._post(f"{self.user_id}/messenger_profile", json={
            "platform": "instagram",
            "ice_breakers": [{"locale": "default",
                              "call_to_actions": [{"question": q[:80], "payload": q[:80]} for q in questions[:4]]}]})

    async def set_persistent_menu(self, items: list[dict]) -> None:
        """منوی ثابت دایرکت. هر مورد: {"type": "url"|"text", "title", "value"}؛ فهرست خالی یعنی حذف."""
        if not items:
            return await self._delete_profile("persistent_menu")
        acts = [{"type": "web_url", "title": x["title"], "url": x["value"]} if x["type"] == "url"
                else {"type": "postback", "title": x["title"], "payload": f"MENU:{i}"} for i, x in enumerate(items)]
        await self._post(f"{self.user_id}/messenger_profile", json={
            "platform": "instagram",
            "persistent_menu": [{"locale": "default", "composer_input_disabled": False, "call_to_actions": acts}]})

    async def is_follower(self, igsid: str) -> bool | None:
        try:
            d = await self._get(igsid, fields="is_user_follow_business")
            return bool(d.get("is_user_follow_business"))
        except RuntimeError:
            return None

    async def profile(self, igsid: str) -> dict:
        """نام کاربری فرستنده‌ی دایرکت."""
        try:
            return await self._get(igsid, fields="username,name,is_user_follow_business")
        except RuntimeError:
            return {}

    async def account(self) -> dict:
        """تعداد فالوور و پست پیج."""
        return await self._get(self.user_id, fields="username,followers_count,follows_count,media_count")

    async def stories(self) -> list[dict]:
        """استوری‌های فعال (۲۴ ساعت اخیر)."""
        d = await self._get(f"{self.user_id}/stories",
                            fields="id,media_type,media_url,thumbnail_url,permalink,timestamp")
        return d.get("data", [])

    async def media(self, limit: int = 50) -> list[dict]:
        fields = "id,caption,media_type,media_product_type,permalink,thumbnail_url,media_url,timestamp"
        if not self.via_composio():
            return (await self._get(f"{self.user_id}/media", fields=fields, limit=limit)).get("data") or []
        out, after = [], None          # Composio پاسخ بزرگ را برنمی‌گرداند: صفحه‌های کوچک
        while len(out) < limit:
            q = {"fields": fields, "limit": min(8, limit - len(out))}
            if after:
                q["after"] = after
            d = await self._get(f"{self.user_id}/media", **q)
            out += d.get("data") or []
            after = ((d.get("paging") or {}).get("cursors") or {}).get("after")
            if not (d.get("paging") or {}).get("next") or not after:
                break
        return out

    async def refresh_token(self) -> tuple[str, int]:
        """توکن بلندمدت ۶۰ روزه را تمدید می‌کند. (token, expires_in_seconds)"""
        d = await self._get("refresh_access_token", grant_type="ig_refresh_token")
        return d["access_token"], int(d.get("expires_in", 0))
