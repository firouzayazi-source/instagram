"""پرونده‌ی مشتری: خودکار از هر کامنت و دایرکت ساخته و به‌روز می‌شود؛ برچسب، یادداشت و شماره از پنل.

شماره‌ی موبایلی که مشتری خودش در پیام بنویسد خودکار در پرونده می‌نشیند؛ برچسب «قصد خرید»، «اقساطی»
و «شکایت» از تشخیص مغز مرکزی می‌آید.
"""
import json
import re
import time

from .normalize import normalize

TAGS = ["قصد خرید", "اقساطی", "شکایت", "VIP", "خرید کرده", "همکار/فروشنده", "پیگیری"]
AUTO_TAGS = {"purchase": "قصد خرید", "installment": "اقساطی", "complaint": "شکایت"}
_PHONE = re.compile(r"(?<!\d)(?:\+?98|0)?9\d{9}(?!\d)")


def cid(channel: str, user_id: str) -> str:
    return f"{channel}:{user_id}"


def find_phone(text: str) -> str:
    m = _PHONE.search(normalize(text or "").replace(" ", "").replace("-", ""))
    if not m:
        return ""
    d = m.group(0)
    return "0" + d[-10:]


def touch(c, channel: str, user_id: str, username: str | None, kind: str, text: str = "") -> str:
    """یک پیام یا کامنت تازه: پرونده را می‌سازد یا به‌روز می‌کند. kind: message | comment"""
    now, key = time.time(), cid(channel, user_id)
    col = "comments" if kind == "comment" else "messages"
    c.execute(f"INSERT INTO customers(id,channel,user_id,username,first_seen,last_seen,{col}) VALUES (?,?,?,?,?,?,1) "
              f"ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen, {col}={col}+1, "
              f"username=COALESCE(excluded.username, username)", (key, channel, user_id, username, now, now))
    phone = find_phone(text)
    if phone and c.execute("UPDATE customers SET phone=? WHERE id=? AND phone=''", (phone, key)).rowcount:
        from . import webhook
        webhook.fire(c, "lead", {"channel": channel, "user_id": user_id, "username": username or "", "phone": phone,
                                 "text": (text or "")[:500]})
    return key


def add_tag(c, key: str, tag: str) -> None:
    row = c.execute("SELECT tags FROM customers WHERE id=?", (key,)).fetchone()
    if not row:
        return
    tags = json.loads(row["tags"] or "[]")
    if tag not in tags:
        c.execute("UPDATE customers SET tags=? WHERE id=?", (json.dumps(tags + [tag], ensure_ascii=False), key))


def auto_tag(c, key: str, intent: str | None) -> None:
    if intent in AUTO_TAGS:
        add_tag(c, key, AUTO_TAGS[intent])


def _row(r) -> dict:
    d = dict(r)
    d["tags"] = json.loads(d["tags"] or "[]")
    return d


WINDOW = 24 * 3600     # پنجره‌ی پیام اینستاگرام: تا ۲۴ ساعت بعد از آخرین پیام مشتری می‌شود دایرکت داد
_LAST_IN = "(SELECT MAX(created_at) FROM messages m WHERE m.user_id=customers.user_id AND m.direction='in')"


def search(c, q: str = "", tag: str = "", limit: int = 100, *, phone: str = "", window: str = "", days: int = 0,
           ordered: str = "") -> list[dict]:
    """phone: yes | no · window: open (پنجره‌ی ۲۴ ساعته باز) | closed · days: آخرین پیام در این چند روز ·
    ordered: yes (سفارش داده) | no"""
    where, args = ["1"], []
    now = time.time()
    if phone == "yes":
        where.append("phone<>''")
    elif phone == "no":
        where.append("phone=''")
    if window == "open":
        where.append(f"COALESCE({_LAST_IN},0)>?"); args.append(now - WINDOW)
    elif window == "closed":
        where.append(f"COALESCE({_LAST_IN},0)<=?"); args.append(now - WINDOW)
    if days:
        where.append("last_seen>?"); args.append(now - days * 86400)
    if ordered == "yes":
        where.append("EXISTS (SELECT 1 FROM orders o WHERE o.user_id=customers.user_id)")
    elif ordered == "no":
        where.append("NOT EXISTS (SELECT 1 FROM orders o WHERE o.user_id=customers.user_id)")
    if q:
        like = f"%{q.strip().lstrip('@')}%"
        where.append("(username LIKE ? OR name LIKE ? OR phone LIKE ? OR notes LIKE ?)")
        args += [like, like, like, like]
    if tag:
        where.append("tags LIKE ?")
        args.append(f'%"{tag}"%')
    rows = c.execute(f"SELECT *, {_LAST_IN} AS last_in FROM customers WHERE {' AND '.join(where)} "
                     "ORDER BY last_seen DESC LIMIT ?", [*args, limit])
    out = []
    for r in rows:
        d = _row(r)
        d["window_left"] = max(0, int((d["last_in"] or 0) + WINDOW - now)) if d["channel"] == "ig" else 0
        out.append(d)
    return out


def bulk(c, keys: list[str], action: str, value: str = "") -> dict:
    """کار گروهی روی مخاطبین: tag_add | tag_remove | message (فقط برای کسانی که پنجره‌ی ۲۴ ساعته‌شان باز است،
    با فاصله‌ی چند ثانیه از صف پیگیری‌ها فرستاده می‌شود)."""
    keys = [k for k in dict.fromkeys(keys or []) if isinstance(k, str)][:500]
    value = (value or "").strip()
    if action in ("tag_add", "tag_remove"):
        tag = value[:30]
        if not tag:
            raise ValueError("برچسب خالی است")
        n = 0
        for k in keys:
            row = c.execute("SELECT tags FROM customers WHERE id=?", (k,)).fetchone()
            if not row:
                continue
            tags = json.loads(row["tags"] or "[]")
            new = (tags + [tag]) if action == "tag_add" and tag not in tags else [t for t in tags if t != tag]
            if new != tags:
                c.execute("UPDATE customers SET tags=? WHERE id=?", (json.dumps(new, ensure_ascii=False), k)); n += 1
        return {"changed": n}
    if action == "message":
        if not value:
            raise ValueError("متن پیام خالی است")
        now, queued, closed = time.time(), 0, 0
        for k in keys:
            r = c.execute(f"SELECT user_id, channel, {_LAST_IN} AS last_in FROM customers WHERE id=?", (k,)).fetchone()
            if not r or r["channel"] != "ig":
                continue
            if (r["last_in"] or 0) + WINDOW <= now + 60:
                closed += 1
                continue
            c.execute("INSERT INTO followups(rule_id,user_id,text,due_at) VALUES (0,?,?,?)",
                      (r["user_id"], value[:900], now + queued * 4))
            queued += 1
        return {"queued": queued, "window_closed": closed}
    raise ValueError("کار ناشناخته")


def get(c, key: str) -> dict | None:
    r = c.execute("SELECT * FROM customers WHERE id=?", (key,)).fetchone()
    if not r:
        return None
    d = _row(r)
    uid = d["user_id"]
    events = [{"at": m["created_at"], "kind": "dm_" + m["direction"], "text": m["text"]}
              for m in c.execute("SELECT * FROM messages WHERE user_id=? ORDER BY created_at DESC LIMIT 100", (uid,))]
    events += [{"at": x["created_at"], "kind": "comment", "text": x["text"], "media_id": x["media_id"]}
               for x in c.execute("SELECT * FROM comments WHERE user_id=? ORDER BY created_at DESC LIMIT 100", (uid,))]
    events += [{"at": x["created_at"], "kind": "handoff", "text": x["reason"] or x["text"]}
               for x in c.execute("SELECT * FROM handoffs WHERE user_id=? ORDER BY created_at DESC LIMIT 30", (uid,))]
    d["timeline"] = sorted(events, key=lambda e: e["at"], reverse=True)[:150]
    return d


def update(c, key: str, patch: dict) -> dict:
    if not c.execute("SELECT 1 FROM customers WHERE id=?", (key,)).fetchone():
        raise ValueError("پرونده پیدا نشد")
    sets, args = [], []
    if "name" in patch:
        sets.append("name=?"); args.append(str(patch["name"] or "").strip()[:100])
    if "notes" in patch:
        sets.append("notes=?"); args.append(str(patch["notes"] or "").strip()[:4000])
    if "phone" in patch:
        p = str(patch["phone"] or "").strip()
        if p and not find_phone(p):
            raise ValueError("شماره‌ی موبایل نامعتبر")
        sets.append("phone=?"); args.append(find_phone(p) if p else "")
    if "tags" in patch:
        tags = [str(t).strip()[:30] for t in patch["tags"] or [] if str(t).strip()][:20]
        sets.append("tags=?"); args.append(json.dumps(list(dict.fromkeys(tags)), ensure_ascii=False))
    if sets:
        c.execute(f"UPDATE customers SET {', '.join(sets)} WHERE id=?", [*args, key])
    return get(c, key)


def all_tags(c) -> list[str]:
    seen = list(TAGS)
    for (t,) in c.execute("SELECT tags FROM customers WHERE tags<>'[]'"):
        for x in json.loads(t):
            if x not in seen:
                seen.append(x)
    return seen
