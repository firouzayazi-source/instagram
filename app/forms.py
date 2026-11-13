"""فرم‌ساز دایرکت: چند سؤال پشت‌سرهم در دایرکت (نام، شماره، مدل گوشی…) و ذخیره‌ی جواب‌ها.

فرم را یک دستور پاسخ هوشمند شروع می‌کند (actions.form_id): بعد از پیام همان دستور، سؤال اول فرستاده
می‌شود و هر پیام بعدی آن نفر جواب سؤال جاری حساب می‌شود تا فرم تمام شود. «لغو» فرم را می‌بندد.
فرم نیمه‌کاره بعد از SESSION_TTL رها می‌شود. جواب‌ها فقط در پایگاه داده‌ی سرور می‌مانند؛ خبر تلگرام
فقط نام فرم را می‌گوید، نه اطلاعات مشتری.
"""
import json
import re
import time

from .normalize import normalize

SCHEMA = """
CREATE TABLE IF NOT EXISTS forms (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  questions TEXT NOT NULL DEFAULT '[]',
  done_text TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS form_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  form_id INTEGER NOT NULL,
  user_id TEXT NOT NULL,
  username TEXT NOT NULL DEFAULT '',
  answers TEXT NOT NULL DEFAULT '[]',
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_form_entries ON form_entries(form_id, created_at);
CREATE TABLE IF NOT EXISTS form_sessions (
  user_id TEXT PRIMARY KEY,
  form_id INTEGER NOT NULL,
  step INTEGER NOT NULL DEFAULT 0,
  answers TEXT NOT NULL DEFAULT '[]',
  updated_at REAL NOT NULL
);
"""
KINDS = {"text": "متن", "phone": "شماره موبایل", "number": "عدد", "choice": "گزینه‌ای"}
SESSION_TTL = 24 * 3600          # پنجره‌ی پیام اینستاگرام هم ۲۴ ساعت است
CANCEL = {"لغو", "انصراف", "بیخیال", "cancel"}
MAX_QUESTIONS = 10
_PHONE = re.compile(r"^(?:\+?98|0)?(9\d{9})$")


def ensure(c) -> None:
    c.executescript(SCHEMA)


def _clean_questions(qs) -> list[dict]:
    out = []
    for q in (qs or [])[:MAX_QUESTIONS]:
        label = str((q or {}).get("label", "")).strip()[:300]
        kind = q.get("kind") if q.get("kind") in KINDS else "text"
        if not label:
            continue
        item = {"label": label, "kind": kind}
        if kind == "choice":
            opts = [str(o).strip()[:20] for o in q.get("options") or [] if str(o).strip()][:13]
            if len(opts) < 2:
                raise ValueError(f"سؤال «{label[:30]}» دست‌کم دو گزینه لازم دارد")
            item["options"] = opts
        out.append(item)
    return out


def save(c, data: dict, form_id: int | None = None) -> int:
    ensure(c)
    name = str(data.get("name", "")).strip()[:80]
    if not name:
        raise ValueError("نام فرم لازم است")
    qs = _clean_questions(data.get("questions"))
    if not qs:
        raise ValueError("دست‌کم یک سؤال لازم است")
    vals = (name, int(bool(data.get("enabled", True))), json.dumps(qs, ensure_ascii=False),
            str(data.get("done_text", "")).strip()[:1000])
    if form_id:
        if not c.execute("UPDATE forms SET name=?, enabled=?, questions=?, done_text=? WHERE id=?", (*vals, form_id)).rowcount:
            raise LookupError("فرم پیدا نشد")
        return form_id
    return c.execute("INSERT INTO forms(name,enabled,questions,done_text,created_at) VALUES (?,?,?,?,?)",
                     (*vals, time.time())).lastrowid


def _row(r) -> dict:
    d = dict(r)
    d["questions"] = json.loads(d["questions"])
    d["enabled"] = bool(d["enabled"])
    return d


def get(c, form_id) -> dict | None:
    ensure(c)
    r = c.execute("SELECT * FROM forms WHERE id=?", (form_id,)).fetchone()
    return _row(r) if r else None


def listing(c) -> list[dict]:
    ensure(c)
    out = []
    for r in c.execute("SELECT * FROM forms ORDER BY id DESC"):
        d = _row(r)
        d["entries"] = c.execute("SELECT COUNT(*) FROM form_entries WHERE form_id=?", (d["id"],)).fetchone()[0]
        out.append(d)
    return out


def delete(c, form_id: int) -> None:
    ensure(c)
    c.execute("DELETE FROM forms WHERE id=?", (form_id,))
    c.execute("DELETE FROM form_sessions WHERE form_id=?", (form_id,))


def entries(c, form_id: int, since: float = 0, until: float = 0) -> list[dict]:
    ensure(c)
    rows = c.execute("SELECT * FROM form_entries WHERE form_id=? AND created_at>=? AND created_at<? ORDER BY id DESC LIMIT 2000",
                     (form_id, since, until or 1e18))
    return [{**dict(r), "answers": json.loads(r["answers"])} for r in rows]


def _ask(q: dict) -> tuple[str, list[str] | None]:
    return q["label"], (q.get("options") if q["kind"] == "choice" else None)


def start(c, form_id, user_id: str, now: float | None = None) -> tuple[str, list[str] | None] | None:
    """فرم را برای این نفر شروع می‌کند. خروجی: (سؤال اول، دکمه‌ها) یا None اگر فرم نیست یا خاموش است."""
    f = get(c, form_id)
    if not f or not f["enabled"] or not f["questions"]:
        return None
    c.execute("INSERT OR REPLACE INTO form_sessions(user_id,form_id,step,answers,updated_at) VALUES (?,?,0,'[]',?)",
              (user_id, f["id"], now or time.time()))
    return _ask(f["questions"][0])


def cancel(c, user_id: str) -> None:
    ensure(c)
    c.execute("DELETE FROM form_sessions WHERE user_id=?", (user_id,))


def active(c, user_id: str, now: float | None = None) -> bool:
    ensure(c)
    r = c.execute("SELECT updated_at FROM form_sessions WHERE user_id=?", (user_id,)).fetchone()
    return bool(r) and (now or time.time()) - r[0] < SESSION_TTL


def _check(q: dict, text: str) -> tuple[str | None, str]:
    """(مقدار درست، پیام خطا)"""
    t = text.strip()
    if q["kind"] == "phone":
        m = _PHONE.match(normalize(t).replace(" ", "").replace("-", ""))
        return ("0" + m.group(1), "") if m else (None, "شماره‌ی موبایل درست نیست؛ مثلاً ۰۹۱۲۱۲۳۴۵۶۷ بنویسید 🙏")
    if q["kind"] == "number":
        n = normalize(t).replace(",", "").replace("٬", "").replace(" ", "")
        return (n, "") if n.isdigit() else (None, "لطفاً فقط عدد بنویسید 🙏")
    if q["kind"] == "choice":
        for o in q["options"]:
            if normalize(o) == normalize(t):
                return o, ""
        return None, "لطفاً یکی از دکمه‌ها را بزنید 🙏"
    return (t[:500], "") if t else (None, "لطفاً جواب را بنویسید 🙏")


def answer(c, user_id: str, username: str, text: str, now: float | None = None) -> dict | None:
    """جواب سؤال جاری. None اگر فرمی در جریان نیست. خروجی:
    {"text": پیام بعدی، "quick_replies": دکمه‌ها یا None، "done": شماره‌ی ثبت یا None، "phone": شماره‌ی ثبت‌شده}"""
    now = now or time.time()
    if not active(c, user_id, now):
        c.execute("DELETE FROM form_sessions WHERE user_id=?", (user_id,))
        return None
    s = c.execute("SELECT * FROM form_sessions WHERE user_id=?", (user_id,)).fetchone()
    f = get(c, s["form_id"])
    if not f or not f["enabled"] or s["step"] >= len(f["questions"]):
        c.execute("DELETE FROM form_sessions WHERE user_id=?", (user_id,))
        return None
    if normalize(text.strip()) in {normalize(x) for x in CANCEL}:
        c.execute("DELETE FROM form_sessions WHERE user_id=?", (user_id,))
        return {"text": "باشه، فرم بسته شد. هر سؤالی داشتید بپرسید 🌸", "quick_replies": None, "done": None, "phone": ""}
    q = f["questions"][s["step"]]
    value, err = _check(q, text)
    if value is None:
        t, qr = _ask(q)
        return {"text": f"{err}\n\n{t}", "quick_replies": qr, "done": None, "phone": ""}
    answers = json.loads(s["answers"]) + [{"label": q["label"], "kind": q["kind"], "value": value}]
    step = s["step"] + 1
    if step < len(f["questions"]):
        c.execute("UPDATE form_sessions SET step=?, answers=?, updated_at=? WHERE user_id=?",
                  (step, json.dumps(answers, ensure_ascii=False), now, user_id))
        t, qr = _ask(f["questions"][step])
        return {"text": t, "quick_replies": qr, "done": None, "phone": ""}
    c.execute("DELETE FROM form_sessions WHERE user_id=?", (user_id,))
    eid = c.execute("INSERT INTO form_entries(form_id,user_id,username,answers,created_at) VALUES (?,?,?,?,?)",
                    (f["id"], user_id, username or "", json.dumps(answers, ensure_ascii=False), now)).lastrowid
    phone = next((a["value"] for a in answers if a["kind"] == "phone"), "")
    return {"text": f["done_text"] or "ممنون 🌸 اطلاعاتتون ثبت شد؛ همکارانمون به‌زودی تماس می‌گیرن.",
            "quick_replies": None, "done": eid, "phone": phone, "form": f["name"]}
