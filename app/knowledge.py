"""پایگاه دانش: پرسش‌های رایج، فایل‌های کاتالوگ، محصولات، کاربران مسدود، و بازیابی متن مرتبط."""
import csv
import io
import re
import time
import zipfile
from xml.etree import ElementTree

from .normalize import normalize

MAX_UPLOAD = 10 * 1024 * 1024
CHUNK_CHARS = 1000
CONDITIONS = {"new": "نو", "used": "کارکرده", "stock": "استوک"}
_STOP = set("و در به از که این را با برای یا هم تا آن یک است هست می ها های رو چی چه چند چنده سلام لطفا ممنون مرسی".split())
_WORD = re.compile(r"[\w؀-ۿ]+")


# ---------- استخراج متن ----------

def extract_text(name: str, data: bytes) -> str:
    """متن فایل TXT، DOCX یا PDF. ValueError برای فرمت ناشناخته یا فایل خراب."""
    if len(data) > MAX_UPLOAD:
        raise ValueError("حجم فایل بیشتر از ۱۰ مگابایت است")
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if ext in ("txt", "md", "csv"):
        for enc in ("utf-8-sig", "utf-16", "cp1256"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        raise ValueError("رمزگذاری فایل متنی شناخته نشد")
    if ext == "docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                xml = z.read("word/document.xml")
        except (zipfile.BadZipFile, KeyError):
            raise ValueError("فایل Word خراب است")
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        root = ElementTree.fromstring(xml)
        paras = ["".join(t.text or "" for t in p.iter(f"{ns}t")) for p in root.iter(f"{ns}p")]
        return "\n".join(p for p in paras if p.strip())
    if ext == "pdf":
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:  # noqa: BLE001
            raise ValueError("فایل PDF خوانده نشد")
    raise ValueError("فقط فایل PDF، DOCX یا TXT پذیرفته می‌شود")


def chunk(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """تقسیم روی مرز پاراگراف؛ پاراگراف خیلی بلند از وسط شکسته می‌شود."""
    out, cur = [], ""
    for para in (p.strip() for p in re.split(r"\n\s*\n|\n", text)):
        if not para:
            continue
        while len(para) > size:
            if cur:
                out.append(cur)
                cur = ""
            out.append(para[:size])
            para = para[size:]
        if len(cur) + len(para) + 1 > size:
            out.append(cur)
            cur = para
        else:
            cur = f"{cur}\n{para}" if cur else para
    if cur:
        out.append(cur)
    return out


# ---------- بازیابی ----------

def tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall(normalize(text)) if len(w) > 1 and w not in _STOP}


def score(query_tokens: set[str], text: str) -> int:
    if not query_tokens:
        return 0
    t = normalize(text)
    return sum(1 for q in query_tokens if q in t)


def relevant_chunks(c, query: str, limit: int = 4, max_chars: int = 4000) -> list[dict]:
    q = tokens(query)
    if not q:
        return []
    rows = c.execute(
        "SELECT ch.text, d.name FROM doc_chunks ch JOIN docs d ON d.id=ch.doc_id WHERE d.enabled=1"
    ).fetchall()
    scored = sorted(((score(q, r["text"]), r["name"], r["text"]) for r in rows), reverse=True)
    out, total = [], 0
    for s, name, text in scored:
        if s == 0 or len(out) >= limit or total + len(text) > max_chars:
            break
        out.append({"source": name, "text": text})
        total += len(text)
    return out


def matching_faq_ids(c, query: str) -> list[int]:
    """پرسش‌هایی که کلمات کلیدی‌شان در پیام آمده؛ برای شمارش استفاده."""
    t = normalize(query)
    ids = []
    for r in c.execute("SELECT id, keywords FROM faq WHERE enabled=1"):
        kws = [normalize(k) for k in re.split(r"[,،\n]", r["keywords"]) if k.strip()]
        if any(k and k in t for k in kws):
            ids.append(r["id"])
    return ids


# ---------- پرسش‌های رایج ----------

def list_faq(c) -> list[dict]:
    return [dict(r) for r in c.execute("SELECT * FROM faq ORDER BY id DESC")]


def save_faq(c, item: dict) -> int:
    q, a = (item.get("question") or "").strip(), (item.get("answer") or "").strip()
    if not q or not a:
        raise ValueError("پرسش و پاسخ هر دو لازم است")
    vals = (q, (item.get("keywords") or "").strip(), a, int(item.get("enabled", True)), time.time())
    if item.get("id"):
        c.execute("UPDATE faq SET question=?, keywords=?, answer=?, enabled=?, updated_at=? WHERE id=?", (*vals, item["id"]))
        return item["id"]
    return c.execute("INSERT INTO faq(question,keywords,answer,enabled,updated_at) VALUES (?,?,?,?,?)", vals).lastrowid


def delete_faq(c, fid: int) -> None:
    c.execute("DELETE FROM faq WHERE id=?", (fid,))


# ---------- فایل‌ها ----------

def add_doc(c, name: str, data: bytes) -> dict:
    text = extract_text(name, data).strip()
    if len(text) < 20:
        raise ValueError("متنی در فایل پیدا نشد (اگر PDF اسکن‌شده است، متن قابل استخراج ندارد)")
    parts = chunk(text)
    did = c.execute("INSERT INTO docs(name,chars,created_at) VALUES (?,?,?)", (name, len(text), time.time())).lastrowid
    c.executemany("INSERT INTO doc_chunks(doc_id,idx,text) VALUES (?,?,?)", [(did, i, p) for i, p in enumerate(parts)])
    return {"id": did, "name": name, "chars": len(text), "chunks": len(parts)}


def list_docs(c) -> list[dict]:
    return [dict(r) for r in c.execute(
        "SELECT d.*, (SELECT COUNT(*) FROM doc_chunks WHERE doc_id=d.id) AS chunks FROM docs d ORDER BY id DESC")]


def doc_preview(c, did: int, limit: int = 1500) -> str:
    rows = c.execute("SELECT text FROM doc_chunks WHERE doc_id=? ORDER BY idx", (did,)).fetchall()
    return "\n\n".join(r[0] for r in rows)[:limit]


def set_doc_enabled(c, did: int, enabled: bool) -> None:
    c.execute("UPDATE docs SET enabled=? WHERE id=?", (int(enabled), did))


def delete_doc(c, did: int) -> None:
    c.execute("DELETE FROM doc_chunks WHERE doc_id=?", (did,))
    c.execute("DELETE FROM docs WHERE id=?", (did,))


# ---------- محصولات ----------

_PRODUCT_FIELDS = ("name", "storage", "color", "condition", "price", "in_stock", "notes", "enabled")


def _clean_price(v) -> int | None:
    if v in (None, ""):
        return None
    digits = re.sub(r"[^\d]", "", normalize(str(v)))
    return int(digits) if digits else None


def _clean_condition(v) -> str:
    v = normalize(str(v or ""))
    for key, fa in CONDITIONS.items():
        if v in (key, normalize(fa)):
            return key
    return "new"


def _clean_bool(v, default=True) -> int:
    if v in (None, ""):
        return int(default)
    return 0 if normalize(str(v)) in ("0", "false", "no", "خیر", "ناموجود", "نه") else 1


def list_products(c) -> list[dict]:
    return [dict(r) for r in c.execute("SELECT * FROM products ORDER BY name, storage, condition, id")]


def save_product(c, p: dict) -> int:
    name = (p.get("name") or "").strip()
    if not name:
        raise ValueError("نام محصول لازم است")
    vals = (name, (p.get("storage") or "").strip(), (p.get("color") or "").strip(), _clean_condition(p.get("condition")),
            _clean_price(p.get("price")), _clean_bool(p.get("in_stock")), (p.get("notes") or "").strip(),
            _clean_bool(p.get("enabled")), time.time())
    if p.get("id"):
        c.execute("UPDATE products SET name=?, storage=?, color=?, condition=?, price=?, in_stock=?, notes=?, enabled=?, "
                  "updated_at=? WHERE id=?", (*vals, p["id"]))
        return p["id"]
    return c.execute("INSERT INTO products(name,storage,color,condition,price,in_stock,notes,enabled,updated_at) "
                     "VALUES (?,?,?,?,?,?,?,?,?)", vals).lastrowid


def delete_product(c, pid: int) -> None:
    c.execute("DELETE FROM products WHERE id=?", (pid,))


def import_products(c, text: str, replace: bool = False) -> int:
    """متن جدولی (CSV یا کپی از اکسل) با ستون‌های: نام، حافظه، رنگ، وضعیت، قیمت، موجودی، توضیح.
    سطر اول اگر عنوان ستون باشد نادیده گرفته می‌شود."""
    text = text.strip()
    if not text:
        raise ValueError("متنی برای وارد کردن نیست")
    delim = "\t" if "\t" in text.splitlines()[0] else ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(x.strip() for x in r)]
    if rows and normalize(rows[0][0]) in ("name", "نام", "مدل", "محصول"):
        rows = rows[1:]
    if replace:
        c.execute("DELETE FROM products WHERE source=''")  # محصولات همگام‌شده از سایت دست نمی‌خورند
    n = 0
    for r in rows:
        r = (r + [""] * 7)[:7]
        save_product(c, dict(zip(("name", "storage", "color", "condition", "price", "in_stock", "notes"), r)))
        n += 1
    return n


def products_text(c, limit: int = 400, out_of_stock: int = 50) -> str:
    # موجودها اول؛ از ناموجودها (مثلاً گوشی‌های فروخته‌شده‌ی سایت) فقط تازه‌ترین‌ها
    rows = c.execute("SELECT * FROM products WHERE enabled=1 AND in_stock=1 ORDER BY name, storage, condition").fetchall()
    rows += c.execute("SELECT * FROM products WHERE enabled=1 AND in_stock=0 ORDER BY updated_at DESC, id DESC LIMIT ?",
                      (out_of_stock,)).fetchall()
    total = c.execute("SELECT COUNT(*) FROM products WHERE enabled=1").fetchone()[0]
    lines = []
    for r in rows[:limit]:
        price = f"{r['price']:,} تومان" if r["price"] else "قیمت: استعلام"
        parts = [r["name"], r["storage"], r["color"], CONDITIONS.get(r["condition"], r["condition"]), price,
                 "موجود" if r["in_stock"] else "ناموجود", r["notes"], r["url"]]
        lines.append(" | ".join(p for p in parts if p))
    if total > len(lines):
        lines.append(f"(و {total - len(lines)} مورد دیگر که اینجا نیامده؛ اگر مشتری محصولی خواست که در این فهرست نیست، ارجاع بده)")
    return "\n".join(lines)


def faq_text(c) -> str:
    rows = c.execute("SELECT question, answer FROM faq WHERE enabled=1 ORDER BY id").fetchall()
    return "\n\n".join(f"پرسش: {r['question']}\nپاسخ: {r['answer']}" for r in rows)


# ---------- کاربران مسدود ----------

def is_blocked(c, user_id: str) -> bool:
    return c.execute("SELECT 1 FROM blocked_users WHERE user_id=?", (user_id,)).fetchone() is not None


def block(c, user_id: str, username: str | None = None, reason: str = "") -> None:
    c.execute("INSERT OR REPLACE INTO blocked_users(user_id,username,reason,created_at) VALUES (?,?,?,?)",
              (user_id, username, reason, time.time()))


def unblock(c, user_id: str) -> None:
    c.execute("DELETE FROM blocked_users WHERE user_id=?", (user_id,))


def list_blocked(c) -> list[dict]:
    return [dict(r) for r in c.execute("SELECT * FROM blocked_users ORDER BY created_at DESC")]
