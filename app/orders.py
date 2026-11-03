"""فروش در دایرکت: ربات قدم‌به‌قدم سفارش می‌گیرد، روش پرداخت را می‌گوید و عکس رسید را می‌شناسد.

شروع: لمس دکمه‌ی «🛒 سفارش» زیر کارت محصول، یا پیامی مثل «ثبت سفارش» / «می‌خوام بخرم ۱۳ پرو».
قدم‌ها: محصول (اگر معلوم نبود) ← نام ← شماره ← شهر ← آدرس ← تأیید. چیزی که در پرونده‌ی مشتری
هست دوباره پرسیده نمی‌شود. «لغو» هر جا گفتگو را می‌بندد. سؤالی که وسط کار بپرسد (با «؟») به
روال عادی می‌رود و سفارش سر جایش می‌ماند. بعد از ثبت، عکسی که مشتری تا ۳ روز بفرستد رسید آن
سفارش است و با عکس به گروه پشتیبانی تلگرام می‌رود.
"""
import asyncio
import json
import re
import time

from . import brain_engine, crm, db, push, tg_notify, webhook
from .normalize import normalize

STATUSES = {"new": "منتظر هماهنگی", "awaiting_payment": "منتظر پرداخت", "receipt": "رسید رسیده",
            "confirmed": "تأیید شد", "shipped": "ارسال شد", "done": "تحویل شد", "canceled": "لغو شد"}
FLOW_TTL = 24 * 3600
RECEIPT_DAYS = 3
PROMPTS = {
    "product": "کدوم محصول رو می‌خواید؟ اسم مدل رو بنویسید (مثلاً «۱۳ پرو ۲۵۶») 🙏",
    "name": "برای ثبت سفارش، نام و نام خانوادگی‌تون رو بنویسید 🙏",
    "phone": "شماره‌ی موبایل‌تون رو بنویسید (مثلاً ۰۹۱۲۱۲۳۴۵۶۷) 📱",
    "city": "شهر و استان‌تون؟ 🏙",
    "address": "آدرس کامل پستی و کد پستی رو بنویسید 📦",
}
STEPS = ["product", "name", "phone", "city", "address", "confirm"]
CANCEL = {"لغو", "انصراف", "کنسل", "بیخیال", "نمیخوام", "لغو سفارش", "منصرف شدم"}
YES = {"بله", "اره", "آره", "بلی", "تایید", "تأیید", "درسته", "اوکی", "ok", "باشه", "اوکیه", "صحیحه", "اره درسته",
       "بله درسته", "تایید میکنم", "ثبت کن", "ثبت"}
NO = {"نه", "خیر", "اصلاح", "ویرایش", "تغییر", "غلطه", "اشتباهه"}
START_RX = re.compile(r"(?:^|\s)(?:ثبت\s*سفارش|سفارش\s*(?:بدم|میدم|میخوام)|میخوام\s*(?:سفارش\s*بدم|بخرم|بخرمش|"
                      r"خرید\s*کنم)|میخواستم\s*(?:بخرم|سفارش\s*بدم)|خرید\s*میکنم)(?:\s|$)|^(?:سفارش|خرید)$")


def _bg(coro) -> None:
    try:
        asyncio.get_running_loop().create_task(coro)
    except RuntimeError:
        coro.close()


def _flow(c, uid: str) -> dict | None:
    r = c.execute("SELECT * FROM order_flow WHERE user_id=?", (uid,)).fetchone()
    if not r:
        return None
    if time.time() - r["updated_at"] > FLOW_TTL:
        c.execute("DELETE FROM order_flow WHERE user_id=?", (uid,))
        return None
    return {"step": r["step"], "data": json.loads(r["data"] or "{}")}


def active(c, uid: str) -> bool:
    return _flow(c, uid) is not None


def _save(c, uid: str, step: str, data: dict) -> None:
    c.execute("INSERT INTO order_flow(user_id,step,data,updated_at) VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE "
              "SET step=excluded.step, data=excluded.data, updated_at=excluded.updated_at",
              (uid, step, json.dumps(data, ensure_ascii=False), time.time()))


def _clear(c, uid: str) -> None:
    c.execute("DELETE FROM order_flow WHERE user_id=?", (uid,))


def wants_order(text: str) -> bool:
    return bool(START_RX.search(normalize(text)))


def _fmt(n) -> str:
    return f"{int(n):,}".translate(str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬")) + " تومان" if n else "استعلام"


def _next_step(data: dict, after: str | None) -> str:
    """قدم بعدی که جوابش هنوز نیامده."""
    start = STEPS.index(after) + 1 if after else 0
    for st in STEPS[start:]:
        if st == "confirm" or not data.get(st):
            return st
    return "confirm"


def _summary(data: dict) -> str:
    return (f"🧾 خلاصه‌ی سفارش:\n\n📱 {data.get('product')}" + (f"\n💰 {_fmt(data.get('price'))}" if data.get("price") else "")
            + f"\n👤 {data.get('name')}\n☎️ {data.get('phone')}\n🏙 {data.get('city')}\n📦 {data.get('address')}"
            + "\n\nاگه درسته «بله» رو بفرستید تا ثبت بشه؛ برای اصلاح «ویرایش» و برای انصراف «لغو».")


def _prompt(step: str, data: dict) -> str:
    return _summary(data) if step == "confirm" else PROMPTS[step]


def _match_product(text: str) -> dict:
    cards = brain_engine.cards_for(text, limit=1, strict=True)
    if cards:
        x = cards[0]
        return {"product": x["title"], "product_id": x["id"], "price": x["price"], "url": x["url"]}
    return {}


def start(c, uid: str, username: str | None, product_id: str = "", text: str = "") -> str:
    """گفتگوی سفارش را شروع می‌کند و اولین سؤال را برمی‌گرداند."""
    data: dict = {}
    if product_id:
        p = brain_engine.product_by_id(product_id)
        if p:
            data = {"product": p["name"], "product_id": p["id"], "price": p["price"], "url": p["url"]}
    if not data and text:
        data = _match_product(text)
    cust = c.execute("SELECT name, phone FROM customers WHERE id=?", (crm.cid("ig", uid),)).fetchone()
    if cust:
        data.update({k: cust[k] for k in ("name", "phone") if cust[k]})
    data["username"] = username or ""
    step = _next_step(data, None)
    _save(c, uid, step, data)
    head = f"عالیه! 🛒 سفارش «{data['product']}»" + (f" ({_fmt(data.get('price'))})" if data.get("price") else "") + "\n\n" \
        if data.get("product") else "عالیه! 🛒 بریم برای ثبت سفارش.\n\n"
    return head + _prompt(step, data) + ("\n\n(هر وقت خواستید «لغو» بنویسید)" if step != "confirm" else "")


def handle(c, uid: str, username: str | None, text: str, images: list[str], s: dict) -> str | None:
    """پیام مشتری در دایرکت. متن جواب، یا None اگر به سفارش مربوط نبود (روال عادی ادامه می‌یابد)."""
    f = _flow(c, uid)
    if f is None:
        if images:
            return receipt(c, uid, username, images[0])
        if s.get("order_enabled") and text and wants_order(text):
            return start(c, uid, username, text=text)
        return None
    n = normalize(text)
    if n in CANCEL:
        _clear(c, uid)
        return "سفارش لغو شد. هر وقت خواستید دوباره «ثبت سفارش» بنویسید 🌸"
    step, data = f["step"], f["data"]
    if images and step != "confirm":
        return "ممنون 🙏 اول اطلاعات سفارش رو کامل کنیم؛ رسید رو بعد از ثبت سفارش بفرستید.\n\n" + _prompt(step, data)
    if not n:
        return None
    if text.strip().endswith(("?", "؟")) and step != "confirm":
        return None          # سؤال وسط کار: جواب عادی می‌گیرد، سفارش منتظر می‌ماند
    if step == "product":
        data.update(_match_product(text) or {"product": text.strip()[:100]})
    elif step == "name":
        if len(n) < 3 or re.search(r"\d", n):
            return "لطفاً نام و نام خانوادگی رو با حروف بنویسید 🙏"
        data["name"] = text.strip()[:100]
    elif step == "phone":
        phone = crm.find_phone(text)
        if not phone:
            return "شماره درست نیست 🙏 یه شماره‌ی موبایل ۱۱ رقمی مثل ۰۹۱۲۱۲۳۴۵۶۷ بنویسید."
        data["phone"] = phone
    elif step == "city":
        if len(n) < 2:
            return PROMPTS["city"]
        data["city"] = text.strip()[:100]
    elif step == "address":
        if len(n) < 10:
            return "آدرس کامل‌تر بنویسید لطفاً (خیابان، کوچه، پلاک، کد پستی) 📦"
        data["address"] = text.strip()[:500]
    elif step == "confirm":
        if n in YES:
            _clear(c, uid)
            return _create(c, uid, username, data, s)
        if n in NO:
            for k in ("name", "phone", "city", "address"):
                data.pop(k, None)
            _save(c, uid, "name", data)
            return "باشه، از اول می‌پرسم ✍️\n\n" + PROMPTS["name"]
        return "برای ثبت «بله»، برای اصلاح «ویرایش» و برای انصراف «لغو» رو بفرستید 🙏"
    nxt = _next_step(data, step)
    _save(c, uid, nxt, data)
    return _prompt(nxt, data)


def _row(r) -> dict:
    d = dict(r)
    d["status_label"] = STATUSES.get(d["status"], d["status"])
    return d


def _public(o: dict) -> dict:
    return {k: o[k] for k in ("id", "channel", "user_id", "username", "product", "product_id", "price", "name", "phone",
                              "city", "address", "status", "created_at", "updated_at")}


def _create(c, uid: str, username: str | None, data: dict, s: dict) -> str:
    pay = (s.get("order_payment_text") or "").strip()
    now = time.time()
    oid = c.execute(
        "INSERT INTO orders(channel,user_id,username,product,product_id,price,name,phone,city,address,status,"
        "created_at,updated_at) VALUES ('ig',?,?,?,?,?,?,?,?,?,?,?,?)",
        (uid, username or data.get("username") or "", data.get("product", ""), data.get("product_id", ""),
         data.get("price"), data["name"], data["phone"], data["city"], data["address"],
         "awaiting_payment" if pay else "new", now, now)).lastrowid
    key = crm.cid("ig", uid)
    c.execute("UPDATE customers SET name=CASE WHEN name='' THEN ? ELSE name END, "
              "phone=CASE WHEN phone='' THEN ? ELSE phone END WHERE id=?", (data["name"], data["phone"], key))
    crm.add_tag(c, key, "قصد خرید")
    o = _row(c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone())
    who = f"@{o['username']}" if o["username"] else uid
    tg_notify.send(f"🛒 سفارش تازه #{oid} از اینستاگرام\n\n📱 {o['product']}"
                   + (f" · {_fmt(o['price'])}" if o["price"] else "")
                   + f"\n👤 {o['name']} · {o['phone']}\n🏙 {o['city']}\n📦 {o['address']}\n💬 {who}"
                   + f"\n\n🔗 https://ig.stland.ir/#/orders/{oid}")
    _bg(push.notify_all(f"🛒 سفارش تازه #{oid}", f"{o['name']}: {o['product']}"[:160], f"/#/orders/{oid}"))
    webhook.fire(c, "order", _public(o))
    done = f"✅ سفارش شماره‌ی {_fa(oid)} ثبت شد."
    if pay:
        return f"{done}\n\n💳 {pay}\n\nبعد از پرداخت، عکس رسید رو همین‌جا بفرستید 🙏"
    return f"{done}\n\nهمکارم برای هماهنگی پرداخت و ارسال به‌زودی پیام می‌ده 🙏"


def _fa(n) -> str:
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def receipt(c, uid: str, username: str | None, url: str) -> str | None:
    """عکسی که مشتری فرستاده؛ اگر سفارش منتظر پرداخت دارد، رسید همان سفارش است."""
    o = c.execute("SELECT * FROM orders WHERE user_id=? AND status IN ('awaiting_payment','new') AND created_at>? "
                  "ORDER BY created_at DESC LIMIT 1", (uid, time.time() - RECEIPT_DAYS * 86400)).fetchone()
    if not o:
        return None
    c.execute("UPDATE orders SET status='receipt', receipt_url=?, updated_at=? WHERE id=?", (url[:2000], time.time(), o["id"]))
    who = f"@{username}" if username else uid
    tg_notify.send(f"🧾 رسید پرداخت سفارش #{o['id']}\n\n📱 {o['product']}" + (f" · {_fmt(o['price'])}" if o["price"] else "")
                   + f"\n👤 {o['name']} · {o['phone']}\n💬 {who}\n\n🔗 https://ig.stland.ir/#/orders/{o['id']}", photo=url)
    _bg(push.notify_all(f"🧾 رسید سفارش #{o['id']}", f"{o['name']}: {o['product']}"[:160], f"/#/orders/{o['id']}"))
    webhook.fire(c, "order_status", {**_public(_row(o)), "status": "receipt"})
    return f"🧾 رسید سفارش {_fa(o['id'])} رسید، ممنون! همکارم بررسی می‌کنه و برای ارسال هماهنگ می‌کنه 🙏"


# ---------- پنل ----------

def list_orders(c, status: str = "", limit: int = 200) -> list[dict]:
    where, args = ("status=?", [status]) if status else ("1", [])
    return [_row(r) for r in c.execute(f"SELECT * FROM orders WHERE {where} ORDER BY created_at DESC LIMIT ?",
                                       [*args, limit])]


def get(c, oid: int) -> dict | None:
    r = c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    return _row(r) if r else None


def update(c, oid: int, patch: dict) -> dict:
    o = get(c, oid)
    if not o:
        raise ValueError("سفارش پیدا نشد")
    sets, args = [], []
    if "status" in patch:
        if patch["status"] not in STATUSES:
            raise ValueError("وضعیت نامعتبر")
        sets.append("status=?"); args.append(patch["status"])
    for k, n in (("note", 2000), ("name", 100), ("city", 100), ("address", 500), ("product", 100)):
        if k in patch:
            sets.append(f"{k}=?"); args.append(str(patch[k] or "").strip()[:n])
    if "phone" in patch:
        p = crm.find_phone(str(patch["phone"] or ""))
        if not p:
            raise ValueError("شماره‌ی موبایل نامعتبر")
        sets.append("phone=?"); args.append(p)
    if "price" in patch:
        sets.append("price=?"); args.append(int(patch["price"]) if patch["price"] else None)
    if not sets:
        return o
    c.execute(f"UPDATE orders SET {', '.join(sets)}, updated_at=? WHERE id=?", [*args, time.time(), oid])
    new = get(c, oid)
    if new["status"] != o["status"]:
        if new["status"] in ("done", "shipped"):
            crm.add_tag(c, crm.cid(new["channel"], new["user_id"]), "خرید کرده")
        webhook.fire(c, "order_status", _public(new))
    return new


def stats(c) -> dict:
    rows = c.execute("SELECT status, COUNT(*) n, COALESCE(SUM(price),0) total FROM orders GROUP BY status").fetchall()
    return {r["status"]: {"count": r["n"], "total": r["total"]} for r in rows}
