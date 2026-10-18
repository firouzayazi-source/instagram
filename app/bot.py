"""The approval flow: Instagram event -> Claude draft -> Telegram card -> owner decides -> Instagram."""

import html
import logging
import time

import anthropic
import httpx

from .config import Settings
from .drafter import CATEGORY_LABELS, Drafter
from .instagram import Event, InstagramClient, InstagramError, parse_webhook
from .store import Item, Store
from .telegram import TelegramClient

log = logging.getLogger("bot")

TOKEN_REFRESH_EVERY = 7 * 24 * 3600

QR_HOWTO = ("برای ساختن: <code>/qradd عنوان | متن جواب</code>\n"
            "<code>{name}</code> جای اسم کاربر می‌شینه.")

HELP = ("ربات فعاله ✅\nکامنت‌ها و دایرکت‌های جدید اینجا میان.\n\n"
        "/qr – جواب‌های آماده\n"
        "/qradd عنوان | متن – ساخت جواب آماده\n"
        "/qrdel شماره – حذف جواب آماده\n"
        "/ig – چک اتصال اینستاگرام\n"
        "/token – تمدید توکن اینستاگرام")


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def short(s: str, n: int) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


class Bot:
    def __init__(self, settings: Settings, store: Store, ig: InstagramClient, tg: TelegramClient,
                 drafter: Drafter | None):
        self.s = settings
        self.store = store
        self.ig = ig
        self.tg = tg
        self.drafter = drafter

    @property
    def admin(self) -> int:
        return self.s.telegram_admin_chat_id

    # ---------- Instagram side ----------

    async def handle_instagram(self, payload: dict) -> None:
        for event in parse_webhook(payload, self.s.ig_user_id):
            try:
                await self._ingest(event)
            except Exception:
                log.exception("failed to handle event %s", event.ext_id)

    async def _ingest(self, event: Event) -> None:
        item = self.store.add_item(kind=event.kind, ext_id=event.ext_id, sender_id=event.sender_id,
                                   username=event.username, text=event.text, media_id=event.media_id,
                                   received_at=event.timestamp)
        if item is None:  # duplicate delivery
            return
        if item.kind == "dm":
            self.store.add_dm(item.sender_id, "them", item.text, item.received_at)
            if not item.username:
                self.store.update_item(item.id, username=await self.ig.get_username(item.sender_id))
        elif item.media_id:
            self.store.update_item(item.id, media_caption=await self.ig.get_media_caption(item.media_id))
        if not self.admin:
            log.warning("TELEGRAM_ADMIN_CHAT_ID is not set; item %s is waiting", item.id)
            return
        await self.draft_and_notify(self.store.get_item(item.id))

    async def draft_and_notify(self, item: Item, instruction: str = "") -> None:
        if self.drafter is None:  # no Claude key: the owner writes or picks a quick reply
            self.store.update_item(item.id, status="pending", error="")
            await self._post_card(self.store.get_item(item.id))
            return
        history = self.store.dm_history(item.sender_id)[:-1] if item.kind == "dm" else None
        try:
            d = await self.drafter.draft(kind=item.kind, text=item.text, username=item.username,
                                         media_caption=item.media_caption, history=history,
                                         instruction=instruction)
            fields = dict(category=d.category, draft=d.reply if d.should_reply else "", note=d.note)
        except (anthropic.APIError, ValueError, KeyError, StopIteration) as e:
            log.exception("drafting failed for item %s", item.id)
            fields = dict(draft="", note=f"خطا در ساخت پیش‌نویس: {short(str(e), 150)}")
        self.store.update_item(item.id, status="pending", error="", **fields)
        await self._post_card(self.store.get_item(item.id))

    # ---------- Telegram cards ----------

    def render(self, item: Item) -> tuple[str, list[list[dict]]]:
        who = f"@{esc(item.username)}" if item.username else f"کاربر {esc(item.sender_id)}"
        if item.kind == "comment":
            head = f"💬 <b>کامنت جدید</b> از {who}"
            if item.media_caption:
                head += f"\nروی پست: «{esc(short(item.media_caption, 80))}»"
        else:
            head = f"✉️ <b>دایرکت جدید</b> از {who}"
        lines = [head, f"<blockquote>{esc(item.text[:1500])}</blockquote>"]
        if item.category:
            lines.append(f"🏷 دسته: {CATEGORY_LABELS.get(item.category, item.category)}")
        if item.draft:
            lines.append(f"✍️ <b>پیش‌نویس:</b>\n<blockquote>{esc(item.draft)}</blockquote>")
        elif self.drafter:
            lines.append("✍️ پیشنهاد: <b>بی‌جواب</b>")
        if item.note:
            lines.append(f"ℹ️ {esc(item.note)}")

        final = {
            "sent": "✅ ارسال شد",
            "skipped": "❌ رد شد",
            "hidden": "🙈 کامنت مخفی شد",
        }
        if item.status in final:
            lines.append(f"\n<b>{final[item.status]}</b>")
            return "\n".join(lines), []
        if item.status == "failed":
            lines.append(f"\n⚠️ <b>ارسال نشد:</b> {esc(item.error)}")

        i = item.id
        row1 = ([{"text": "✅ ارسال", "callback_data": f"ap:{i}"}] if item.draft else []) + \
               [{"text": "✏️ ویرایش" if item.draft else "✏️ خودم می‌نویسم", "callback_data": f"ed:{i}"}]
        row1.append({"text": "⚡ جواب آماده", "callback_data": f"qr:{i}"})
        row2 = [{"text": "🔄 دوباره بنویس", "callback_data": f"rg:{i}"}] if self.drafter else []
        if item.kind == "comment":
            row2.append({"text": "🙈 مخفی کن", "callback_data": f"hd:{i}"})
        row2.append({"text": "❌ رد", "callback_data": f"sk:{i}"})
        return "\n".join(lines), [row1, row2]

    async def _post_card(self, item: Item) -> None:
        """Send a fresh card for the item (and retire the old one, if any)."""
        if item.tg_message_id:
            try:
                await self.tg.edit_message(self.admin, item.tg_message_id, "⤵️ نسخه‌ی جدید پایین‌تر")
            except (RuntimeError, httpx.HTTPError):
                pass
        text, buttons = self.render(item)
        msg_id = await self.tg.send_message(self.admin, text, buttons)
        self.store.update_item(item.id, tg_message_id=msg_id)

    async def _refresh_card(self, item: Item) -> None:
        text, buttons = self.render(item)
        if item.tg_message_id:
            await self.tg.edit_message(self.admin, item.tg_message_id, text, buttons)

    # ---------- Telegram side ----------

    async def handle_telegram(self, update: dict) -> None:
        if cq := update.get("callback_query"):
            await self._on_callback(cq)
        elif (msg := update.get("message")) and msg.get("text"):
            await self._on_message(msg)

    async def _on_message(self, msg: dict) -> None:
        chat_id = msg["chat"]["id"]
        text = msg["text"].strip()
        if chat_id != self.admin:
            if text.startswith("/start") and not self.admin:
                await self.tg.send_message(
                    chat_id, f"شناسه‌ی چت شما: <code>{chat_id}</code>\n"
                             "این عدد را در TELEGRAM_ADMIN_CHAT_ID بگذارید و سرور را ری‌استارت کنید.")
            return
        if text.startswith("/start") or text.startswith("/help"):
            await self.tg.send_message(chat_id, HELP)
            return
        if text.startswith("/qradd"):
            title, sep, body = text.removeprefix("/qradd").partition("|")
            if not sep or not title.strip() or not body.strip():
                await self.tg.send_message(chat_id, "شکلش این‌طوریه:\n<code>/qradd قیمت | سلام {name}، قیمت‌ها توی هایلایت هست.</code>")
                return
            qr_id = self.store.add_quick_reply(title.strip(), body.strip())
            await self.tg.send_message(chat_id, f"✅ جواب آماده‌ی شماره‌ی {qr_id} ذخیره شد.")
            return
        if text.startswith("/qrdel"):
            arg = text.removeprefix("/qrdel").strip()
            done = arg.isdigit() and self.store.delete_quick_reply(int(arg))
            await self.tg.send_message(chat_id, "🗑 حذف شد." if done else "شماره پیدا نشد. فهرست: /qr")
            return
        if text.startswith("/qr"):
            qrs = self.store.quick_replies()
            if not qrs:
                await self.tg.send_message(chat_id, "هنوز جواب آماده‌ای نیست.\n" + QR_HOWTO)
                return
            lines = [f"<b>{i}.</b> {esc(t)}\n{esc(short(b, 120))}" for i, t, b in qrs]
            await self.tg.send_message(chat_id, "⚡ <b>جواب‌های آماده</b>\n\n" + "\n\n".join(lines) +
                                       "\n\nحذف: <code>/qrdel شماره</code>")
            return
        if text.startswith("/ig"):
            try:
                me = await self.ig.me()
                ok = str(me.get("user_id")) == self.s.ig_user_id
                await self.tg.send_message(chat_id, (
                    f"✅ توکن اینستاگرام کار می‌کنه\n"
                    f"پیج: @{esc(str(me.get('username', '')))} ({esc(str(me.get('account_type', '')))})\n"
                    f"فالوور: {me.get('followers_count', '?')} — پست: {me.get('media_count', '?')}\n"
                    f"IG_USER_ID: <code>{esc(str(me.get('user_id', '')))}</code>\n" +
                    ("✔ با .env یکیه" if ok else "⚠️ این عدد رو جلوی IG_USER_ID توی .env بذارید و ری‌استارت کنید")))
            except (InstagramError, httpx.HTTPError) as e:
                await self.tg.send_message(chat_id, f"✘ توکن اینستاگرام کار نکرد: {esc(short(str(e), 200))}")
            return
        if text.startswith("/token"):
            await self.tg.send_message(chat_id, await self.refresh_ig_token(force=True))
            return

        pending = self.store.get("await_edit")
        if not pending:
            await self.tg.send_message(chat_id, "برای ویرایش، اول روی دکمه‌ی ✏️ زیر یکی از پیام‌ها بزنید.")
            return
        self.store.delete("await_edit")
        item = self.store.get_item(int(pending))
        if not item or item.status not in ("pending", "failed"):
            return
        if text.startswith("!") and self.drafter:
            await self.draft_and_notify(item, instruction=text[1:].strip())
        else:
            self.store.update_item(item.id, draft=text, note="متن خودتان", status="pending", error="")
            await self._post_card(self.store.get_item(item.id))

    async def _on_callback(self, cq: dict) -> None:
        chat_id = cq.get("message", {}).get("chat", {}).get("id")
        if chat_id != self.admin or cq.get("from", {}).get("id") != self.admin:
            await self.tg.answer_callback(cq["id"], "دسترسی ندارید")
            return
        action, _, raw_id = cq.get("data", "").partition(":")
        item_part = raw_id.partition(":")[0]
        item = self.store.get_item(int(item_part)) if item_part.isdigit() else None
        if not item or item.status not in ("pending", "failed"):
            await self.tg.answer_callback(cq["id"], "این مورد قبلاً بسته شده")
            return

        if action == "ap":
            await self.tg.answer_callback(cq["id"], "در حال ارسال…")
            await self.approve(item)
        elif action == "ed":
            self.store.set("await_edit", str(item.id))
            await self.tg.answer_callback(cq["id"])
            hint = ("\nاگر با <b>!</b> شروع کنید، دستور بازنویسی برای Claude است "
                    "(مثلاً: <code>!کوتاه‌تر و خودمونی‌تر</code>).") if self.drafter else ""
            await self.tg.send_message(self.admin, "متن جواب را بفرستید." + hint, force_reply=True)
        elif action == "qr":
            await self.tg.answer_callback(cq["id"])
            qrs = self.store.quick_replies()
            if not qrs:
                await self.tg.send_message(self.admin, "هنوز جواب آماده‌ای نیست.\n" + QR_HOWTO)
                return
            buttons = [[{"text": short(t, 40), "callback_data": f"qp:{item.id}:{i}"}] for i, t, _ in qrs[:30]]
            await self.tg.send_message(self.admin, "کدوم جواب آماده؟", buttons)
        elif action == "qp":
            await self.tg.answer_callback(cq["id"])
            item_id, _, qr_raw = raw_id.partition(":")
            qr = self.store.get_quick_reply(int(qr_raw)) if qr_raw.isdigit() else None
            if qr:
                title, body = qr
                body = body.replace("{name}", item.username or "").replace("  ", " ")
                self.store.update_item(item.id, draft=body, note=f"جواب آماده: {title}", status="pending", error="")
                await self._post_card(self.store.get_item(item.id))
        elif action == "rg" and self.drafter:
            await self.tg.answer_callback(cq["id"], "در حال بازنویسی…")
            await self.draft_and_notify(item, instruction="یک نسخه‌ی متفاوت با پیش‌نویس قبلی بنویس.")
        elif action == "hd" and item.kind == "comment":
            await self.tg.answer_callback(cq["id"])
            try:
                await self.ig.hide_comment(item.ext_id)
                self.store.update_item(item.id, status="hidden")
            except (InstagramError, httpx.HTTPError) as e:
                self.store.update_item(item.id, status="failed", error=short(str(e), 200))
            await self._refresh_card(self.store.get_item(item.id))
        elif action == "sk":
            await self.tg.answer_callback(cq["id"])
            self.store.update_item(item.id, status="skipped")
            await self._refresh_card(self.store.get_item(item.id))
        else:
            await self.tg.answer_callback(cq["id"])

    async def approve(self, item: Item) -> None:
        if not item.draft:
            return
        if "{{" in item.draft:
            self.store.update_item(item.id, status="failed",
                                   error="پیش‌نویس هنوز جای خالی {{...}} دارد؛ ویرایشش کنید.")
            await self._refresh_card(self.store.get_item(item.id))
            return
        if item.kind == "dm" and time.time() - item.received_at > self.s.dm_window_hours * 3600:
            self.store.update_item(item.id, status="failed",
                                   error=f"بیش از {self.s.dm_window_hours} ساعت از پیام گذشته؛ "
                                         "اینستاگرام اجازه‌ی جواب از طریق API نمی‌دهد. از خود اپ جواب دهید.")
            await self._refresh_card(self.store.get_item(item.id))
            return
        self.store.update_item(item.id, status="sending")
        try:
            if item.kind == "comment":
                await self.ig.reply_to_comment(item.ext_id, item.draft)
            else:
                await self.ig.send_dm(item.sender_id, item.draft)
                self.store.add_dm(item.sender_id, "me", item.draft)
            self.store.update_item(item.id, status="sent", error="")
        except (InstagramError, httpx.HTTPError) as e:
            self.store.update_item(item.id, status="failed", error=short(str(e), 200))
        await self._refresh_card(self.store.get_item(item.id))

    # ---------- token upkeep ----------

    async def refresh_ig_token(self, force: bool = False) -> str:
        if not (self.store.get("ig_token") or self.s.ig_access_token):
            return "توکن اینستاگرام هنوز تنظیم نشده."
        last = self.store.get("ig_token_refreshed_at")
        if last is None and not force:
            # First start: the token was just generated (valid 60 days), so start the clock now.
            self.store.set("ig_token_refreshed_at", str(time.time()))
            return "نیازی به تمدید نیست."
        if not force and time.time() - float(last) < TOKEN_REFRESH_EVERY:
            return "نیازی به تمدید نیست."
        try:
            token, expires_in = await self.ig.refresh_token()
        except (InstagramError, httpx.HTTPError, KeyError) as e:
            log.warning("token refresh failed: %s", e)
            return f"⚠️ تمدید توکن اینستاگرام نشد: {esc(short(str(e), 200))}"
        self.store.set("ig_token", token)
        self.store.set("ig_token_refreshed_at", str(time.time()))
        return f"✅ توکن تمدید شد ({expires_in // 86400} روز اعتبار)."
