"""رضایت مشتری و یادگیری خودکار.

زیر جواب‌های هوش مصنوعی (نه موتور فهم که خودش آفلاین است) از مشتری می‌پرسیم «مفید بود؟». جوابی که مشتری
پسندید، اگر به اطلاعات لحظه‌ای (قیمت، موجودی، لینک کالا) وابسته نباشد، به دانش آفلاین مشترک می‌رود: دفعه‌ی
بعد همان سؤال در اینستاگرام، تلگرام و هر کانال دیگر بی‌هزینه و فوری از موتور فهم جواب می‌گیرد.
هر آموخته در پنل («مغز مرکزی ← آموخته‌ها») دیده و با یک لمس برگردانده می‌شود.
"""
import re
import time

from . import shared_kb
from .normalize import normalize

UP, DOWN = "up", "down"
# جواب‌هایی که کهنه می‌شوند یاد گرفته نمی‌شوند
VOLATILE_INTENTS = {"price", "availability", "purchase", "complaint"}
_VOLATILE = re.compile(r"\d[\d٬,.]*\s*(?:میلیون|تومان|تومن|هزار)|[۰-۹][۰-۹٬,.]*\s*(?:میلیون|تومان|تومن|هزار)|"
                       r"stland\.ir/\?p=|موجود(?:ی)?\s*(?:داریم|نداریم)|امروز|الان")


def _row(c, log_id: int):
    return c.execute("SELECT * FROM ai_log WHERE id=?", (log_id,)).fetchone()


def learnable(r) -> bool:
    if not r or r["action"] != "reply" or r["is_test"] or not (r["reply"] or "").strip():
        return False
    if (r["model"] or "") in ("", "brain") or (r["intent"] or "") in VOLATILE_INTENTS:
        return False
    q, a = r["input"] or "", r["reply"] or ""
    if not (3 <= len(normalize(q)) <= 300) or len(a) > 900:
        return False
    return not _VOLATILE.search(a)


def vote(c, log_id: int, v: str, s: dict, owner: str | None = None) -> dict:
    """رأی مشتری. owner (شناسه‌ی کاربر در ai_log) تا هر کس فقط به جواب خودش رأی بدهد.
    خروجی: {"ok", "learned"}."""
    r = _row(c, log_id)
    if not r or v not in (UP, DOWN) or (owner is not None and r["user_id"] != owner):
        return {"ok": False, "learned": False}
    c.execute("UPDATE ai_log SET customer_vote=?, voted_at=? WHERE id=?", (v, time.time(), log_id))
    learned = v == UP and s.get("auto_learn", True) and learn(c, log_id)
    return {"ok": True, "learned": bool(learned)}


def learn(c, log_id: int) -> bool:
    """جواب این لاگ را به دانش آفلاین مشترک می‌سپارد (اگر قابل یادگیری و تکراری نباشد)."""
    r = _row(c, log_id)
    if not learnable(r) or not shared_kb.ready():
        return False
    q = r["input"].strip()[:300]
    qn = normalize(q)
    if c.execute("SELECT 1 FROM learned WHERE qnorm=?", (qn,)).fetchone():
        return False
    try:
        shared_kb.save_intent({"keys": [], "examples": [q], "answer": r["reply"].strip(), "enabled": True})
    except ValueError:
        return False
    c.execute("INSERT INTO learned(log_id,channel,question,qnorm,answer,created_at) VALUES (?,?,?,?,?,?)",
              (log_id, r["channel"], q, qn, r["reply"].strip(), time.time()))
    return True


def items(c, limit: int = 200) -> list[dict]:
    return [dict(x) for x in c.execute("SELECT * FROM learned ORDER BY created_at DESC LIMIT ?", (limit,))]


def undo(c, lid: int) -> bool:
    """آموخته را برمی‌گرداند: نیت ساخته‌شده از دانش مشترک پاک می‌شود."""
    x = c.execute("SELECT * FROM learned WHERE id=?", (lid,)).fetchone()
    if not x or x["status"] != "learned":
        return False
    for it in shared_kb.intents():
        if not it["builtin"] and x["question"] in it["examples"] and it["answer"].strip() == x["answer"]:
            shared_kb.delete_intent(it["id"])
            break
    c.execute("UPDATE learned SET status='undone' WHERE id=?", (lid,))
    return True


def stats(c) -> dict:
    q = lambda sql: c.execute(sql).fetchone()[0]  # noqa: E731
    return {"up": q("SELECT COUNT(*) FROM ai_log WHERE customer_vote='up'"),
            "down": q("SELECT COUNT(*) FROM ai_log WHERE customer_vote='down'"),
            "learned": q("SELECT COUNT(*) FROM learned WHERE status='learned'")}
