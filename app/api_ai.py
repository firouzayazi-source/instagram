"""API پاسخ هوشمند و پایگاه دانش. همه‌ی مسیرها نشست می‌خواهند."""
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from . import ai, auth, config, db, knowledge, secrets_env, shared_kb, site_sync

router = APIRouter(prefix="/api/ai", dependencies=[Depends(auth.require_session)])


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except ValueError as e:
        raise HTTPException(422, str(e))


# ---------- تنظیمات و آمار ----------

@router.get("/settings")
def get_settings():
    with db.connect() as c:
        st = ai.settings(c)
        return {"settings": st, "providers": ai.providers_info(), "intents": ai.INTENT_FA,
                "has_key": ai.has_key(st["provider"])}


@router.put("/settings")
def put_settings(body: dict):
    with db.connect() as c:
        return {"settings": _guard(ai.save_settings, c, body)}


@router.get("/stats")
def get_stats():
    with db.connect() as c:
        return ai.stats(c)


class TestIn(BaseModel):
    channel: str = "dm"
    text: str


@router.post("/test")
async def test(body: TestIn):
    """پاسخ ربات را بدون ارسال نشان می‌دهد. هزینه‌ی API دارد."""
    if body.channel not in ("comment", "dm") or not body.text.strip():
        raise HTTPException(422, "کانال یا متن نامعتبر")
    with db.connect() as c:
        d = await ai.decide(c, channel=body.channel, text=body.text.strip(), user_id="test", username="test", is_test=True)
        cost = c.execute("SELECT cost FROM ai_log WHERE id=?", (d.log_id,)).fetchone()
        err = c.execute("SELECT error FROM ai_log WHERE id=?", (d.log_id,)).fetchone()
    return {"action": d.action, "reply": d.reply, "public_reply": d.public_reply, "intent": d.intent,
            "confidence": d.confidence, "handoff_reason": d.handoff_reason, "skip_reason": d.skip_reason,
            "cost": cost[0] if cost else 0, "error": err[0] if err else None}


# ---------- پرسش‌های رایج ----------

class FaqIn(BaseModel):
    question: str
    keywords: str = ""
    answer: str
    enabled: bool = True


@router.get("/faq")
def faq_list():
    with db.connect() as c:
        return knowledge.list_faq(c)


@router.post("/faq")
def faq_create(body: FaqIn):
    with db.connect() as c:
        return {"id": _guard(knowledge.save_faq, c, body.model_dump())}


@router.put("/faq/{fid}")
def faq_update(fid: int, body: FaqIn):
    with db.connect() as c:
        return {"id": _guard(knowledge.save_faq, c, {**body.model_dump(), "id": fid})}


@router.delete("/faq/{fid}")
def faq_delete(fid: int):
    with db.connect() as c:
        knowledge.delete_faq(c, fid)
    return {"ok": True}


# ---------- فایل‌ها ----------

@router.get("/docs")
def docs_list():
    with db.connect() as c:
        return knowledge.list_docs(c)


@router.post("/docs")
async def docs_upload(request: Request, name: str = Query(..., min_length=1, max_length=200)):
    """بدنه‌ی درخواست خود فایل است (نه فرم)."""
    data = await request.body()
    if not data:
        raise HTTPException(422, "فایل خالی است")
    with db.connect() as c:
        return _guard(knowledge.add_doc, c, name, data)


@router.get("/docs/{did}")
def docs_preview(did: int):
    with db.connect() as c:
        return {"preview": knowledge.doc_preview(c, did)}


@router.post("/docs/{did}/enable")
def docs_enable(did: int, body: dict):
    with db.connect() as c:
        knowledge.set_doc_enabled(c, did, bool(body.get("enabled")))
    return {"ok": True}


@router.delete("/docs/{did}")
def docs_delete(did: int):
    with db.connect() as c:
        knowledge.delete_doc(c, did)
    return {"ok": True}


# ---------- محصولات ----------

class ProductIn(BaseModel):
    name: str
    storage: str = ""
    color: str = ""
    condition: str = "new"
    price: int | str | None = None
    in_stock: bool = True
    notes: str = ""
    enabled: bool = True


@router.get("/products")
def products_list():
    with db.connect() as c:
        return knowledge.list_products(c)


@router.post("/products")
def products_create(body: ProductIn):
    with db.connect() as c:
        return {"id": _guard(knowledge.save_product, c, body.model_dump())}


@router.put("/products/{pid}")
def products_update(pid: int, body: ProductIn):
    with db.connect() as c:
        return {"id": _guard(knowledge.save_product, c, {**body.model_dump(), "id": pid})}


@router.delete("/products/{pid}")
def products_delete(pid: int):
    with db.connect() as c:
        knowledge.delete_product(c, pid)
    return {"ok": True}


class ImportIn(BaseModel):
    text: str
    replace: bool = False


@router.post("/products/import")
def products_import(body: ImportIn):
    with db.connect() as c:
        return {"imported": _guard(knowledge.import_products, c, body.text, body.replace)}


# ---------- همگام‌سازی با سایت ----------

def _sync_view(st: dict) -> dict:
    return {**st, "has_wc_key": bool(config.WC_CONSUMER_KEY and config.WC_CONSUMER_SECRET)}


@router.get("/site-sync")
def site_sync_get():
    with db.connect() as c:
        return _sync_view(site_sync.get_settings(c))


@router.put("/site-sync")
def site_sync_put(body: dict):
    with db.connect() as c:
        return _sync_view(_guard(site_sync.save_settings, c, body))


@router.post("/site-sync/run")
async def site_sync_run():
    """همگام‌سازی همین الان. خطای خواندن سایت در last_error برمی‌گردد، نه به صورت خطای HTTP."""
    with db.connect() as c:
        try:
            st = await site_sync.sync(c)
        except ValueError as e:
            raise HTTPException(422, str(e))
        return _sync_view(st)


# ---------- لاگ و بازخورد ----------

_LOG_FILTERS = {
    "all": "1", "reply": "action='reply'", "handoff": "action='handoff'",
    "ignore": "action IN ('ignore','skip')", "error": "action='error' OR status='failed'", "bad": "feedback='bad'",
    "test": "is_test=1",
}


@router.get("/log")
def log_list(filter: str = "all", limit: int = Query(50, le=200), before: float | None = None):
    where = f"({_LOG_FILTERS.get(filter, '1')})"
    if filter != "test":
        where += " AND is_test=0"
    args: list = []
    if before:
        where += " AND created_at<?"
        args.append(before)
    with db.connect() as c:
        return [dict(r) for r in c.execute(
            f"SELECT * FROM ai_log WHERE {where} ORDER BY created_at DESC LIMIT ?", [*args, limit])]


class FeedbackIn(BaseModel):
    feedback: str                      # good | bad | ""
    correct_answer: str = ""           # اگر پر شود، به پرسش‌های رایج اضافه می‌شود
    keywords: str = ""


@router.post("/log/{lid}/feedback")
def log_feedback(lid: int, body: FeedbackIn):
    if body.feedback not in ("good", "bad", ""):
        raise HTTPException(422, "بازخورد نامعتبر")
    with db.connect() as c:
        row = c.execute("SELECT input FROM ai_log WHERE id=?", (lid,)).fetchone()
        if not row:
            raise HTTPException(404)
        c.execute("UPDATE ai_log SET feedback=? WHERE id=?", (body.feedback or None, lid))
        faq_id, shared = None, False
        if body.correct_answer.strip():
            if shared_kb.ready():
                # دانش مشترک: از این به بعد هم اینستاگرام و هم تلگرام همین را جواب می‌دهند
                _guard(shared_kb.save_intent, {"keys": body.keywords, "examples": [row["input"][:300]],
                                               "answer": body.correct_answer.strip()})
                shared = True
            else:
                faq_id = knowledge.save_faq(c, {"question": row["input"][:300], "keywords": body.keywords,
                                                "answer": body.correct_answer})
    return {"ok": True, "faq_id": faq_id, "shared": shared}


# ---------- دانش مشترک اینستاگرام و تلگرام ----------

@router.get("/kb")
def kb_get():
    with db.connect() as c:
        old = len(knowledge.list_faq(c))
    return {"ready": shared_kb.ready(), "intents": shared_kb.intents() if shared_kb.ready() else [],
            "sections": shared_kb.sections(), "actions": shared_kb.ACTIONS, "pending": shared_kb.pending(),
            "old_faq": old}


@router.post("/kb/intents")
def kb_intent_save(body: dict):
    _guard(shared_kb.save_intent, body)
    return {"queued": True}


@router.delete("/kb/intents/{iid}")
def kb_intent_delete(iid: str):
    _guard(shared_kb.delete_intent, iid)
    return {"queued": True}


@router.put("/kb/sections/{key}")
def kb_section_save(key: str, body: dict):
    _guard(shared_kb.save_section, key, body.get("text", ""))
    return {"queued": True}


@router.post("/kb/migrate-faq")
def kb_migrate_faq():
    """پرسش‌های رایج قدیمی (فقط اینستاگرام) به دانش مشترک می‌روند و از جدول قدیمی پاک می‌شوند."""
    with db.connect() as c:
        moved = 0
        for f in knowledge.list_faq(c):
            _guard(shared_kb.save_intent, {"keys": f["keywords"], "examples": [f["question"]], "answer": f["answer"],
                                           "enabled": bool(f["enabled"])})
            knowledge.delete_faq(c, f["id"])
            moved += 1
    return {"moved": moved}


# ---------- ارجاع به انسان ----------

@router.get("/handoffs")
def handoffs_list(status: str = "open"):
    where = "status=?" if status in ("open", "done") else "1"
    args = (status,) if status in ("open", "done") else ()
    with db.connect() as c:
        return [dict(r) for r in c.execute(
            f"SELECT h.*, l.reply AS bot_reply FROM handoffs h LEFT JOIN ai_log l ON l.id=h.ai_log_id "
            f"WHERE {where.replace('status', 'h.status')} ORDER BY h.created_at DESC LIMIT 200", args)]


@router.post("/handoffs/{hid}/resolve")
def handoff_resolve(hid: int, body: dict | None = None):
    done = (body or {}).get("done", True)
    with db.connect() as c:
        c.execute("UPDATE handoffs SET status=?, resolved_at=? WHERE id=?",
                  ("done" if done else "open", time.time() if done else None, hid))
    return {"ok": True}


# ---------- کاربران مسدود ----------

class BlockIn(BaseModel):
    user_id: str
    username: str | None = None
    reason: str = ""


@router.get("/blocked")
def blocked_list():
    with db.connect() as c:
        return knowledge.list_blocked(c)


@router.post("/blocked")
def blocked_add(body: BlockIn):
    if not body.user_id.strip():
        raise HTTPException(422, "شناسه‌ی کاربر لازم است")
    with db.connect() as c:
        knowledge.block(c, body.user_id.strip(), body.username, body.reason)
    return {"ok": True}


@router.delete("/blocked/{user_id}")
def blocked_remove(user_id: str):
    with db.connect() as c:
        knowledge.unblock(c, user_id)
    return {"ok": True}


# ---------- کلید سرویس‌های هوش مصنوعی (در ‎.env‎ سرور؛ هرگز برگردانده نمی‌شود) ----------

@router.get("/keys")
def keys_get():
    return {"items": secrets_env.status()}


@router.put("/keys/{name}")
def keys_put(name: str, body: dict):
    try:
        items = secrets_env.set_value(name, str(body.get("value") or ""))
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"items": items, "providers": ai.providers_info()}
