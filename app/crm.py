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
    if phone:
        c.execute("UPDATE customers SET phone=? WHERE id=? AND phone=''", (phone, key))
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


def search(c, q: str = "", tag: str = "", limit: int = 100) -> list[dict]:
    where, args = ["1"], []
    if q:
        like = f"%{q.strip().lstrip('@')}%"
        where.append("(username LIKE ? OR name LIKE ? OR phone LIKE ? OR notes LIKE ?)")
        args += [like, like, like, like]
    if tag:
        where.append("tags LIKE ?")
        args.append(f'%"{tag}"%')
    rows = c.execute(f"SELECT * FROM customers WHERE {' AND '.join(where)} ORDER BY last_seen DESC LIMIT ?",
                     [*args, limit])
    return [_row(r) for r in rows]


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
