import os, re, json, time, random, asyncio, logging, aiosqlite, jdatetime, pytz, zipfile, io, html, secrets, traceback, hashlib
from datetime import datetime, timedelta
import aiofiles
import brain       # موتور فهم پیام — بدون هیچ API بیرونی
import profanity   # تشخیص فحش و توهین
from telegram import (Update, ReplyKeyboardMarkup, InlineKeyboardMarkup,
                      InlineKeyboardButton, BotCommand, WebAppInfo)
from telegram.error import Forbidden, BadRequest, Conflict
from telegram.ext import (ApplicationBuilder, ApplicationHandlerStop, CommandHandler,
                           MessageHandler, CallbackQueryHandler, ContextTypes, filters)

os.environ.pop("HTTP_PROXY", None); os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("ALL_PROXY", None); os.environ["NO_PROXY"] = "*"

def _env(name):
    v = (os.environ.get(name) or "").strip()
    if not v:
        raise SystemExit(
            f"❌ متغیر محیطی {name} تنظیم نشده است.\n"
            f"   فایل .env کنار bot.py را بسازید و مقداردهی کنید:\n"
            f"       BOT_TOKEN=...\n"
            f"       ADMIN_ID=...\n"
            f"   (در systemd باید EnvironmentFile=/opt/telegram-bot/.env باشد)")
    return v

TOKEN = _env("BOT_TOKEN")
# ADMIN_ID می‌تواند یک آیدی باشد یا چند آیدی جداشده با کاما.
# اولین آیدی «مالک» است: تنها کسی که مدیر اضافه/کم می‌کند و بک‌آپ را
# بازمی‌گرداند. بقیه فقط به پنل دسترسی دارند.
try:
    _ADMIN_ENV = [int(x) for x in re.split(r"[,\s]+", _env("ADMIN_ID").strip()) if x]
except ValueError:
    raise SystemExit("❌ ADMIN_ID باید عدد باشد (آیدی عددی تلگرام، نه یوزرنیم).\n"
                     "   برای چند مدیر با کاما جدا کنید:  ADMIN_ID=11111111,22222222")
if not _ADMIN_ENV:
    raise SystemExit("❌ ADMIN_ID خالی است.")
OWNER_ID = _ADMIN_ENV[0]     # مالک — مقصد بک‌آپ و گزارش خطا
_admins: set = set(_ADMIN_ENV)
_admins_extra: list = []     # مدیرهای افزوده‌شده از پنل (admins.json)

def is_admin(uid) -> bool: return uid in _admins
def is_owner(uid) -> bool: return uid == OWNER_ID
def admin_ids() -> list:
    """مالک همیشه اول فهرست."""
    return sorted(_admins, key=lambda x: (x != OWNER_ID, x))
DATA_FILE = "data.json"; DB_FILE = "users.db"; BANNER_FILE = "banner.json"
WORKHOURS_FILE = "workhours.json"; BUTTONS_FILE = "buttons.json"
MENU_FILE = "menu.json"; BACKUPS_FILE = "backups.json"; PLACES_FILE = "places.json"
SETTINGS_FILE = "settings.json"; STATS_FILE = "stats.json"
ADMINS_FILE = "admins.json"; BROADCAST_FILE = "broadcast.json"
FAQ_FILE = "faq.json"; UNMATCHED_FILE = "unmatched.json"
PAGES_FILE = "pages.json"; TOPICS_FILE = "topics.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ── محافظت از توکن در لاگ‌ها
# httpx هر درخواست را در سطح INFO لاگ می‌کند و توکن داخلِ خودِ URL است:
#   "HTTP Request: POST https://api.telegram.org/bot<TOKEN>/getMe"
# یعنی توکن با متن ساده در journalctl می‌نشست و با هر کپی‌کردن لاگ بیرون
# می‌رفت. هرکس آن رشته را داشته باشد کنترل کامل ربات را دارد.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Application").setLevel(logging.INFO)

class _RedactToken(logging.Filter):
    """تور ایمنی: اگر توکن از هر مسیر دیگری (خطا، traceback، کتابخانه‌ی
    ناشناس) به لاگ راه پیدا کرد، جایش ‹توکن› نوشته می‌شود."""
    def filter(self, record):
        try:
            msg = record.getMessage()
            if TOKEN and TOKEN in msg:
                record.msg = msg.replace(TOKEN, "‹توکن پنهان شد›"); record.args = ()
        except Exception:
            pass
        return True

for _h in logging.getLogger().handlers:
    _h.addFilter(_RedactToken())

logger = logging.getLogger(__name__)
IRAN_TZ = pytz.timezone("Asia/Tehran")

# ── زمان
_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
# ارقام فارسی/عربی → انگلیسی (کاربر ممکن است شماره را با کیبورد فارسی بنویسد)
FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
MONTH_FA = {1:"فروردین",2:"اردیبهشت",3:"خرداد",4:"تیر",5:"مرداد",6:"شهریور",
            7:"مهر",8:"آبان",9:"آذر",10:"دی",11:"بهمن",12:"اسفند"}
DAY_FA   = {"0":"شنبه","1":"یکشنبه","2":"دوشنبه","3":"سه‌شنبه",
            "4":"چهارشنبه","5":"پنجشنبه","6":"جمعه"}

def to_fa(v): return str(v).translate(_FA)

def shamsi_now():
    now = datetime.now(IRAN_TZ); j = jdatetime.datetime.fromgregorian(datetime=now)
    return f"{to_fa(j.day)} {MONTH_FA[j.month]} {to_fa(j.year)} — {to_fa(now.strftime('%H:%M'))}"

def gregorian_now(): return datetime.now(IRAN_TZ).strftime("%Y-%m-%d %H:%M:%S")

# ── منو
MENU_ITEMS = {"1":"🌐 شبکه‌های اجتماعی","2":"🌐 سایت استوک لند",
              "3":"💰 شرایط اقساط","4":"📞 پشتیبانی","5":"📍 آدرس فروشگاه",
              "6":"🔖 دکمه ذخیره ۱","7":"🔖 دکمه ذخیره ۲"}
# پیکربندی منوی اصلی — قابل تغییر از پنل ادمین (menu.json)
# هر آیتم: key (ثابت), label (قابل تغییر), order (ترتیب), enabled (روشن/خاموش)
DEFAULT_MENU = [
    {"key":"1","label":"🌐 شبکه‌های اجتماعی","order":1,"enabled":True,"width":"half"},
    {"key":"2","label":"🌐 سایت استوک لند","order":2,"enabled":True,"width":"half"},
    {"key":"3","label":"💰 شرایط اقساط","order":3,"enabled":True,"width":"half"},
    {"key":"5","label":"📍 آدرس فروشگاه","order":4,"enabled":True,"width":"half"},
    {"key":"workhours","label":"🕐 ساعت کاری","order":6,"enabled":True,"width":"half"},
    {"key":"4","label":"📞 پشتیبانی","order":7,"enabled":True,"width":"half"},
    {"key":"6","label":"🔖 دکمه ذخیره ۱","order":8,"enabled":False,"width":"half"},
    {"key":"7","label":"🔖 دکمه ذخیره ۲","order":9,"enabled":False,"width":"half"},
    {"key":"notify","label":"🔔 اطلاع‌رسانی","order":5,"enabled":True,"width":"half"},
]
menu_cfg = []

# بخش‌های پایه — همیشه هستند و حذف نمی‌شوند
BASE_SECTIONS = {"welcome":"🏠 خوش‌آمدگویی",
                 "workhours":"🕐 ساعت کاری",
                 "1":"🌐 شبکه‌های اجتماعی","2":"🌐 سایت استوک لند",
                 "3":"💰 شرایط اقساط","4":"📞 پشتیبانی","5":"📍 آدرس فروشگاه",
                 "6":"🔖 دکمه ذخیره ۱","7":"🔖 دکمه ذخیره ۲",
                 "notify":"🔔 اطلاع‌رسانی"}
# SECTION_NAMES = پایه + بخش‌های سفارشیِ ادمین (pages.json).
# عمداً همان dict می‌ماند تا همه‌ی کدهایی که SECTION_NAMES[key] یا
# «for k in SECTION_NAMES» می‌زنند بدون تغییر کار کنند.
SECTION_NAMES = dict(BASE_SECTIONS)
pages: list = []          # [{"key":"p_ab12cd34","title":"🛍 محصولات"}]

def is_custom(key): return str(key).startswith("p_")

# موضوع‌های اطلاع‌رسانی — کاربر خودش انتخاب می‌کند از چه چیزی خبردار شود.
# رضایت‌محور: بدون این، هر پیام همگانی برای همه می‌رود و آدم‌ها بلاک می‌کنند.
topics: list = []         # [{"id":"t_ab12","title":"🔔 لیست قیمت تازه"}]
def new_topic_id(): return "t_"+secrets.token_hex(3)
def topic_item(tid): return next((x for x in topics if x["id"]==tid),None)
def new_page_key(): return "p_"+secrets.token_hex(4)

# ── state
responses=None; banners={}; workhours={}; buttons={}; settings={}; stats={}; places={}

DEFAULT_WH = {"enabled":True,"schedule":{
    "0":{"open":True,"shifts":[{"from":"11:00","to":"14:00"},{"from":"17:00","to":"23:00"}]},
    "1":{"open":True,"shifts":[{"from":"11:00","to":"14:00"},{"from":"17:00","to":"23:00"}]},
    "2":{"open":True,"shifts":[{"from":"11:00","to":"14:00"},{"from":"17:00","to":"23:00"}]},
    "3":{"open":True,"shifts":[{"from":"11:00","to":"14:00"},{"from":"17:00","to":"23:00"}]},
    "4":{"open":True,"shifts":[{"from":"11:00","to":"14:00"},{"from":"17:00","to":"23:00"}]},
    "5":{"open":True,"shifts":[{"from":"11:00","to":"14:00"},{"from":"17:00","to":"23:00"}]},
    "6":{"open":True,"shifts":[{"from":"17:00","to":"23:00"}]}},
    "msg_open":"✅ هم‌اکنون باز است","msg_closed":"🔴 هم‌اکنون بسته است"}
DEFAULT_SETTINGS = {"notify_new_user":True,"store_open":True,"forward_user_msgs":True,
                    "faq_auto":True,        # پاسخ خودکار به سؤال‌های آماده
                    "faq_shortcut":True,    # میان‌بر #کلیدواژه هنگام پاسخ مدیر
                    "log_unmatched":True,   # ثبت سؤال‌هایی که جوابی نداشتند
                    "track_visits":True,    # حافظه‌ی رفتار مشتری (کارت شناخت)
                    "weekly_digest":True,   # خلاصه‌ی هفته کنار بکاپ جمعه
                    "miniapp":True,         # لینک سایت داخل تلگرام باز شود
                    "assistant":True,       # دستیار هوشمند (موتور داخلی، بدون API)
                    "typing_delay":True,    # «در حال نوشتن…» پیش از جواب
                    "ai_cc_admin":True,     # رونوشت پاسخ‌های دستیار برای مدیرها
                    "profanity_filter":True}  # تذکر به پیام توهین‌آمیز

# ── helpers
def get_banner(k): banners.setdefault(k,{"file_id":None,"active":False}); return banners[k]
def get_sec_btns(k): buttons.setdefault(k,{"enabled":True,"items":[]}); return buttons[k]
def get_place(k):
    places.setdefault(k,{"lat":None,"lon":None,"title":"","address":"","active":False})
    return places[k]
def get_setting(k): return settings.get(k,DEFAULT_SETTINGS.get(k,True))

HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

def valid_shift(sh):
    return bool(HHMM_RE.match(sh.get("from","")) and HHMM_RE.match(sh.get("to","")))

def in_shift(ns, sh):
    """آیا ساعت ns داخل شیفت است؟ شیفت‌های نیمه‌شب‌گذر (۲۲:۰۰ تا ۰۲:۰۰) هم پشتیبانی می‌شوند."""
    if not valid_shift(sh): return False
    f,t = sh["from"], sh["to"]
    if f <= t: return f <= ns <= t          # شیفت عادی
    return ns >= f or ns <= t                # از نیمه‌شب رد می‌شود

def is_open():
    if not get_setting("store_open"): return False
    if not workhours.get("enabled",True): return True
    now=datetime.now(IRAN_TZ); j=jdatetime.datetime.fromgregorian(datetime=now)
    ns=now.strftime("%H:%M")
    # شیفتی که از نیمه‌شب گذشته، متعلق به «دیروز» است
    today=str(j.weekday()); yday=str((j.weekday()-1) % 7)
    sched=workhours.get("schedule",{})
    d=sched.get(today,{})
    if d.get("open",False) and any(in_shift(ns,sh) for sh in d.get("shifts",[])
                                   if sh.get("from","") <= sh.get("to","")):
        return True
    for key in (today,yday):
        dd=sched.get(key,{})
        if not dd.get("open",False): continue
        for sh in dd.get("shifts",[]):
            if sh.get("from","") > sh.get("to","") and in_shift(ns,sh): return True
    return False

def next_open_text():
    """«فردا از ۱۱:۰۰» یا «شنبه از ۱۷:۰۰» — نزدیک‌ترین شیفتی که هنوز نیامده."""
    if not workhours.get("enabled",True): return ""
    now=datetime.now(IRAN_TZ); sched=workhours.get("schedule",{})
    for off in range(0,8):
        d=now+timedelta(days=off)
        j=jdatetime.datetime.fromgregorian(datetime=d)
        day=sched.get(str(j.weekday()),{})
        if not day.get("open",False): continue
        starts=sorted(sh["from"] for sh in day.get("shifts",[]) if valid_shift(sh))
        for st in starts:
            if off==0 and st<=now.strftime("%H:%M"): continue
            when=("امروز" if off==0 else "فردا" if off==1 else DAY_FA.get(str(j.weekday()),""))
            return f"{when} از ساعت {to_fa(st)}"
    return ""

def wh_today_block():
    if not workhours.get("enabled",True): return None
    j=jdatetime.datetime.fromgregorian(datetime=datetime.now(IRAN_TZ))
    wd=str(j.weekday()); day=workhours.get("schedule",{}).get(wd,{})
    lines=[status_line() or "",""]
    lines.append(f"📅 امروز {DAY_FA.get(wd,'')}")
    if not day.get("open"):
        lines.append("امروز تعطیل هستیم.")
    else:
        icons=["🌅","🌇","🌃","🕯"]
        for i,sh in enumerate(day.get("shifts",[])):
            if not valid_shift(sh): continue
            mark="🟢" if in_shift(datetime.now(IRAN_TZ).strftime("%H:%M"),sh) else (icons[i] if i<len(icons) else "🕐")
            lines.append(f"{mark} {to_fa(sh['from'])} تا {to_fa(sh['to'])}")
    return "\n".join(x for x in lines if x is not None).strip()

def wh_full_table():
    rows=[]
    for k,name in DAY_FA.items():
        day=workhours.get("schedule",{}).get(k,{})
        if not day.get("open"): rows.append(f"❌ {name}: تعطیل")
        else:
            sh=" و ".join(f"{to_fa(s['from'])} تا {to_fa(s['to'])}" for s in day.get("shifts",[]))
            rows.append(f"✅ {name}: {sh}")
    return "\n".join(rows)

def new_btn_id():
    """شناسه یکتا — time.time() ثانیه‌ای بود و دو دکمه در یک ثانیه شناسه یکسان می‌گرفتند."""
    return "b" + secrets.token_hex(4)

# طرح‌های مجاز برای دکمه‌های لینک؛ لینک نامعتبر باعث می‌شود تلگرام کل پیام
# آن بخش را رد کند و بخش برای همه کاربران از کار بیفتد.
# میزبان باید حداقل یک نقطه و یک TLD حرفی داشته باشد، وگرنه چیزی مثل
# «https://سلام» هم قبول می‌شد و دکمه در تلگرام رد می‌شد.
_URL_RE = re.compile(
    r"^https?://"                       # طرح
    r"(?:[^\s:@/]+(?::[^\s@/]*)?@)?"     # user:pass اختیاری
    r"[\w\u0080-\uffff-]+"              # برچسب اول دامنه
    r"(?:\.[\w\u0080-\uffff-]+)*"      # برچسب‌های میانی
    r"\.[A-Za-z\u0080-\uffff]{2,}"      # TLD
    r"(?::\d{1,5})?"                    # پورت اختیاری
    r"(?:[/?#]\S*)?$",                  # مسیر اختیاری
    re.IGNORECASE)

def normalize_url(text):
    """لینک را نرمال و اعتبارسنجی می‌کند. اگر معتبر نبود None برمی‌گرداند."""
    t=(text or "").strip()
    if not t: return None
    if t.startswith(("tg://","mailto:")): return t
    if not t.lower().startswith(("http://","https://")): t="https://"+t
    return t if _URL_RE.match(t) and len(t)<=2048 else None

# ════════════════════════════════════════════════
#  زبان بصری ربات — یک قالب واحد برای همه‌ی پیام‌ها
# ════════════════════════════════════════════════
HR   = "━━━━━━━━━━━━━━━"
CAP_LIMIT  = 1024      # سقف caption عکس در تلگرام
TEXT_LIMIT = 4096      # سقف متن پیام

def esc(t): return html.escape(str(t or ""))

def _fit(t,limit):
    if len(t)<=limit: return t
    cut=t[:limit-2].rsplit("\n",1)[0]
    return (cut or t[:limit-2])+"…"

def build_msg(title,content,sec_key=None,limit=TEXT_LIMIT):
    """قالب استاندارد: عنوان پررنگ، خط جداکننده، متن.

    خروجی HTML است؛ محتوای ادمین escape می‌شود تا کاراکترهایی مثل < پیام را
    نشکنند.
    """
    body=esc(content).strip()
    return _fit(f"<b>{esc(title)}</b>\n{HR}\n{body}" if body else f"<b>{esc(title)}</b>",limit)

def status_line():
    """نوار وضعیت زنده — «الان بازیم یا نه» مهم‌ترین چیزی است که مشتری می‌پرسد."""
    if not get_setting("store_open"): return "🔴 فروشگاه موقتاً بسته است"
    if not workhours.get("enabled",True): return None
    j=jdatetime.datetime.fromgregorian(datetime=datetime.now(IRAN_TZ))
    day=workhours.get("schedule",{}).get(str(j.weekday()),{})
    if is_open():
        now=datetime.now(IRAN_TZ).strftime("%H:%M")
        end=next((sh["to"] for sh in day.get("shifts",[]) if in_shift(now,sh)),None)
        return f"🟢 هم‌اکنون باز هستیم" + (f" · تا {to_fa(end)}" if end else "")
    if not day.get("open"): return "🔴 امروز تعطیل هستیم"
    nxt=next((sh["from"] for sh in day.get("shifts",[]) if sh.get("from","")>datetime.now(IRAN_TZ).strftime("%H:%M")),None)
    return "🔴 هم‌اکنون بسته است" + (f" · بازگشایی {to_fa(nxt)}" if nxt else "")

def progress_bar(v,t,n=8):
    if t==0: return "░"*n
    f=int(n*v/t); return "▓"*f+"░"*(n-f)

_stats_dirty = False
_last_err_report = 0.0      # زمان آخرین گزارش خطا به ادمین
_ERR_REPORT_GAP  = 60.0     # حداقل فاصله بین دو گزارش (ثانیه)

EV_MSG = "_msg"          # کلید ویژه: پیام آزادِ مشتری
EV_ABUSE = "_abuse"      # پیام توهین‌آمیز (برای کارت مشتری)

async def record_stat(k,uid=None):
    """شمارنده‌ی کلی (برای آمار) + رویداد شخصی (برای کارت شناخت مشتری)."""
    global _stats_dirty
    stats[k]=stats.get(k,0)+1
    _stats_dirty=True   # فقط flag — بدون disk write
    if uid is not None and get_setting("track_visits"):
        try: await record_event(uid,k)
        except Exception as e: logger.debug(f"record_event: {e}")

async def record_event(uid,key):
    await db.execute("INSERT INTO events(user_id,key,ts) VALUES(?,?,?)",
                     (uid,key,gregorian_now()))
    await db.commit()

# بازه‌های چهارساعته — ۲۴ خط در پیام تلگرام خوانا نیست
HOUR_BUCKETS = [(0,4,"🌙 ۰۰–۰۴"),(4,8,"🌅 ۰۴–۰۸"),(8,12,"☀️ ۰۸–۱۲"),
                (12,16,"🌤 ۱۲–۱۶"),(16,20,"🌇 ۱۶–۲۰"),(20,24,"🌃 ۲۰–۲۴")]

async def busy_hours(days=30):
    """پیام‌های مشتری در هر بازه‌ی ساعتی — «کی باید کنار گوشی باشم».

    ts به وقت تهران و به‌صورت متن ذخیره شده، پس strftime مستقیم همان
    ساعت محلی را می‌دهد و تبدیل منطقه‌ی زمانی لازم نیست.
    """
    async with db.execute(
        "SELECT CAST(strftime('%H',ts) AS INTEGER) h,COUNT(*) c FROM events "
        "WHERE key=? AND ts>=datetime('now',?,'localtime') GROUP BY h",
        (EV_MSG,f"-{days} days")) as c:
        rows=await c.fetchall()
    per_hour={h:n for h,n in rows if h is not None}
    buckets=[(lbl,sum(per_hour.get(h,0) for h in range(a,b))) for a,b,lbl in HOUR_BUCKETS]
    peak=max(per_hour.items(),key=lambda x:x[1])[0] if per_hour else None
    return buckets,peak,sum(per_hour.values())

async def prune_events(days=90):
    await db.execute("DELETE FROM events WHERE ts<datetime('now',?,'localtime')",
                     (f"-{days} days",))
    await db.commit()

async def _stats_flush_loop():
    """هر ۳۰ ثانیه اگر آمار تغییر کرده باشد، ذخیره می‌کند."""
    global _stats_dirty
    while True:
        await asyncio.sleep(30)
        # بدون این try، یک خطای نوشتن (دیسک پر، دسترسی) تسک را می‌کشت و
        # آمار تا ری‌استارت بعدی دیگر ذخیره نمی‌شد — آن هم بی‌صدا
        try:
            if _stats_dirty: await save_stats(); _stats_dirty=False
        except Exception as e: logger.error(f"stats_flush: {e}")

# ── load/save
async def _rj(path,default):
    """خواندن JSON. فایلِ خراب قرنطینه می‌شود تا ذخیره‌ی بعدی رویش ننویسد."""
    try:
        async with aiofiles.open(path,"r",encoding="utf-8") as f:
            return json.loads(await f.read())
    except FileNotFoundError:
        pass                      # اولین اجرا — طبیعی است
    except Exception as e:
        # فایل هست ولی خراب است. اگر کاری نکنیم، ذخیره‌ی بعدی محتوای
        # فروشگاه را با پیش‌فرض بازنویسی و برای همیشه نابود می‌کند.
        bad=f"{path}.corrupt"
        try:
            os.replace(path,bad)
            logger.error(f"⚠️ {path} خراب بود ({e}) — به {bad} منتقل شد و پیش‌فرض بارگذاری شد.")
        except Exception as e2:
            logger.error(f"⚠️ {path} خراب است ({e}) و قرنطینه هم نشد: {e2}")
    return default() if callable(default) else default

async def _wj(path,data):
    """نوشتن اتمیک. در صورت شکست False برمی‌گرداند تا فراخوان بتواند خبر بدهد."""
    tmp=path+".tmp"
    try:
        async with aiofiles.open(tmp,"w",encoding="utf-8") as f:
            await f.write(json.dumps(data,ensure_ascii=False,indent=2))
        os.replace(tmp,path)   # atomic — اگر crash کند فایل اصلی سالم می‌ماند
        return True
    except Exception as e:
        logger.error(f"write {path}: {e}")
        try: os.unlink(tmp)
        except Exception: pass
        return False

async def load_topics():
    global topics
    d=await _rj(TOPICS_FILE,lambda:None)
    if d is None:
        topics=[{"id":new_topic_id(),"title":"💰 لیست قیمت تازه"},
                {"id":new_topic_id(),"title":"🎁 تخفیف‌ها و پیشنهادها"},
                {"id":new_topic_id(),"title":"✨ محصولات تازه"}]
        await save_topics(); return
    topics=[x for x in d if isinstance(x,dict) and x.get("id") and x.get("title")] \
           if isinstance(d,list) else []

async def save_topics(): return await _wj(TOPICS_FILE,topics)

# ── اشتراک کاربر
async def sub_toggle(uid,tid):
    """برمی‌گرداند: وضعیت تازه (True=مشترک شد)."""
    async with db.execute("SELECT 1 FROM subs WHERE user_id=? AND topic=?",(uid,tid)) as c:
        on=(await c.fetchone()) is not None
    if on: await db.execute("DELETE FROM subs WHERE user_id=? AND topic=?",(uid,tid))
    else:   await db.execute("INSERT OR REPLACE INTO subs(user_id,topic,ts) VALUES(?,?,?)",
                             (uid,tid,gregorian_now()))
    await db.commit()
    return not on

async def user_subs(uid):
    async with db.execute("SELECT topic FROM subs WHERE user_id=?",(uid,)) as c:
        return {r[0] for r in await c.fetchall()}

async def sub_count(tid):
    return await _cnt("SELECT COUNT(*) FROM subs s JOIN users u ON u.user_id=s.user_id "
                      "WHERE s.topic=? AND u.is_blocked=0 AND u.has_left=0",(tid,))

async def load_pages():
    """بخش‌های سفارشی را به SECTION_NAMES تزریق می‌کند تا بقیه‌ی ربات
    (متن، بنر، دکمه، آمار، بک‌آپ) بدون هیچ تغییری با آن‌ها کار کند."""
    global pages
    data=await _rj(PAGES_FILE,list)
    pages=[x for x in data if isinstance(x,dict) and x.get("key") and x.get("title")] \
          if isinstance(data,list) else []
    SECTION_NAMES.clear(); SECTION_NAMES.update(BASE_SECTIONS)
    for pg in pages: SECTION_NAMES[pg["key"]]=pg["title"]
    logger.info(f"pages: {len(pages)} بخش سفارشی")

async def save_pages():
    SECTION_NAMES.clear(); SECTION_NAMES.update(BASE_SECTIONS)
    for pg in pages: SECTION_NAMES[pg["key"]]=pg["title"]
    invalidate_menu_cache()
    return await _wj(PAGES_FILE,pages)

def page_item(key): return next((x for x in pages if x["key"]==key),None)

async def load_data():
    global responses
    responses=await _rj(DATA_FILE,lambda:dict(MENU_ITEMS,welcome="✨ خوش آمدید به ربات استوک لند"))
async def save_data(): return await _wj(DATA_FILE,responses)

async def load_banners():
    global banners
    banners=await _rj(BANNER_FILE,dict)
    # migration: فرمت قدیمی flat (show_on, caption) → فرمت section-based
    if "show_on" in banners or "caption" in banners:
        old=banners.copy(); banners={}
        for k in SECTION_NAMES:
            if k in old and isinstance(old[k],dict):
                banners[k]=old[k]
        logger.info("banner.json: فرمت قدیمی شناسایی و migrate شد")
        await save_banners()
    for k in SECTION_NAMES: banners.setdefault(k,{"file_id":None,"active":False})
async def save_banners(): await _wj(BANNER_FILE,banners)

async def load_workhours():
    global workhours
    workhours=await _rj(WORKHOURS_FILE,dict)
    if not workhours: workhours=dict(DEFAULT_WH); await save_workhours()
async def save_workhours(): await _wj(WORKHOURS_FILE,workhours)

async def load_buttons():
    global buttons
    buttons=await _rj(BUTTONS_FILE,dict)
    for k in SECTION_NAMES: buttons.setdefault(k,{"enabled":True,"items":[]})
async def save_buttons(): await _wj(BUTTONS_FILE,buttons)

async def load_places():
    global places
    places=await _rj(PLACES_FILE,dict)
async def save_places(): return await _wj(PLACES_FILE,places)

async def load_menu():
    global menu_cfg
    invalidate_menu_cache()
    menu_cfg = await _rj(MENU_FILE, list)
    if not menu_cfg:
        menu_cfg = [dict(m) for m in DEFAULT_MENU]; await save_menu()
    else:
        valid = {d["key"] for d in DEFAULT_MENU} | {p["key"] for p in pages}
        # حذف کلیدهایی که دیگر وجود ندارند (مثلاً catalog از نسخه‌های قبلی)
        # وگرنه دکمه‌ای در منو می‌ماند که هیچ هندلری ندارد.
        dropped = [m["key"] for m in menu_cfg if m.get("key") not in valid]
        if dropped:
            menu_cfg = [m for m in menu_cfg if m.get("key") in valid]
            logger.info(f"menu: دکمه‌های منسوخ حذف شدند → {dropped}")
        # اطمینان از وجود همه کلیدها (اگر نسخه قدیمی بود)
        existing = {m["key"] for m in menu_cfg}
        for d in DEFAULT_MENU:
            if d["key"] not in existing: menu_cfg.append(dict(d))
        for m in menu_cfg:
            m.setdefault("width","half")
        if dropped: await save_menu()

async def save_menu():
    invalidate_menu_cache()
    return await _wj(MENU_FILE, menu_cfg)

async def reset_menu():
    global menu_cfg
    menu_cfg=[dict(m) for m in DEFAULT_MENU]
    await save_menu()

def menu_sorted():
    """آیتم‌های منو مرتب‌شده بر اساس order."""
    return sorted(menu_cfg, key=lambda m: m.get("order", 99))

def menu_item(key):
    return next((m for m in menu_cfg if m["key"] == key), None)

def menu_row_partner(key):
    """اگر این دکمه half باشد و در یک ردیف با دکمه half دیگری جفت شده،
    کلید جفتش را برمی‌گرداند؛ وگرنه None. (فقط دکمه‌های فعال)"""
    m = menu_item(key)
    if not m or m.get("width","half")!="half" or not m.get("enabled",True): return None
    items=[x for x in menu_sorted() if x.get("enabled",True)]
    # شبیه‌سازی جفت‌سازی main_menu
    pending=None
    for x in items:
        if x.get("width","half")=="full":
            pending=None
        else:
            if pending:
                if pending["key"]==key: return x["key"]
                if x["key"]==key: return pending["key"]
                pending=None
            else:
                pending=x
    return None

async def load_settings():
    global settings
    settings=await _rj(SETTINGS_FILE,dict)
    if not settings:
        settings=dict(DEFAULT_SETTINGS)
        await save_settings()
async def save_settings(): await _wj(SETTINGS_FILE,settings)

# ── مدیران
async def load_admins():
    """مدیرهای .env همیشه هستند؛ admins.json فقط مدیرهای افزوده‌شده از پنل است.
    اگر فایل خراب شود، مالک هرگز دسترسی‌اش را از دست نمی‌دهد."""
    global _admins_extra
    data=await _rj(ADMINS_FILE,list)
    _admins_extra=[int(x) for x in data
                   if isinstance(x,(int,str)) and str(x).lstrip("-").isdigit()] if isinstance(data,list) else []
    _admins.clear(); _admins.update(_ADMIN_ENV); _admins.update(_admins_extra)
    logger.info(f"admins: {len(_admins)} مدیر ({len(_admins_extra)} از پنل)")

async def save_admins(): return await _wj(ADMINS_FILE,_admins_extra)

async def add_admin(uid:int):
    if uid in _admins: return False
    _admins_extra.append(uid); _admins.add(uid); await save_admins(); return True

async def del_admin(uid:int):
    """مالک و مدیرهای .env از پنل حذف نمی‌شوند — وگرنه ممکن است کسی
    خودش را از ربات بیرون بیندازد و راه برگشتی نماند."""
    if uid in _ADMIN_ENV: return False
    if uid in _admins_extra: _admins_extra.remove(uid)
    _admins.discard(uid); await save_admins(); return True

async def notify_admins(bot,text,exclude=None,**kw):
    """یک خبر به همه‌ی مدیرها. خطای یک مدیر جلوی بقیه را نمی‌گیرد."""
    sent=0
    for aid in admin_ids():
        if exclude is not None and aid==exclude: continue
        try:
            await bot.send_message(aid,text,**kw); sent+=1
        except Exception as e: logger.debug(f"notify_admins {aid}: {e}")
    return sent
async def load_stats():
    global stats; stats=await _rj(STATS_FILE,dict)
async def save_stats(): await _wj(STATS_FILE,stats)

# ── database
db=None

async def safe_edit(msg,text,**kw):
    # اگر پیام عکس/کپشن دارد، edit_text کار نمی‌کند → پیام را حذف و پیام متنی جدید بفرست
    if getattr(msg,"photo",None) or getattr(msg,"caption",None) is not None:
        try: await msg.delete()
        except Exception: pass
        try: await msg.reply_text(text,**kw); return
        except Exception as e: logger.error(f"safe_edit(photo): {e}"); return
    try: await msg.edit_text(text,**kw)
    except Exception as e:
        if "not modified" in str(e).lower(): return
        try: await msg.reply_text(text,**kw)
        except Exception: logger.error(f"safe_edit: {e}")

async def init_db():
    global db
    db=await aiosqlite.connect(DB_FILE)
    # بهینه‌سازی SQLite — ایمن و سریع‌تر
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA synchronous=NORMAL")   # ایمن با WAL، سریع‌تر از FULL
    await db.execute("PRAGMA cache_size=-8000")     # ۸ مگابایت cache در RAM
    await db.execute("PRAGMA temp_store=MEMORY")    # عملیات موقت در RAM
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,username TEXT,first_name TEXT,
            joined_at TEXT,last_seen TEXT,is_blocked INTEGER DEFAULT 0);
        CREATE INDEX IF NOT EXISTS idx_ls ON users(last_seen);
        CREATE TABLE IF NOT EXISTS subs(
            user_id INTEGER,topic TEXT,ts TEXT,
            PRIMARY KEY(user_id,topic));
        CREATE INDEX IF NOT EXISTS idx_sub_t ON subs(topic);
        CREATE TABLE IF NOT EXISTS events(
            user_id INTEGER,key TEXT,ts TEXT);
        CREATE INDEX IF NOT EXISTS idx_ev_u ON events(user_id,ts);
        CREATE INDEX IF NOT EXISTS idx_ev_k ON events(key,ts);
        CREATE TABLE IF NOT EXISTS threads(
            admin_id INTEGER,msg_id INTEGER,user_id INTEGER,ts TEXT,
            PRIMARY KEY(admin_id,msg_id));
    """)
    for sql in ["ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN has_left INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN source TEXT DEFAULT ''",
                "ALTER TABLE users ADD COLUMN open_msg_at TEXT DEFAULT ''",
                "ALTER TABLE users ADD COLUMN reminded INTEGER DEFAULT 0"]:
        try: await db.execute(sql)
        except Exception as e:
            # «ستون تکراری» یعنی مهاجرت قبلاً انجام شده — بقیه خطاها واقعی‌اند
            if "duplicate column" not in str(e).lower():
                logger.error(f"مهاجرت دیتابیس ناموفق: {sql} → {e}")
    await db.commit()
    # تست واقعی نوشتن — بهتر است همین‌جا با پیام واضح بمیریم تا اینکه بعداً
    # موقع اولین /start کاربر بترکد و ربات ظاهراً «بی‌صدا» شود
    try:
        await db.execute("CREATE TABLE IF NOT EXISTS _wtest(x INTEGER)")
        await db.execute("DROP TABLE IF EXISTS _wtest")
        await db.commit()
    except Exception as e:
        raise SystemExit(
            f"❌ دیتابیس قابل نوشتن نیست: {e}\n"
            f"   مسیر: {os.path.abspath(DB_FILE)}\n"
            f"   کاربرِ اجراکننده‌ی سرویس باید اجازه نوشتن در این پوشه را داشته باشد\n"
            f"   (SQLite علاوه بر فایل دیتابیس، به نوشتن در خودِ پوشه هم نیاز دارد).\n"
            f"   رفع سریع:  sudo chown -R $(whoami) {os.path.dirname(os.path.abspath(DB_FILE))}")

_seen_uids: dict = {}   # uid → زمان آخرین save_user
_SEEN_TTL  = 300        # 5 دقیقه — اگر اخیراً ذخیره شده، skip کن

async def save_user(u):
    now_ts=time.time()
    if u.id in _seen_uids and now_ts-_seen_uids[u.id]<_SEEN_TTL: return
    now=gregorian_now()
    # یک UPSERT به‌جای INSERT+UPDATE — نصف کردن نوشتن روی مسیر داغ هر پیام.
    # نام ستون‌ها صریح است تا افزودن ستون جدید این کوئری را نشکند.
    await db.execute(
        "INSERT INTO users(user_id,username,first_name,joined_at,last_seen)"
        " VALUES(?,?,?,?,?)"
        " ON CONFLICT(user_id) DO UPDATE SET"
        "   username=excluded.username,"
        "   first_name=excluded.first_name,"
        "   last_seen=excluded.last_seen",
        (u.id,u.username or"",u.first_name or"",now,now))
    await db.commit()
    _seen_uids[u.id]=now_ts

async def mark_left(uid, left=1):
    """کاربری که ربات را بلاک/حذف کرده. جدا از is_blocked (که بلاکِ ادمین است)."""
    await db.execute("UPDATE users SET has_left=? WHERE user_id=?",(left,uid)); await db.commit()

async def left_count(): return await _cnt("SELECT COUNT(*) FROM users WHERE has_left=1")

# ── رشته‌ی گفتگو: هر پیامی که در چت مدیر مربوط به یک مشتری است ثبت می‌شود،
# تا وقتی مدیر رویش ریپلای زد بدانیم پاسخ برای چه کسی است.
async def link_thread(admin_id,msg_id,user_id):
    await db.execute(
        "INSERT OR REPLACE INTO threads(admin_id,msg_id,user_id,ts) VALUES(?,?,?,?)",
        (admin_id,msg_id,user_id,gregorian_now()))
    await db.commit()

async def thread_user(admin_id,msg_id):
    async with db.execute("SELECT user_id FROM threads WHERE admin_id=? AND msg_id=?",
                          (admin_id,msg_id)) as c:
        r=await c.fetchone()
    return r[0] if r else None

async def thread_last_msg(admin_id,user_id):
    """تازه‌ترین پیام مربوط به این مشتری در چت این مدیر — برای اینکه
    یادآوری به‌صورت ریپلای برود و با یک تپ به همان پیام بپرد."""
    async with db.execute(
        "SELECT msg_id FROM threads WHERE admin_id=? AND user_id=? ORDER BY msg_id DESC LIMIT 1",
        (admin_id,user_id)) as c:
        r=await c.fetchone()
    return r[0] if r else None

# ── کارت شناخت مشتری
async def customer_card(uid):
    """چند خط که مدیر را در جریان می‌گذارد طرف کیست.

    هیچ هوش مصنوعی‌ای در کار نیست — فقط همان چیزی که ربات دیده: کِی آمد،
    چند بار نوشت، از کجا آمد، و پیش از نوشتن چه خواند. وقتی بدانی مشتری
    صفحه‌ی اقساط را خوانده و بعد «سلام» نوشته، جوابت با یک تازه‌وارد فرق می‌کند.
    """
    if not get_setting("track_visits"): return ""
    async with db.execute(
        "SELECT joined_at,source FROM users WHERE user_id=?",(uid,)) as c:
        row=await c.fetchone()
    lines=[]
    src=(row[1] if row else "") or ""
    first=(row[0] if row else "") or ""
    head=[]
    if src: head.append(SOURCE_LABELS.get(src,f"🎯 {src}"))
    if first:
        a=ago_text(first)
        # تازه‌وارد یعنی همین امروز رسیده — «از ۳ دقیقه پیش اینجاست» بی‌معنی است
        head.append("🆕 تازه‌وارد" if ("دقیقه" in a or a=="همین الان" or "ساعت" in a)
                    else f"از {a} اینجاست")
    if head: lines.append(" · ".join(head))

    async with db.execute(
        "SELECT COUNT(*) FROM events WHERE user_id=? AND key=?",(uid,EV_MSG)) as c:
        nmsg=(await c.fetchone())[0]
    async with db.execute(
        "SELECT ts FROM events WHERE user_id=? AND key=? ORDER BY ts DESC LIMIT 1 OFFSET 1",
        (uid,EV_MSG)) as c:
        prev=await c.fetchone()
    part=[]
    if nmsg>1:   part.append(f"💬 {to_fa(nmsg)}اُمین پیامش")
    elif nmsg==1: part.append("💬 اولین پیامش")
    if prev: part.append(f"آخرین تماس {ago_text(prev[0])}")
    if part: lines.append("  ·  ".join(part))

    # چه بخش‌هایی را پیش از نوشتن دیده — بدون تکرار، تازه‌ترین اول
    async with db.execute(
        "SELECT key,MAX(ts) t FROM events WHERE user_id=? AND key NOT IN (?,?) "
        "GROUP BY key ORDER BY t DESC LIMIT 4",(uid,EV_MSG,EV_ABUSE)) as c:
        seen=[r[0] for r in await c.fetchall()]
    if seen:
        labels=[event_label(k) for k in seen]
        lines.append("👀 دیده: "+"، ".join(labels))
    async with db.execute(
        "SELECT COUNT(*) FROM events WHERE user_id=? AND key=?",(uid,EV_ABUSE)) as c:
        nab=(await c.fetchone())[0]
    if nab: lines.append(f"⚠️ {to_fa(nab)} بار پیام توهین‌آمیز")
    return "\n".join(esc(x) for x in lines)

# ── پیام‌های بی‌جواب
async def mark_open(uid):
    """اولین پیام بی‌جواب زمانش ثبت می‌شود و تا پاسخ دست‌نخورده می‌ماند،
    وگرنه هر پیام تازه سن انتظار را صفر می‌کرد."""
    await db.execute(
        "UPDATE users SET open_msg_at=? WHERE user_id=? AND COALESCE(open_msg_at,'')=''",
        (gregorian_now(),uid))
    await db.commit()

async def mark_answered(uid):
    await db.execute("UPDATE users SET open_msg_at='',reminded=0 WHERE user_id=?",(uid,))
    await db.commit()

async def open_count():
    return await _cnt("SELECT COUNT(*) FROM users WHERE COALESCE(open_msg_at,'')<>''")

async def open_list(limit=15):
    async with db.execute(
        "SELECT user_id,first_name,username,open_msg_at FROM users "
        "WHERE COALESCE(open_msg_at,'')<>'' ORDER BY open_msg_at LIMIT ?",(limit,)) as c:
        return await c.fetchall()

async def open_stale(hours=2):
    """بی‌جواب‌هایی که وقتشان گذشته و هنوز یادآوری نشده‌اند."""
    async with db.execute(
        "SELECT user_id,first_name FROM users WHERE COALESCE(open_msg_at,'')<>'' "
        "AND reminded=0 AND open_msg_at<datetime('now',?,'localtime')",(f"-{hours} hours",)) as c:
        return await c.fetchall()

def ago_text(ts):
    """«۳ ساعت پیش» — بدون تاریخ کامل، چون فقط سنِ انتظار مهم است."""
    try: t=datetime.strptime(ts,"%Y-%m-%d %H:%M:%S")
    except Exception: return "—"
    mins=int((datetime.now(IRAN_TZ).replace(tzinfo=None)-t).total_seconds()//60)
    if mins<1:  return "همین الان"
    if mins<60: return f"{to_fa(mins)} دقیقه پیش"
    if mins<1440: return f"{to_fa(mins//60)} ساعت پیش"
    return f"{to_fa(mins//1440)} روز پیش"

async def prune_threads(days=60):
    """رشته‌های خیلی قدیمی به درد نمی‌خورند — کسی روی پیام دو ماه پیش ریپلای نمی‌زند."""
    await db.execute("DELETE FROM threads WHERE ts<datetime('now',?,'localtime')",(f"-{days} days",))
    await db.commit()

# برچسب‌های خوانا برای منبع ورود (پارامتر deep-link)
SOURCE_LABELS = {"insta":"📸 اینستاگرام","instagram":"📸 اینستاگرام","tg":"✈️ تلگرام",
                 "telegram":"✈️ تلگرام","bale":"💬 بله","ble":"💬 بله","site":"🌐 سایت",
                 "web":"🌐 سایت","card":"🪧 کارت ویزیت","qr":"🔳 کد QR","shop":"🏪 حضوری"}
_SRC_RE = __import__("re").compile(r"^[A-Za-z0-9_-]{1,32}$")

async def set_source(uid,src):
    """منبع ورود فقط یک‌بار ثبت می‌شود — اولین راهی که کاربر از آن آمده."""
    if not src or not _SRC_RE.match(src): return
    await db.execute(
        "UPDATE users SET source=? WHERE user_id=? AND (source IS NULL OR source='')",
        (src.lower(),uid))
    await db.commit()

async def source_stats():
    async with db.execute(
        "SELECT COALESCE(NULLIF(source,''),'—') s,COUNT(*) c FROM users "
        "GROUP BY s ORDER BY c DESC") as c:
        return await c.fetchall()

_block_cache: dict = {}   # uid → (is_blocked: bool, expires: float)
_BLOCK_CACHE_TTL = 60     # ثانیه — بعد از این مدت مجدداً از DB خوانده می‌شود

async def is_blocked(uid):
    now=time.time()
    cached=_block_cache.get(uid)
    if cached and cached[1]>now: return cached[0]
    async with db.execute("SELECT is_blocked FROM users WHERE user_id=?",(uid,)) as c:
        r=await c.fetchone()
    result=bool(r and r[0])
    _block_cache[uid]=(result,now+_BLOCK_CACHE_TTL)
    return result

async def set_block(uid,v):
    await db.execute("UPDATE users SET is_blocked=? WHERE user_id=?",(v,uid)); await db.commit()
    _block_cache[uid]=(bool(v),time.time()+_BLOCK_CACHE_TTL)  # فوری cache را آپدیت کن

async def search_users(q):
    q_like=f"%{q}%"
    async with db.execute(
        "SELECT user_id,first_name,username,last_seen,is_blocked FROM users WHERE first_name LIKE ? OR username LIKE ? OR CAST(user_id AS TEXT) LIKE ? ORDER BY last_seen DESC LIMIT 15",
        (q_like,q_like,q_like)) as c: return await c.fetchall()

async def get_users_page(offset,limit=15,ft="all"):
    flt={"today":"WHERE DATE(last_seen)=DATE('now','localtime')","week":"WHERE last_seen>=datetime('now','-7 days','localtime')","blocked":"WHERE is_blocked=1"}
    async with db.execute(f"SELECT user_id,first_name,username,last_seen,is_blocked FROM users {flt.get(ft,'')} ORDER BY last_seen DESC LIMIT {limit} OFFSET {offset}") as c: return await c.fetchall()

async def _cnt(sql,args=()):
    async with db.execute(sql,args) as c: return(await c.fetchone())[0]

async def total_users(): return await _cnt("SELECT COUNT(*) FROM users")
async def today_users(): return await _cnt("SELECT COUNT(*) FROM users WHERE DATE(last_seen)=DATE('now','localtime')")
async def week_users():  return await _cnt("SELECT COUNT(*) FROM users WHERE last_seen>=datetime('now','-7 days','localtime')")
async def month_users(): return await _cnt("SELECT COUNT(*) FROM users WHERE last_seen>=datetime('now','-30 days','localtime')")
async def new_today():   return await _cnt("SELECT COUNT(*) FROM users WHERE DATE(joined_at)=DATE('now','localtime')")
async def blk_count():   return await _cnt("SELECT COUNT(*) FROM users WHERE is_blocked=1")

# ── anti-spam (سیستم سبک — sliding window، بدون DB query، بدون lock)
_rate:       dict = {}   # uid → [timestamps]
_warned:     dict = {}   # uid → زمان اولین هشدار
_hard_block: dict = {}   # uid → blocked_until timestamp
_RATE_MAX   = 8          # حداکثر کلیک مجاز در پنجره
_RATE_WIN   = 10.0       # پنجره زمانی (ثانیه)
_HARD_BLOCK = 10.0       # مدت بلاک سخت (ثانیه)

async def _spam_cleanup_loop():
    """هر ۶ ساعت دیکشنری‌های anti-spam را از کاربران منقضی پاک می‌کند.
    صفر تاثیر روی سرعت — فقط در زمان idle اجرا می‌شود."""
    while True:
        await asyncio.sleep(6 * 3600)
        try:
            now = time.time()
            stale = [uid for uid, ts in list(_rate.items())
                     if not ts or now - max(ts) > _RATE_WIN * 6]
            for uid in stale:
                _rate.pop(uid, None); _warned.pop(uid, None)
            for uid in [u for u, t in list(_hard_block.items()) if t < now]:
                del _hard_block[uid]
            for uid in [u for u,(v,exp) in list(_block_cache.items()) if exp<now]:
                del _block_cache[uid]
            for uid in [u for u,ts in list(_seen_uids.items()) if now-ts>_SEEN_TTL*3]:
                del _seen_uids[uid]
            if stale: logger.debug(f"spam_cleanup: {len(stale)} رکورد منقضی پاک شد")
            await prune_threads(); await prune_events()
        except Exception as e: logger.error(f"spam_cleanup: {e}")

def spam_check(uid: int) -> str:
    """کاملاً sync — بدون await، بدون DB، صفر overhead.
    بازگشتی: 'ok' | 'warn' | 'block'
      ok    → درخواست معمولی، ادامه بده
      warn  → اولین بار اسپم شناسایی شد — popup هشدار نشان بده، ریپلای نده
      block → کاربر بعد از هشدار ادامه داد — ۱۰ ثانیه بی‌صدا بلاک"""
    if is_admin(uid): return 'ok'
    now = time.time()
    # بلاک سخت فعال است؟
    if _hard_block.get(uid, 0) > now: return 'block'
    # پنجره نرخ — فقط timestamps داخل _RATE_WIN ثانیه اخیر
    ts = [t for t in _rate.get(uid, ()) if now - t < _RATE_WIN]
    if len(ts) >= _RATE_MAX:
        _rate[uid] = ts
        if uid in _warned:        # هشدار قبلاً داده شده → بلاک سخت ۱۰ ثانیه
            del _warned[uid]
            _hard_block[uid] = now + _HARD_BLOCK
            return 'block'
        _warned[uid] = now        # اولین تخطی → هشدار
        return 'warn'
    ts.append(now); _rate[uid] = ts
    _warned.pop(uid, None)        # کاربر آرام گرفت → هشدار ریست شود
    return 'ok'

# ════════════════════════════════════════════════
#  KEYBOARDS
# ════════════════════════════════════════════════
_menu_kb_cache = None      # کیبورد منو در هر پیام از نو ساخته می‌شد

def invalidate_menu_cache():
    global _menu_kb_cache
    _menu_kb_cache = None

# متن کم‌رنگِ داخل جعبه‌ی تایپ — جایی که مشتری دقیقاً همان لحظه نگاه می‌کند.
# هر بار یکی، تا حس «یک دستیار زنده» بدهد و نشان دهد چه چیزهایی می‌شود پرسید.
# (سقف تلگرام ۶۴ نویسه است)
ASSIST_HINTS = ("🤖 بپرسید… مثلاً: آیفون ۱۳ چنده؟",
                "🤖 بپرسید… مثلاً: قسطی با چک میشه؟",
                "🤖 بپرسید… مثلاً: گوشیمو معاوضه می‌کنید؟",
                "🤖 بپرسید… مثلاً: رجیستر شده دارید؟",
                "🤖 بپرسید… مثلاً: گارانتی دارن؟",
                "🤖 بپرسید… مثلاً: کجایید؟ تا کی بازید؟")

def main_menu():
    global _menu_kb_cache
    if _menu_kb_cache is None: _menu_kb_cache = _build_main_menu()
    if not get_setting("assistant"): return _menu_kb_cache
    return ReplyKeyboardMarkup(_menu_kb_cache.keyboard,resize_keyboard=True,
                               input_field_placeholder=random.choice(ASSIST_HINTS))

def _build_main_menu():
    # به ترتیب order، با احترام به عرض هر دکمه:
    #   full → یک ردیف کامل | half → کنار دکمه half بعدی
    # نکته RTL: تلگرام لیست را چپ‌به‌راست می‌چیند، پس برای اینکه
    # دکمه اولِ هر جفت سمت راست بیفتد، ترتیب لیست را معکوس می‌کنیم.
    items=[m for m in menu_sorted() if m.get("enabled",True)]
    rows=[]; pending=None
    for m in items:
        if m.get("width","half")=="full":
            if pending: rows.append([pending]); pending=None
            rows.append([m["label"]])
        else:
            if pending:
                rows.append([m["label"],pending]); pending=None  # دومی چپ، اولی(pending) راست
            else:
                pending=m["label"]
    if pending: rows.append([pending])
    if not rows: rows=[["🏠 منو"]]
    return ReplyKeyboardMarkup(rows,resize_keyboard=True)

def cancel_menu(): return ReplyKeyboardMarkup([["❌ لغو عملیات"]],resize_keyboard=True)

# یکپارچه برای تمام بخش‌ها — support_kb حذف شد (تکراری بود)
def section_links(key):
    """لینک‌های نهایی یک بخش: دکمه‌های دستیِ ادمین + لینک‌های خودِ متن.

    لینک داخل متن خودکار دکمه می‌شود — نه لینک آبیِ خام در پیام. ادمین
    لازم نیست کاری بکند؛ فقط لینک را در متن بنویسد.
    """
    out=[]; seen=set()
    sec=get_sec_btns(key)
    if sec.get("enabled",True):
        for it in sec.get("items",[]):
            u=(it.get("url") or "").strip()
            if not u or u.rstrip("/").lower() in seen: continue
            seen.add(u.rstrip("/").lower()); out.append((it.get("title") or "🔗 لینک",u))
    for title,u in extract_links(responses.get(key,"") if responses else ""):
        if u.rstrip("/").lower() in seen: continue
        seen.add(u.rstrip("/").lower()); out.append((title,u))
    return out

def link_button(title,url):
    """دکمه‌ی لینک. لینک سایتِ خودِ فروشگاه به‌صورت «مینی‌اپ» باز می‌شود:
    سایت داخل خود تلگرام می‌آید، نه در مرورگر — مشتری از ربات جدا نمی‌شود.
    شرط تلگرام: فقط HTTPS و فقط در چت خصوصی."""
    if (get_setting("miniapp") and url.lower().startswith("https://")
            and SHOP_SITE.lower() in url.lower()):
        try: return InlineKeyboardButton(title,web_app=WebAppInfo(url=url))
        except Exception: pass
    return InlineKeyboardButton(title,url=url)

def user_sec_kb(key,home=False):
    links=section_links(key)
    btns=[]; row=[]
    for i,(title,url) in enumerate(links):
        row.append(link_button(title,url))
        # لینک‌های کوتاه دوتایی، بلندها تک‌ردیفه — چیدمان تمیزتر
        if len(row)==2 or len(title)>18 or i==len(links)-1:
            btns.append(row); row=[]
    if row: btns.append(row)
    return InlineKeyboardMarkup(btns) if btns else None

# ── admin keyboards
def backup_text():
    last=settings.get("last_auto_backup") or ""
    if last:
        try:
            j=jdatetime.date.fromgregorian(date=datetime.strptime(last,"%Y-%m-%d").date())
            last=f"{to_fa(j.day)} {MONTH_FA[j.month]}"
        except Exception: pass
    return ("💾 پشتیبان‌گیری و بازیابی\n"+"─"*20+
            "\n🗓 بکاپ خودکار: هفته‌ای یک‌بار، جمعه ۳ بامداد"+
            (f"\n✅ آخرین بکاپ خودکار: {last}" if last else "\n⏳ هنوز بکاپ خودکاری نرفته")+
            f"\n📦 {to_fa(len(_backup_registry))} نسخه‌ی اخیر نگه داشته می‌شود"
            "\n\nهر وقت خواستید، «دریافت پشتیبان» فوری هم می‌گیرد.")

def backup_kb():
    rows=[
        [InlineKeyboardButton("💾 دریافت پشتیبان",callback_data="backup_get"),
         InlineKeyboardButton("📥 بارگذاری فایل",callback_data="backup_import")]
    ]
    if _backup_registry:
        rows.append([InlineKeyboardButton("──── بکاپ‌های هفتگی ────",callback_data="noop")])
        for i,b in enumerate(reversed(_backup_registry)):
            rows.append([InlineKeyboardButton(f"♻️ {b['date']}",callback_data=f"backup_auto_{i}")])
    rows.extend(_nav(back="settings_menu"))
    return InlineKeyboardMarkup(rows)

# ════════════════════════════════════════════════
#  پنل ادمین — صفحه اصلی زنده
# ════════════════════════════════════════════════
HOME_CB = "adm_home"

def _nav(*extra, home=True, back=None):
    """ردیف ناوبری استاندارد ته هر صفحه — همه‌جا یکسان."""
    row=[]
    if back: row.append(InlineKeyboardButton("🔙 بازگشت",callback_data=back))
    if home: row.append(InlineKeyboardButton("🏠 پنل اصلی",callback_data=HOME_CB))
    rows=[list(e) for e in extra]
    if row: rows.append(row)
    return rows

async def admin_home_text():
    """وضعیت لحظه‌ای فروشگاه — مهم‌ترین اعداد بدون نیاز به باز کردن چیزی."""
    t,d,nt,op = await asyncio.gather(total_users(), today_users(), new_today(), open_count())
    opened=is_open()
    sep="─"*20
    lines=[f"👑 پنل مدیریت — {shamsi_now()}", sep]
    if not get_setting("store_open"):
        lines.append("🔴 فروشگاه دستی بسته شده است")
    else:
        lines.append("🟢 فروشگاه باز است" if opened else "🔴 خارج از ساعت کاری")
    wh=workhours.get("schedule",{}).get(
        str(jdatetime.datetime.fromgregorian(datetime=datetime.now(IRAN_TZ)).weekday()),{})
    if wh.get("open") and wh.get("shifts"):
        sh=" و ".join(f"{to_fa(x['from'])}–{to_fa(x['to'])}" for x in wh["shifts"])
        lines.append(f"🕐 امروز: {sh}")
    elif workhours.get("enabled",True):
        lines.append("🕐 امروز تعطیل است")
    lines += [sep,
              f"👥 {to_fa(t)} کاربر  ·  🆕 {to_fa(nt)} امروز  ·  📅 {to_fa(d)} فعال امروز"]
    if op:
        lines.append(f"💬 {to_fa(op)} پیام بی‌جواب — برای پاسخ در همین چت ریپلای بزنید")
    if _bc_job:
        n=len(_bc_job["queue"])
        if _bc_job["status"]=="pending" and _bc_job.get("run_at"):
            lines.append(f"⏰ پخش زمان‌بندی‌شده برای {bc_when_text(_bc_job['run_at'])} · {to_fa(n)} نفر")
        else:
            lines.append(f"📢 پخش در حال اجرا — {to_fa(_bc_job['i'])}/{to_fa(n)}")
    if len(_admins)>1:
        lines.append(f"👮 {to_fa(len(_admins))} مدیر")
    return "\n".join(lines)

def admin_home_kb(open_msgs=0):
    shop=("🔴 بستن فروشگاه" if get_setting("store_open") else "🟢 باز کردن فروشگاه")
    rows=[]
    if open_msgs:
        rows.append([InlineKeyboardButton(f"💬 {to_fa(open_msgs)} پیام بی‌جواب",
                                          callback_data="pending")])
    return InlineKeyboardMarkup(rows+[
        [InlineKeyboardButton("👥 کاربران",callback_data="users_menu"),
         InlineKeyboardButton("📊 آمار",callback_data="adm_stats")],
        [InlineKeyboardButton("✏️ محتوای ربات",callback_data="adm_content"),
         InlineKeyboardButton("🕐 ساعت کاری",callback_data="wh_menu")],
        [InlineKeyboardButton("📣 پیام همگانی",callback_data="broadcast"),
         InlineKeyboardButton("⚙️ تنظیمات",callback_data="settings_menu")],
        [InlineKeyboardButton(shop,callback_data="stg_store_open")],
    ])

async def show_home(msg, edit=True):
    txt=await admin_home_text(); kb=admin_home_kb(await open_count())
    if edit: await safe_edit(msg,txt,reply_markup=kb)
    else:    await msg.reply_text(txt,reply_markup=kb)

def settings_text():
    return ("⚙️ تنظیمات\n"+"─"*20+
            "\nبا زدن هر گزینه، روشن/خاموش می‌شود."
            "\n\n💡 پاسخ خودکار: سؤال آماده‌ای که کلیدواژه‌اش در پیام مشتری باشد"
            "\n#️⃣ میان‌بر: هنگام پاسخ، #کلیدواژه را می‌نویسید و جواب آماده می‌رود"
            "\n❓ سؤال‌های بی‌پاسخ: پرسش‌هایی که هیچ جوابی برایشان نبود"
            "\n👤 حافظه‌ی رفتار: کارت شناخت مشتری روی پیام‌ها و آمار ساعت‌های شلوغ"
            "\n📊 گزارش هفتگی: خلاصه‌ی هفته، جمعه‌ها کنار بکاپ"
            f"\n🪟 سایت داخل تلگرام: لینک‌های {SHOP_SITE} به‌جای مرورگر، داخل خود تلگرام"
            "\n🧠 دستیار: گفت‌وگوی طبیعی با مشتری از روی نیت‌ها (بدون API)"
            "\n📋 رونوشت: پیام‌هایی که دستیار جواب داد هم برای مدیرها فرستاده شود"
            "\n🛡 توهین: به پیام بی‌ادبانه تذکر می‌دهد؛ بار سوم گفتگو یک ساعت متوقف می‌شود"
            " (کلمه‌ی تازه: /badword)")

def stats_kb():
    return InlineKeyboardMarkup(_nav(
        [InlineKeyboardButton("🗑 صفر کردن آمار بازدید",callback_data="stats_reset")],
        [InlineKeyboardButton("🔄 بروزرسانی",callback_data="adm_stats")],
    ))

async def stats_text():
    """داشبورد و آمار بخش‌ها در یک صفحه — قبلاً دو صفحه جدا بود."""
    t,d,w,m,nt,bl,lf = await asyncio.gather(
        total_users(),today_users(),week_users(),month_users(),new_today(),
        blk_count(),left_count())
    sep="─"*20
    out=[f"📊 آمار — {shamsi_now()}",sep,
         f"👥 کل کاربران: {to_fa(t)}",
         f"✅ فعال: {to_fa(t-lf-bl)}   🚪 ترک‌کرده: {to_fa(lf)}   🚫 بلاک: {to_fa(bl)}",
         sep,
         f"🆕 عضو امروز:  {to_fa(nt)}",
         f"📅 فعال امروز: {to_fa(d)}  {progress_bar(d,t)}",
         f"📆 فعال هفته:  {to_fa(w)}  {progress_bar(w,t)}",
         f"🗓 فعال ماه:   {to_fa(m)}  {progress_bar(m,t)}"]
    srcs=[r for r in await source_stats() if r[0]!="—"]
    if srcs:
        out += [sep,"🎯 مشتری‌ها از کجا آمده‌اند"]
        out += [f"• {SOURCE_LABELS.get(r[0],r[0])}: {to_fa(r[1])}" for r in srcs[:8]]
    try:
        buckets,peak,total_msg=await busy_hours()
    except Exception as e:
        logger.debug(f"busy_hours: {e}"); buckets,peak,total_msg=[],None,0
    if total_msg:
        out += [sep,f"🕘 پیام مشتری‌ها در ۳۰ روز اخیر ({to_fa(total_msg)} پیام)"]
        top=max(n for _,n in buckets) or 1
        out += [f"{progress_bar(n,top)} {to_fa(n):>3}  {lbl}" for lbl,n in buckets if n]
        if peak is not None:
            out.append(f"⏰ شلوغ‌ترین ساعت: {to_fa(f'{peak:02d}')}:۰۰")
    labels=dict(SECTION_NAMES); labels["wh_page"]="🕐 ساعت کاری"
    rows=sorted(((labels.get(k,k),v) for k,v in stats.items() if v),key=lambda r:-r[1])
    out += [sep,"📈 بازدید بخش‌ها"]
    if not rows:
        out.append("هنوز بازدیدی ثبت نشده است.")
    else:
        top=rows[0][1]
        out += [f"{progress_bar(v,top)} {to_fa(v)}  {name}" for name,v in rows[:12]]
        out.append(f"مجموع: {to_fa(sum(v for _,v in rows))} بازدید")
    txt="\n".join(out)
    return txt[:3990]+"…" if len(txt)>4000 else txt

async def topics_text():
    out=["<b>🔔 موضوع‌های اطلاع‌رسانی</b>",HR,
         "کاربر خودش انتخاب می‌کند از چه چیزی خبردار شود. بعد در «پیام همگانی» "
         "می‌توانید فقط به مشترک‌های یک موضوع پیام بدهید — نه به همه.",HR]
    if not topics: out.append("هنوز موضوعی تعریف نشده.")
    for t in topics:
        out.append(f"• {esc(t['title'])} — {to_fa(await sub_count(t['id']))} مشترک")
    return _fit("\n".join(out),TEXT_LIMIT)

def topics_kb():
    rows=[[InlineKeyboardButton("➕ موضوع تازه",callback_data="tp_add")]]
    for t in topics:
        rows.append([InlineKeyboardButton(f"🗑 {_fit(t['title'],26)}",
                                          callback_data=f"tp_dl_{t['id']}")])
    return InlineKeyboardMarkup(_nav(*rows,back="adm_content"))

def content_kb():
    return InlineKeyboardMarkup(_nav(
        [InlineKeyboardButton("🧩 دکمه‌های منوی اصلی",callback_data="menu_mgr")],
        [InlineKeyboardButton("📝 متن، بنر و لینک بخش‌ها",callback_data="sections")],
        [InlineKeyboardButton(f"🧠 دستیار هوشمند · {to_fa(len(faq))} نیت",callback_data="faq_menu")],
        [InlineKeyboardButton(f"🔔 موضوع‌های اطلاع‌رسانی · {to_fa(len(topics))}",
                              callback_data="tp_menu")],
    ))

# ── سؤال‌های آماده
# مدیرهایی که دارند مثل مشتری با دستیار حرف می‌زنند (در حافظه؛ ری‌استارت خاموشش می‌کند)
test_mode: set = set()

TEST_HELP = ("🧪 <b>حالت آزمایش روشن شد</b>\n"+HR+
             "\nحالا مثل یک مشتری بنویسید؛ دستیار دقیقاً همان جوابی را می‌دهد که "
             "مشتری می‌گیرد. هیچ چیزی ثبت، شمرده یا برای همکارها فرستاده نمی‌شود."
             "\n\nچند نمونه:\n• سلام، آیفون ۱۳ چنده؟\n• واسه ۱۴ چی؟\n• قسطی میدید؟"
             "\n• کجایید؟\n• گوشیمو میخرید؟\n• رجیستر شده دارید؟"
             "\n\nبرای خاموشی دوباره <code>/test</code> را بزنید.")

def faq_menu_text():
    on=sum(1 for x in faq if x.get("enabled",True))
    hits=sum(x.get("hits",0) for x in faq)
    state=("🟢 روشن" if get_setting("assistant") else "⚫️ خاموش (فقط تطبیق ساده‌ی کلیدواژه)")
    return ("<b>🧠 دستیار هوشمند</b>  ·  "+state+"\n"+HR+
            "\nمشتری مثل یک گفت‌وگوی عادی می‌نویسد؛ دستیار می‌فهمد درباره‌ی کدام "
            "«نیت» است و جواب می‌دهد — با هم‌معنی‌ها، غلط تایپی و ادامه‌ی بحث. "
            "اگر نفهمد، حدس نمی‌زند و پیام را به شما می‌سپارد."
            "\n\n<b>هر نیت:</b> کلیدواژه‌ها + جمله‌های نمونه + متن پاسخ + یک «کار» "
            "(نمایش بخش، ساعت کاری، لیست قیمت، سپردن به همکار)."
            "\n\n🧪 <b>امتحان مثل مشتری:</b> «حالت آزمایش» را روشن کنید و هر چه "
            "می‌خواهید بنویسید — جوابِ دستیار را همان‌طور که مشتری می‌بیند می‌گیرید "
            "(چیزی ثبت یا برای کسی فرستاده نمی‌شود). یا یک جمله: "
            "<code>/ask میشه قسطی بخرم؟</code>"
            f"\n\n📊 {to_fa(on)} نیت فعال از {to_fa(len(faq))}  ·  "
            f"{to_fa(hits)} بار جواب داده")

def faq_menu_kb(uid=None):
    t="🧪 حالت آزمایش: روشن — برای خاموشی بزنید" if uid in test_mode else "🧪 امتحان مثل مشتری"
    rows=[[InlineKeyboardButton(t,callback_data="faq_test")],
          [InlineKeyboardButton("➕ نیت تازه",callback_data="faq_add")]]
    if get_setting("log_unmatched") and unmatched:
        rows.append([InlineKeyboardButton(
            f"❓ سؤال‌های بی‌پاسخ · {to_fa(len(unmatched))}",callback_data="unm_menu")])
    for it in faq:
        mark="🟢" if it.get("enabled",True) else "⚫️"
        h=it.get("hits",0)
        rows.append([InlineKeyboardButton(
            f"{mark} {_fit(faq_title(it),24)}"+(f" · {to_fa(h)}" if h else ""),
            callback_data=f"faq_v_{it['id']}")])
    return InlineKeyboardMarkup(_nav(*rows,back="adm_content"))

def faq_view_text(it):
    pic=""
    if it.get("photo"):
        pic=f"\n🖼 عکس دارد  ·  {faq_photo_stamp(it) or '—'}"
    k1=(it.get("keys") or [None])[0]
    act=it.get("action") or ""
    ex=it.get("examples") or []
    sug=[faq_title(faq_item(i)) for i in it.get("suggest") or [] if faq_item(i)]
    ans=it.get("answer","")
    if not ans.strip() and act.startswith("section:"):
        ans=f"(متن از خودِ بخش «{SECTION_NAMES.get(act[8:],act[8:])}» خوانده می‌شود)"
    nvar=len([x for x in brain.VARIANT_SEP.split(it.get("answer","")) if x.strip()])
    return _fit(f"<b>🧠 {esc(faq_title(it))}</b>  ·  "
                +("🟢 فعال" if it.get("enabled",True) else "⚫️ خاموش")+"\n"+HR+
                "\n🔑 کلیدواژه‌ها: "+esc("، ".join(it.get("keys",[]) or ["—"]))+
                (f"\n🗣 جمله‌های نمونه: {to_fa(len(ex))}" if ex else "")+
                f"\n⚙️ کار: {esc(action_label(act))}"+
                (f"\n👉 پیشنهاد بعدی: {esc('، '.join(sug))}" if sug else "")+
                (f"\n🎲 {to_fa(nvar)} شکلِ متفاوت از پاسخ" if nvar>1 else "")+
                f"\n📊 {to_fa(it.get('hits',0))} بار جواب داده"+pic+
                (f"\n\n♻️ برای عوض‌کردن سریع عکس، همین‌جا عکس را با کپشن "
                 f"<code>#{esc(k1)}</code> بفرستید." if k1 else "")+
                f"\n{HR}\n"+esc(ans)+
                "\n\n<i>راهنما: چند شکل پاسخ را با خطی که فقط «---» دارد جدا کنید. "
                "جای‌نگهدارها: {name} {product} {status} {hours}</i>",TEXT_LIMIT)

def faq_view_kb(it):
    pic=([InlineKeyboardButton("🖼 تغییر عکس",callback_data=f"faq_ep_{it['id']}"),
          InlineKeyboardButton("🗑 حذف عکس",callback_data=f"faq_dp_{it['id']}")]
         if it.get("photo") else
         [InlineKeyboardButton("🖼 افزودن عکس",callback_data=f"faq_ep_{it['id']}")])
    return InlineKeyboardMarkup(_nav(
        [InlineKeyboardButton("🔑 کلیدواژه‌ها",callback_data=f"faq_ek_{it['id']}"),
         InlineKeyboardButton("📝 پاسخ",callback_data=f"faq_ea_{it['id']}")],
        [InlineKeyboardButton("⚙️ کار دستیار",callback_data=f"faq_ac_{it['id']}")],
        pic,
        [InlineKeyboardButton("⚫️ غیرفعال کن" if it.get("enabled",True) else "🟢 فعال کن",
                              callback_data=f"faq_tg_{it['id']}"),
         InlineKeyboardButton("🗑 حذف",callback_data=f"faq_dl_{it['id']}")],
        back="faq_menu"))

def faq_by_key(word):
    """پیدا کردن سؤال آماده از روی یک کلیدواژه‌ی دقیق — برای میان‌بر #."""
    w=faq_norm(word).strip()
    if len(w)<2: return None
    for it in faq:
        if any(faq_norm(k).strip()==w for k in it.get("keys",[])): return it
    return None

# ── پیام‌های بی‌جواب
async def pending_text():
    rows=await open_list()
    if not rows:
        return "<b>💬 پیام‌های بی‌جواب</b>\n"+HR+"\n✅ همه‌ی پیام‌ها جواب داده شده‌اند."
    out=["<b>💬 پیام‌های بی‌جواب</b>",HR]
    for uid,fn,un,ts in rows:
        out.append(f"• {esc(fn or '—')}"+(f" · @{esc(un)}" if un else "")+
                   f"\n  🆔 <code>{uid}</code> · {esc(ago_text(ts))}")
    out += [HR,"برای پاسخ، در همین چت روی پیام مشتری ریپلای بزنید.",
            "دکمه‌ی زیر پیام‌ها را برایتان بالا می‌آورد."]
    return _fit("\n".join(out),TEXT_LIMIT)

def pending_kb(has_rows=True):
    rows=[]
    if has_rows: rows.append([InlineKeyboardButton("🔔 نشانم بده در چت",callback_data="pend_ping")])
    rows.append([InlineKeyboardButton("🔄 بروزرسانی",callback_data="pending")])
    return InlineKeyboardMarkup(_nav(*rows))

async def ping_open(bot,admin_id):
    """هر پیام بی‌جواب را به‌صورت ریپلای بالا می‌آورد — یک تپ و مدیر
    دقیقاً روی همان پیام مشتری است و همان‌جا جواب می‌دهد."""
    sent=0
    for uid,fn,un,ts in await open_list():
        mid=await thread_last_msg(admin_id,uid)
        try:
            await bot.send_message(admin_id,
                f"⏳ بی‌جواب از {ago_text(ts)} — {fn or uid}",
                reply_to_message_id=mid)
            sent+=1
        except Exception as e:
            logger.debug(f"ping_open {admin_id}/{uid}: {e}")
    return sent

async def _pending_loop(bot):
    """هر نیم‌ساعت: پیامی که بیش از ۲ ساعت بی‌جواب مانده یک‌بار یادآوری می‌شود."""
    await asyncio.sleep(120)
    while True:
        try:
            for uid,fn in await open_stale(2):
                for aid in admin_ids():
                    mid=await thread_last_msg(aid,uid)
                    if mid is None: continue
                    try:
                        await bot.send_message(aid,
                            f"⏰ پیام {fn or uid} بیش از ۲ ساعت بی‌جواب مانده.",
                            reply_to_message_id=mid)
                    except Exception as e: logger.debug(f"reminder {aid}: {e}")
                await db.execute("UPDATE users SET reminded=1 WHERE user_id=?",(uid,))
            await db.commit()
        except Exception as e: logger.error(f"pending_loop: {e}")
        await asyncio.sleep(1800)

# ترتیب نمایش بخش‌ها — دقیقاً مطابق منوی کاربر
SECTION_ORDER = ["welcome","1","2","3","4","5","workhours","notify","6","7"]

def section_order():
    """ترتیب نمایش در پنل: بخش‌های پایه، بعد بخش‌های سفارشی."""
    return SECTION_ORDER + [p["key"] for p in pages]

def pages_hint():
    return ("\n\n📄 بخش‌های سفارشی: هر تعداد که بخواهید بسازید. هرکدام متن، "
            "بنر، لینک و لوکیشن خودش را دارد و می‌تواند به منوی اصلی برود.")

def sections_kb():
    btns=[]; row=[]
    for key in section_order():
        if key not in SECTION_NAMES: continue
        name=SECTION_NAMES[key]
        cont=responses.get(key,"") if responses else ""
        b=get_banner(key); sec=get_sec_btns(key)
        mark=""
        if cont and cont not in("تنظیم نشده",""): mark+="📝"
        if b.get("active") and b.get("file_id"): mark+="🖼"
        if sec.get("enabled") and sec.get("items"): mark+="🔗"
        label=f"{name}  {mark}" if mark else name
        row.append(InlineKeyboardButton(label,callback_data=f"sec_{key}"))
        if len(row)==2: btns.append(row); row=[]
    if row: btns.append(row)
    btns.append([InlineKeyboardButton("➕ بخش تازه",callback_data="page_add")])
    btns.extend(_nav(back="adm_content"))
    return InlineKeyboardMarkup(btns)

def section_kb(key):
    b=get_banner(key)
    ban_lbl="🖼 بنر  🟢 فعال" if(b.get("active") and b.get("file_id")) else("🖼 بنر  ⏸ آپلود‌شده" if b.get("file_id") else"🖼 بنر  ➕ ندارد")
    sec=get_sec_btns(key); n=len(sec.get("items",[])); en=sec.get("enabled")
    btn_lbl=f"🔗 دکمه‌ها  {'🟢' if en else '🔴'}  ({to_fa(n)} عدد)"
    rows=[[InlineKeyboardButton("✏️ ویرایش متن",callback_data=f"sec_text_{key}")]]
    rows.append([InlineKeyboardButton(ban_lbl,callback_data=f"sec_ban_{key}")])
    rows.append([InlineKeyboardButton(btn_lbl,callback_data=f"sec_btns_{key}")])
    pl=places.get(key) or {}
    if pl.get("lat") is not None:
        loc_lbl=f"📍 لوکیشن  {'🟢 فعال' if pl.get('active') else '🔴 غیرفعال'}"
    else:
        loc_lbl="📍 لوکیشن  ➕ ندارد"
    rows.append([InlineKeyboardButton(loc_lbl,callback_data=f"sec_loc_{key}")])
    if key not in ("welcome",):
        rows.append([InlineKeyboardButton("🔗 لینک مستقیم این بخش",
                                          callback_data=f"sec_link_{key}")])
    if is_custom(key):
        m=menu_item(key)
        on=bool(m and m.get("enabled",True))
        rows.append([InlineKeyboardButton(f"🧩 در منوی اصلی  {'🟢' if on else '⚫️'}",
                                          callback_data=f"page_menu_{key}"),
                     InlineKeyboardButton("🗑 حذف بخش",callback_data=f"page_dl_{key}")])
    rows.append([InlineKeyboardButton("🔙 بازگشت",callback_data="sections")])
    return InlineKeyboardMarkup(rows)

def place_text(key):
    pl=places.get(key) or {}
    name=SECTION_NAMES.get(key,key)
    out=[f"📍 لوکیشن: {name}","─"*20]
    if pl.get("lat") is None:
        out += ["❌ هنوز لوکیشنی ثبت نشده است.","",
                "با «📤 ثبت لوکیشن» و سپس فرستادن موقعیت از منوی 📎 تلگرام،",
                "نقشه داخل خودِ تلگرام برای کاربران باز می‌شود — بدون لینک بیرونی."]
    else:
        out += ["🟢 به کاربران نمایش داده می‌شود" if pl.get("active")
                else "⚫️ ذخیره شده ولی نمایش داده نمی‌شود",
                f"🏷 {pl.get('title') or SHOP_NAME}"]
        if pl.get("address"): out.append(f"🗺 {pl['address']}")
        out.append(f"🧭 {pl['lat']:.6f}, {pl['lon']:.6f}")
        if pl.get("active"):
            out += ["","📌 تا وقتی این لوکیشن فعال است، کاربر **فقط همین کارت**"
                       " را می‌بیند: نقشه + نام + آدرس + دکمه‌های بخش.",
                    "متن و بنر این بخش نمایش داده نمی‌شوند (تلگرام اجازه نمی‌دهد"
                    " نقشه با عکس یا متن در یک پیام باشد).",
                    "با غیرفعال‌کردن لوکیشن، متن و بنر برمی‌گردند."]
    return "\n".join(out)

def place_kb(key):
    pl=places.get(key) or {}
    rows=[[InlineKeyboardButton("📤 ثبت لوکیشن" if pl.get("lat") is None else "🔄 تغییر لوکیشن",
                                callback_data=f"loc_up_{key}")]]
    if pl.get("lat") is not None:
        rows.append([InlineKeyboardButton("🔴 غیرفعال‌سازی" if pl.get("active") else "🟢 فعال‌سازی",
                                          callback_data=f"loc_tg_{key}")])
        rows.append([InlineKeyboardButton("✏️ عنوان و آدرس",callback_data=f"loc_ed_{key}")])
        rows.append([InlineKeyboardButton("🗑 حذف لوکیشن",callback_data=f"loc_dl_{key}")])
    rows.extend(_nav(back=f"sec_{key}"))
    return InlineKeyboardMarkup(rows)

def banner_kb(key):
    b=get_banner(key); tg="🔴 غیرفعال‌سازی" if b.get("active") else "🟢 فعال‌سازی"
    btns=[[InlineKeyboardButton("📤 آپلود تصویر",callback_data=f"ban_up_{key}")],
          [InlineKeyboardButton(tg,callback_data=f"ban_tg_{key}")]]
    if b.get("file_id"): btns.append([InlineKeyboardButton("🗑 حذف تصویر",callback_data=f"ban_dl_{key}")])
    btns.extend(_nav(back=f"sec_{key}")); return InlineKeyboardMarkup(btns)

def banner_text(key):
    b=get_banner(key); name=SECTION_NAMES.get(key,key)
    lines=[f"🖼 بنر: {name}","─"*20]
    if not b.get("file_id"):
        lines.append("❌ هنوز تصویری ثبت نشده است.")
    else:
        lines.append("🟢 فعال — به کاربران نمایش داده می‌شود" if b.get("active")
                     else "⚫️ غیرفعال — ذخیره شده ولی نمایش داده نمی‌شود")
        if b.get("w"): lines.append(f"📐 {to_fa(b['w'])}×{to_fa(b.get('h',0))}")
        lines.append("♻️ روی سرور تلگرام ذخیره است — بدون آپلود مجدد ارسال می‌شود.")
    return "\n".join(lines)

def sec_btns_kb(key):
    sec=get_sec_btns(key); tg="🔴 غیرفعال‌سازی" if sec.get("enabled") else "🟢 فعال‌سازی"
    btns=[[InlineKeyboardButton(tg,callback_data=f"btn_tg_{key}")]]
    for it in sec.get("items",[]):
        btns.append([InlineKeyboardButton(f"🔗 {it['title']}",callback_data=f"btn_ed_{key}_{it['id']}"),
                     InlineKeyboardButton("🗑 حذف",callback_data=f"btn_dl_{key}_{it['id']}")])
    btns.append([InlineKeyboardButton("➕ افزودن دکمه",callback_data=f"btn_add_{key}")])
    if extract_links(responses.get(key,"") if responses else ""):
        btns.append([InlineKeyboardButton("✨ ساخت دکمه از لینک‌های متن",
                                          callback_data=f"btn_auto_{key}")])
    btns.extend(_nav(back=f"sec_{key}"))
    return InlineKeyboardMarkup(btns)

def wh_kb():
    en=workhours.get("enabled",True)
    tg="🔴 غیرفعال‌سازی" if en else "🟢 فعال‌سازی"
    btns=[[InlineKeyboardButton(tg,callback_data="wh_toggle")]]
    day_list=list(DAY_FA.items())
    for i in range(0,len(day_list),2):
        row=[]
        for k,name in day_list[i:i+2]:
            day=workhours.get("schedule",{}).get(k,{})
            row.append(InlineKeyboardButton(f"{'✅' if day.get('open') else '❌'} {name}",callback_data=f"wh_day_{k}"))
        btns.append(row)
    btns+=[[InlineKeyboardButton("✏️ پیام باز",callback_data="wh_mop"),
            InlineKeyboardButton("✏️ پیام بسته",callback_data="wh_mcl")],
           ]+_nav()
    return InlineKeyboardMarkup(btns)

def wh_day_kb(dk):
    day=workhours.get("schedule",{}).get(dk,{})
    tg="🔴 تعطیل" if day.get("open") else "🟢 باز کردن"
    return InlineKeyboardMarkup([[InlineKeyboardButton(tg,callback_data=f"wh_dtg_{dk}")],
        [InlineKeyboardButton("✏️ ساعت‌ها",callback_data=f"wh_sh_{dk}")],
        [InlineKeyboardButton("🔙",callback_data="wh_menu")]])

def menu_mgr_kb():
    """لیست دکمه‌های منو با وضعیت، برای مدیریت."""
    btns=[]
    items=menu_sorted()
    for idx,m in enumerate(items):
        status="🟢" if m.get("enabled",True) else "⚫️"
        btns.append([InlineKeyboardButton(f"{status} {m['label']}",callback_data=f"mi_{m['key']}")])
    btns.append([InlineKeyboardButton("♻️ بازگردانی به حالت پیش‌فرض",callback_data="menu_reset")])
    btns.extend(_nav(back="adm_content"))
    return InlineKeyboardMarkup(btns)

def menu_item_kb(key):
    """تنظیمات یک دکمه: روشن/خاموش، تغییر نام، جابجایی بالا/پایین."""
    m=menu_item(key)
    if not m: return menu_mgr_kb()
    items=menu_sorted()
    idx=next((i for i,x in enumerate(items) if x["key"]==key),0)
    en=m.get("enabled",True)
    w=m.get("width","half")
    w_lbl="📐 عرض: تمام‌صفحه" if w=="full" else "📐 عرض: نصف‌صفحه"
    rows=[
        [InlineKeyboardButton("🔴 خاموش کردن" if en else "🟢 روشن کردن",callback_data=f"mtg_{key}")],
        [InlineKeyboardButton("✏️ تغییر نام",callback_data=f"mnm_{key}")],
        [InlineKeyboardButton(w_lbl,callback_data=f"mw_{key}")],
    ]
    move=[]
    if idx>0: move.append(InlineKeyboardButton("⬆️ بالا",callback_data=f"mup_{key}"))
    if idx<len(items)-1: move.append(InlineKeyboardButton("⬇️ پایین",callback_data=f"mdn_{key}"))
    if move: rows.append(move)
    # جابجایی چپ/راست فقط وقتی این نیم‌دکمه با دکمه دیگری هم‌ردیف باشد
    if w=="half" and menu_row_partner(key):
        rows.append([InlineKeyboardButton("↔️ جابجایی چپ و راست",callback_data=f"msw_{key}")])
    rows.append([InlineKeyboardButton("🔙 بازگشت",callback_data="menu_mgr")])
    return InlineKeyboardMarkup(rows)

def settings_kb(owner=False):
    notif="🟢" if get_setting("notify_new_user") else "⚫️"
    fwd="🟢" if get_setting("forward_user_msgs") else "⚫️"
    shop="🟢" if get_setting("store_open") else "🔴"
    auto="🟢" if get_setting("faq_auto") else "⚫️"
    scut="🟢" if get_setting("faq_shortcut") else "⚫️"
    unm ="🟢" if get_setting("log_unmatched") else "⚫️"
    trk ="🟢" if get_setting("track_visits") else "⚫️"
    dig ="🟢" if get_setting("weekly_digest") else "⚫️"
    ast ="🟢" if get_setting("assistant") else "⚫️"
    typ ="🟢" if get_setting("typing_delay") else "⚫️"
    ccad="🟢" if get_setting("ai_cc_admin") else "⚫️"
    mini="🟢" if get_setting("miniapp") else "⚫️"
    prof="🟢" if get_setting("profanity_filter") else "⚫️"
    rows=[[InlineKeyboardButton(f"{shop} فروشگاه باز است",callback_data="stg_store_open")],
          [InlineKeyboardButton(f"{notif} اعلان عضو جدید",callback_data="stg_notify_new_user")],
          [InlineKeyboardButton(f"{fwd} دریافت پیام کاربران",callback_data="stg_forward_user_msgs")],
          [InlineKeyboardButton(f"{auto} پاسخ خودکار سؤال‌ها",callback_data="stg_faq_auto")],
          [InlineKeyboardButton(f"{scut} میان‌بر #کلیدواژه",callback_data="stg_faq_shortcut")],
          [InlineKeyboardButton(f"{unm} ثبت سؤال‌های بی‌پاسخ",callback_data="stg_log_unmatched")],
          [InlineKeyboardButton(f"{trk} حافظه‌ی رفتار مشتری",callback_data="stg_track_visits")],
          [InlineKeyboardButton(f"{dig} گزارش هفتگی",callback_data="stg_weekly_digest")],
          [InlineKeyboardButton(f"{mini} سایت داخل تلگرام",callback_data="stg_miniapp")],
          [InlineKeyboardButton(f"{ast} دستیار هوشمند",callback_data="stg_assistant")],
          [InlineKeyboardButton(f"{typ} «در حال نوشتن…»",callback_data="stg_typing_delay"),
           InlineKeyboardButton(f"{ccad} رونوشت برای مدیر",callback_data="stg_ai_cc_admin")],
          [InlineKeyboardButton(f"{prof} تذکر به توهین و فحش",callback_data="stg_profanity_filter")]]
    # مدیریت مدیرها و بازگردانی بک‌آپ فقط دستِ مالک است
    if owner:
        rows.append([InlineKeyboardButton(f"👮 مدیران ربات · {to_fa(len(_admins))}",
                                          callback_data="adm_admins")])
        rows.append([InlineKeyboardButton("💾 پشتیبان‌گیری و بازیابی",callback_data="backup")])
    return InlineKeyboardMarkup(_nav(*rows))

# ── مدیریت مدیرها (فقط مالک)
async def user_label(uid):
    async with db.execute("SELECT first_name,username FROM users WHERE user_id=?",(uid,)) as c:
        r=await c.fetchone()
    if not r: return "—"
    return (r[0] or "—")+(f" · @{r[1]}" if r[1] else "")

async def admins_text():
    lines=["<b>👮 مدیران ربات</b>",HR]
    for aid in admin_ids():
        if aid==OWNER_ID:      tag="👑 مالک"
        elif aid in _ADMIN_ENV: tag="🔒 ثابت (از فایل .env)"
        else:                   tag="👤 مدیر"
        lines.append(f"{tag} — {esc(await user_label(aid))}\n🆔 <code>{aid}</code>")
    lines += [HR,
              "هر مدیر پیام‌های مشتری‌ها را می‌گیرد و به پنل دسترسی دارد.",
              "بک‌آپ، بازگردانی و همین صفحه فقط برای مالک باز است."]
    return "\n".join(lines)

def admins_kb():
    rows=[[InlineKeyboardButton("➕ افزودن مدیر",callback_data="adm_add")]]
    for aid in admin_ids():
        if aid in _ADMIN_ENV: continue   # مالک و مدیرهای .env از پنل حذف نمی‌شوند
        rows.append([InlineKeyboardButton(f"🗑 حذف {aid}",callback_data=f"adm_del_{aid}")])
    return InlineKeyboardMarkup(_nav(*rows,back="settings_menu"))

def users_menu_kb(): return InlineKeyboardMarkup(_nav(
    [InlineKeyboardButton("🔍 جستجوی کاربر",callback_data="users_search")],
    [InlineKeyboardButton("👥 همه کاربران",callback_data="ul_all_0"),
     InlineKeyboardButton("🆕 امروز",callback_data="ul_today_0")],
    [InlineKeyboardButton("📆 این هفته",callback_data="ul_week_0"),
     InlineKeyboardButton("🚫 بلاک‌شده‌ها",callback_data="ul_blocked_0")],
))

def users_list_kb(rows,off,ft,total):
    btns=[[InlineKeyboardButton(f"{'🚫 ' if r[4] else ''}{r[1] or '—'} | {r[0]}",callback_data=f"uv_{r[0]}")] for r in rows]
    nav=[]
    if off>0: nav.append(InlineKeyboardButton("◀️",callback_data=f"ul_{ft}_{off-15}"))
    if off+15<total: nav.append(InlineKeyboardButton("▶️",callback_data=f"ul_{ft}_{off+15}"))
    if nav: btns.append(nav)
    btns.append([InlineKeyboardButton("🔙",callback_data="users_menu")]); return InlineKeyboardMarkup(btns)

# پاسخ به مشتری فقط از راه چت خود تلگرام است (ریپلای روی پیام فوروارد‌شده)،
# پس اینجا دکمه‌ی «پیام به کاربر» نداریم.
def udetail_kb(uid,is_bl): return InlineKeyboardMarkup([
    [InlineKeyboardButton("✅ رفع بلاک" if is_bl else "🚫 بلاک",callback_data=f"utog_{uid}")],
    [InlineKeyboardButton("🔙",callback_data="users_menu")]])


# ── send with banner
# ── عکس‌ها ───────────────────────────────────────
# تلگرام هر عکس را در چند اندازه نگه می‌دارد و برای هرکدام یک file_id می‌دهد.
# با ذخیره‌ی file_id، عکس فقط یک‌بار آپلود می‌شود و برای همیشه بازاستفاده
# می‌گردد. انتخاب نسخه‌ی مناسب (نه بزرگ‌ترین) یعنی کاربران حجم کمتری دانلود
# می‌کنند — بدون نیاز به هیچ کتابخانه‌ی پردازش تصویر.
BANNER_MAX_W = 1280      # عرض هدف برای بنر
THUMB_MAX_W  = 320       # عرض هدف برای پیش‌نمایش پنل

def _area(p): return (getattr(p,"width",0) or 0)*(getattr(p,"height",0) or 0)

def pick_photo(sizes,max_w=BANNER_MAX_W):
    """سبک‌ترین نسخه‌ای که هنوز کیفیت کافی دارد (عرض ≤ max_w)."""
    if not sizes: return None
    ordered=sorted(sizes,key=_area)
    fit=[p for p in ordered if (getattr(p,"width",0) or 0)<=max_w]
    return fit[-1] if fit else ordered[0]

def human_kb(n):
    try: n=int(n or 0)
    except Exception: return "؟"
    return f"{to_fa(round(n/1024))} کیلوبایت" if n else "؟"

SHOP_NAME = "استوک لند"

# ── حذف لینک نقشه وقتی کارت لوکیشن جایگزینش می‌شود ─────────
_MAP_URL_RE = re.compile(
    r"https?://\S*(?:maps\.app\.goo\.gl|goo\.gl/maps|google\.[a-z.]+/maps|maps\.google"
    r"|neshan\.org|nshn\.ir|balad\.ir|waze\.com|openstreetmap\.org|osm\.org)\S*",
    re.IGNORECASE)
_ARROWS = "👇⬇↓👉➡️⬅"
# واژه‌هایی که نشان می‌دهند یک خط فقط برای اشاره به لینک نقشه نوشته شده
_MAP_WORDS = ("گوگل","مپ","map","نقشه","لینک","link","مسیریاب","مسیر یاب",
              "لوکیشن","موقعیت","نشان","بلد","waze","google")

def _rstrip_arrows(t):
    while t and (t[-1] in _ARROWS or t[-1] in " \u200c\ufe0f"):
        t=t[:-1]
    return t.rstrip()

def _strip_urls(text,url_re):
    """لینک‌های منطبق و هر چیزی که فقط به آن‌ها اشاره می‌کرد را برمی‌دارد."""
    if not text or not url_re.search(text): return text

    def _is_label(t):
        """برچسب کوتاهی که فقط نام لینک بوده — نه یک جمله‌ی واقعی."""
        return len(t)<=22 and not t.rstrip().endswith((".","،","!","؟",":"))

    out=[]
    for line in text.splitlines():
        had_url=bool(url_re.search(line))
        cleaned=url_re.sub("",line).strip()
        # خطی که جز لینک چیزی نداشت (یا فقط «🔗» از آن مانده)
        if had_url and (not cleaned or not any(ch.isalnum() for ch in cleaned)):
            # برچسبِ بالای آن («📸 Instagram») هم مرجعی ندارد — نام روی
            # خودِ دکمه نوشته شده است.
            if out and _is_label(out[-1]): out.pop()
            continue
        if not cleaned: continue
        low=cleaned.lower()
        if any(a in cleaned for a in _ARROWS) and any(w in low for w in _MAP_WORDS):
            continue                                    # اشاره‌گرِ بی‌مرجع
        if had_url:
            bare=cleaned.rstrip(" :：-–—»>|،,").strip()
            if not bare or (len(cleaned)<=25 and cleaned[-1] in ":：-–—»>|"):
                continue                                # برچسب معلق
        cleaned=_rstrip_arrows(cleaned)
        if cleaned: out.append(cleaned)
    res=[]
    for line in out:
        if not line and (not res or not res[-1]): continue
        res.append(line)
    return "\n".join(res).strip()

def strip_map_links(text):
    """لینک نقشه را برمی‌دارد چون کارت نقشه جایش را گرفته.
    غیرمخرب — متن اصلی در data.json دست‌نخورده می‌ماند."""
    return _strip_urls(text,_MAP_URL_RE)

# ── لینک‌های شبکه‌های اجتماعی → دکمه ─────────────────────
SHOP_SITE = "stland.ir"      # دامنه‌ی خود فروشگاه — برای نام‌گذاری دکمه
_ANY_URL_RE = re.compile(
    r"https?://\S+"
    r"|(?<![\w@./])(?:www\.)?[\w-]+\.(?:ir|com|net|org|me|ai|io|co)(?:/\S*)?",
    re.IGNORECASE)
_LINK_LABELS = (
    ("instagram.","📸 اینستاگرام"), ("t.me","✈️ تلگرام"), ("telegram.","✈️ تلگرام"),
    ("ble.ir","💬 بله"), ("bale.ai","💬 بله"), ("eitaa.","📱 ایتا"),
    ("rubika.","🟣 روبیکا"), ("rubino.","🟣 روبینو"), ("wa.me","💚 واتساپ"),
    ("whatsapp.","💚 واتساپ"), ("aparat.","🎬 آپارات"), ("youtube.","▶️ یوتیوب"),
    ("youtu.be","▶️ یوتیوب"), ("linkedin.","💼 لینکدین"), ("twitter.","✖️ ایکس"),
    ("x.com","✖️ ایکس"), ("facebook.","📘 فیس‌بوک"), ("divar.","🔷 دیوار"),
)

def label_for_url(url):
    low=url.lower()
    for frag,lbl in _LINK_LABELS:
        if frag in low: return lbl
    host=re.sub(r"^https?://","",low).split("/")[0].replace("www.","")
    if host and SHOP_SITE in host: return "🌐 وب‌سایت فروشگاه"
    return f"🔗 {host}" if host else "🔗 لینک"

def extract_links(text):
    """(عنوان، لینک) برای هر لینک متن — بدون تکرار، به ترتیب ظهور."""
    out=[]; seen=set()
    for m in _ANY_URL_RE.finditer(text or ""):
        u=normalize_url(m.group(0).rstrip(".،,؛;"))
        if not u or u in seen: continue
        seen.add(u); out.append((label_for_url(u),u))
    return out

# ════════════════════════════════════════════════
#  FAQ — پاسخ خودکار به سؤال‌های تکراری
# ════════════════════════════════════════════════
# هیچ دکمه‌ای به منوی مشتری اضافه نمی‌شود: مشتری سؤالش را مثل همیشه
# می‌نویسد، اگر با کلیدواژه‌های ادمین جور بود همان‌جا جواب می‌گیرد، و
# پیامش باز هم برای مدیرها فوروارد می‌شود تا اگر ناقص بود کاملش کنند.
faq: list = []

# ی/ك عربی → فارسی، حذف نیم‌فاصله و علائم، تا نوشتار مشتری مانع تطبیق نشود
_AR_FIX = str.maketrans("يكةۀأإآؤ", "یکههاااو")
_PUNCT_RE = re.compile(r"[\u200c\u200f\u200e?؟!.,،؛;:\-_()\[\]{}\"'«»]+")

def faq_norm(t):
    t=(t or "").translate(_AR_FIX).translate(FA_DIGITS).lower()
    t=_PUNCT_RE.sub(" ",t)
    return " "+re.sub(r"\s+"," ",t).strip()+" "

def faq_match(text):
    """اولین سؤال آماده‌ای که کلیدواژه‌اش در متن مشتری هست.

    تطبیق فقط با کلیدواژه‌های خودِ ادمین است — هیچ حدسی در کار نیست.
    اگر مطمئن نباشیم چیزی نمی‌گوییم؛ جواب غلط از جواب ندادن بدتر است.
    بلندترین کلیدواژه برنده است تا «گارانتی طلایی» بر «گارانتی» بچربد.
    """
    if not text: return None
    n=faq_norm(text)
    best=None; best_len=0
    for item in faq:
        if not item.get("enabled",True) or not item.get("answer"): continue
        for k in item.get("keys",[]):
            kn=faq_norm(k).strip()
            if len(kn)<2 or kn not in n: continue
            if len(kn)>best_len: best,best_len=item,len(kn)
    return best

def faq_title(item):
    """نام خوانا — برچسب دکمه، یا اولین کلیدواژه، یا ابتدای پاسخ."""
    if item.get("button"): return item["button"]
    ks=item.get("keys") or []
    return ks[0] if ks else _fit(item.get("answer",""),30)

def faq_photo_stamp(item):
    """«لیست ۲۱ مرداد» — تاریخِ عکس روی خودِ جواب، تا اگر روزی آپدیت
    نشد مشتری خودش بفهمد و بپرسد."""
    ts=item.get("photo_at")
    if not ts: return ""
    try: d=datetime.strptime(ts,"%Y-%m-%d %H:%M:%S")
    except Exception: return ""
    j=jdatetime.datetime.fromgregorian(datetime=d)
    return f"🗓 {to_fa(j.day)} {MONTH_FA[j.month]}"

async def send_faq(msg,item,footer=True,chat=False,lead="",values=None,extra_rows=None):
    """پاسخ آماده — اگر عکس داشته باشد با عکس، وگرنه متنی.

    chat=True یعنی لحن گفت‌وگو: بدون قاب و سرتیتر، مثل پیام یک آدم.
    پاسخ‌های چندشکلی («---») و جای‌نگهدارها ({name}، {product}…) فقط
    همین‌جا پر می‌شوند تا هیچ‌وقت خام به مشتری نرسند."""
    kb=merge_kb(faq_kb_for(item),extra_rows)
    raw=brain.pick_variant(item.get("answer","")) if chat else item.get("answer","")
    if values is not None or chat: raw=brain.fill(raw,**(values or {}))
    body=strip_text_links(raw) if faq_kb_for(item) else raw
    stamp=faq_photo_stamp(item)
    if chat:
        parts=[esc(x) for x in (lead,body) if x and x.strip()]
        if stamp and item.get("photo"): parts.append(f"<i>{esc(stamp)}</i>")
        txt="\n\n".join(parts) or "👇"
    else:
        head=f"<b>💡 {esc(faq_title(item))}</b>"
        if stamp: head += f"  ·  {esc(stamp)}"
        tail=("\n\n<i>اگر پاسخ کامل نبود نگران نباشید — همکاران ما هم پیام شما را "
              "دیدند و جواب می‌دهند.</i>") if footer else ""
        txt=f"{head}\n{HR}\n{esc(body)}{tail}"
    if item.get("photo"):
        await msg.reply_photo(photo=item["photo"],caption=_fit(txt,CAP_LIMIT),
                              parse_mode="HTML",reply_markup=kb)
    else:
        await msg.reply_text(_fit(txt,TEXT_LIMIT),parse_mode="HTML",
                             reply_markup=kb or main_menu(),disable_web_page_preview=True)

def faq_kb_for(item):
    """لینک‌های داخل پاسخ → دکمه، مثل بقیه‌ی بخش‌ها."""
    links=extract_links(item.get("answer",""))
    btns=[]; row=[]
    for i,(title,url) in enumerate(links):
        row.append(link_button(title,url))
        if len(row)==2 or len(title)>18 or i==len(links)-1:
            btns.append(row); row=[]
    if row: btns.append(row)
    return InlineKeyboardMarkup(btns) if btns else None

# نشانه‌ی متن نمونه‌ای که هنوز ادمین ننوشته (نسخه‌های قبلی چنین نمونه‌هایی
# می‌ساختند؛ هنگام کاشت نیت‌های پیش‌فرض با نسخه‌ی کامل جایگزین می‌شوند)
PLACEHOLDER_MARK = "را اینجا بنویسید"

# ── سؤال‌های بی‌پاسخ: چیزی که مشتری پرسید و هیچ جوابی برایش نبود.
# فهرستِ سؤال‌های آماده را به‌جای حدسِ ادمین، از خودِ مشتری‌ها می‌سازد.
unmatched: list = []      # [{"text","count","last","uid"}]
UNMATCHED_MAX = 200
_UNM_MIN, _UNM_MAX = 3, 200   # کوتاه‌تر از این حرف نیست، بلندتر از این متن است

async def log_unmatched(text,user=None):
    if not get_setting("log_unmatched"): return
    t=(text or "").strip()
    if not (_UNM_MIN <= len(t) <= _UNM_MAX): return
    n=faq_norm(t)
    for it in unmatched:
        if faq_norm(it["text"])==n:
            it["count"]=it.get("count",1)+1; it["last"]=gregorian_now()
            break
    else:
        unmatched.insert(0,{"id":new_btn_id(),"text":t,"count":1,"last":gregorian_now(),
                            "uid":getattr(user,"id",None)})
        del unmatched[UNMATCHED_MAX:]
    await save_unmatched()

async def load_unmatched():
    global unmatched
    d=await _rj(UNMATCHED_FILE,list)
    unmatched=[x for x in d if isinstance(x,dict) and x.get("text")][:UNMATCHED_MAX] \
              if isinstance(d,list) else []

async def save_unmatched(): return await _wj(UNMATCHED_FILE,unmatched)

def unmatched_text():
    if not get_setting("log_unmatched"):
        return ("<b>❓ سؤال‌های بی‌پاسخ</b>\n"+HR+
                "\n⚫️ این قابلیت از «تنظیمات» خاموش شده است.")
    if not unmatched:
        return ("<b>❓ سؤال‌های بی‌پاسخ</b>\n"+HR+
                "\nهنوز سؤالی بدون جواب نمانده.")
    top=unmatched_sorted()
    out=["<b>❓ سؤال‌های بی‌پاسخ</b>",HR,
         "پرسش‌هایی که هیچ سؤال آماده‌ای جوابشان را نداشت — "
         "پرتکرارها اول. روی هرکدام بزنید تا از رویش سؤال آماده بسازید.",HR]
    for it in top[:20]:
        c=it.get("count",1)
        out.append(f"• {esc(_fit(it['text'],70))}"+(f"  ×{to_fa(c)}" if c>1 else ""))
    return _fit("\n".join(out),TEXT_LIMIT)

def unmatched_kb():
    rows=[]
    for it in unmatched_sorted()[:10]:
        c=it.get("count",1)
        # شناسه‌ی ثابت، نه شماره‌ی ردیف: اگر بین نمایش و تپ سؤال تازه‌ای
        # برسد، ترتیب عوض می‌شود و ردیف اشتباه باز می‌شد
        rows.append([InlineKeyboardButton(
            f"➕ {_fit(it['text'],28)}"+(f" ×{to_fa(c)}" if c>1 else ""),
            callback_data=f"unm_{it.get('id','?')}")])
    if unmatched:
        rows.append([InlineKeyboardButton("🗑 پاک کردن فهرست",callback_data="unm_clear")])
    return InlineKeyboardMarkup(_nav(*rows,back="faq_menu"))

def unmatched_sorted():
    """پرتکرارها اول؛ در تساوی، تازه‌ترها بالاتر."""
    by_date=sorted(unmatched,key=lambda x:x.get("last",""),reverse=True)
    return sorted(by_date,key=lambda x:-x.get("count",1))

def unmatched_by_id(uid):
    return next((x for x in unmatched if x.get("id")==uid),None)

async def load_faq():
    global faq
    data=await _rj(FAQ_FILE,list)
    faq=[x for x in data if isinstance(x,dict) and (x.get("answer") or x.get("action"))] \
        if isinstance(data,list) else []
    await seed_intents()
    logger.info(f"faq: {len(faq)} نیت/سؤال آماده")

async def save_faq(): return await _wj(FAQ_FILE,faq)

def faq_item(fid): return next((x for x in faq if x.get("id")==fid),None)

def strip_button_links(text,key):
    """هر لینکی که دکمه شده از متن پنهان می‌شود — دکمه جای لینک آبی را
    گرفته و نگه داشتن هر دو فقط شلوغی است. غیرمخرب: متن اصلی می‌ماند."""
    return _strip_link_list(text,[u for _,u in section_links(key)])

def strip_text_links(text):
    """فقط لینک‌های خودِ متن — برای جاهایی که بخش (key) در کار نیست، مثل FAQ."""
    return _strip_link_list(text,[])

def _strip_link_list(text,urls):
    # لینک‌هایی که در خود متن بودند هم باید بروند حتی اگر شکل کوتاه نوشته شده‌اند
    urls=list(urls)+[m.group(0) for m in _ANY_URL_RE.finditer(text or "")]
    if not urls: return text
    parts=[]
    for u in urls:
        parts.append(re.escape(u.rstrip("/")))
        parts.append(re.escape(re.sub(r"^https?://(?:www\.)?","",u).rstrip("/")))
    rx=re.compile(r"(?:https?://)?(?:www\.)?(?:"+"|".join(parts)+r")/?",re.IGNORECASE)
    return _strip_urls(text,rx)

def place_active(key):
    pl=places.get(key) or {}
    return bool(pl.get("active") and pl.get("lat") is not None and pl.get("lon") is not None)

async def send_place(msg,key,kb=None):
    """کارت نقشه‌ی بومی تلگرام برای این بخش.

    sendVenue نه caption می‌پذیرد نه photo (محدودیت Bot API)، ولی reply_markup
    می‌پذیرد — پس دکمه‌های خود بخش زیر همین کارت می‌نشینند و همه‌چیز در یک
    پیام واحد جمع می‌شود: نقشه + نام + آدرس + دکمه‌ها.
    """
    if not place_active(key): return False
    pl=places[key]
    try:
        await msg.reply_venue(latitude=float(pl["lat"]),longitude=float(pl["lon"]),
                              title=pl.get("title") or SHOP_NAME,
                              address=pl.get("address") or "",
                              reply_markup=kb)
        return True
    except Exception as e:
        logger.error(f"venue[{key}]: {e}")
        try:
            await msg.reply_location(latitude=float(pl["lat"]),longitude=float(pl["lon"]),
                                     reply_markup=kb)
            return True
        except Exception as e2:
            logger.error(f"location[{key}]: {e2}")
            return False

async def send_place_preview(msg,key):
    pl=places.get(key) or {}
    if pl.get("lat") is None: return
    await msg.reply_venue(latitude=float(pl["lat"]),longitude=float(pl["lon"]),
                          title=pl.get("title") or SHOP_NAME,
                          address=pl.get("address") or "")

async def typing(msg,photo=False):
    """نشانگر «در حال نوشتن» — پاسخ زنده‌تر حس می‌شود."""
    try: await msg.chat.send_action("upload_photo" if photo else "typing")
    except Exception: pass

async def send_banner(msg,text,key,kb=None):
    b=get_banner(key)
    await typing(msg,photo=bool(b.get("active") and b.get("file_id")))
    if b.get("active") and b.get("file_id"):
        try:
            await msg.reply_photo(photo=b["file_id"],caption=_fit(text,CAP_LIMIT),
                                  parse_mode="HTML",reply_markup=kb)
            return
        except Exception as e: logger.error(f"banner[{key}]: {e}")
    await msg.reply_text(_fit(text,TEXT_LIMIT),parse_mode="HTML",
                         reply_markup=kb,disable_web_page_preview=True)

# ════════════════════════════════════════════════
#  BROADCAST — مقاوم در برابر ری‌استارت، زمان‌بندی‌شده، مخاطب‌محور
# ════════════════════════════════════════════════
# کار پخش روی دیسک (broadcast.json) ذخیره می‌شود و پس از هر ۲۰ ارسال
# به‌روزرسانی می‌گردد؛ اگر ربات وسط پخش ری‌استارت شود، از همان نفر بعدی
# ادامه می‌دهد و هیچ‌کس دو بار پیام نمی‌گیرد.
_bc_job: dict = None     # کار جاری
_bc_task = None          # asyncio.Task در حال ارسال
_bc_cancel = False

BC_AUDIENCE = {
    "all":      ("👥 همه‌ی کاربران",   ""),
    "active30": ("🔥 فعال‌های ۳۰ روز",  "AND last_seen>=datetime('now','-30 days','localtime')"),
    "new7":     ("🆕 تازه‌واردهای هفته","AND joined_at>=datetime('now','-7 days','localtime')"),
    "cold90":   ("💤 غایب‌های ۹۰ روز+", "AND last_seen<datetime('now','-90 days','localtime')"),
}

async def bc_uids(aud):
    """فهرست مقصد. بلاک‌شده‌ها، کسانی که ربات را حذف کرده‌اند و خودِ مدیرها
    همیشه بیرون‌اند (مدیر پیش‌نمایش را دیده، لازم نیست دوباره بگیرد)."""
    if aud.startswith("sub:"):
        tid=aud[4:]
        if not topic_item(tid): return []
        async with db.execute(
            "SELECT s.user_id FROM subs s JOIN users u ON u.user_id=s.user_id "
            "WHERE s.topic=? AND u.is_blocked=0 AND u.has_left=0",(tid,)) as c:
            rows=await c.fetchall()
        return [r[0] for r in rows if not is_admin(r[0])]
    if aud.startswith("src:"):
        src=aud[4:]
        if not _SRC_RE.match(src): return []
        async with db.execute(
            "SELECT user_id FROM users WHERE is_blocked=0 AND has_left=0 AND source=?",(src,)) as c:
            rows=await c.fetchall()
    else:
        cond=BC_AUDIENCE.get(aud,BC_AUDIENCE["all"])[1]
        async with db.execute(
            f"SELECT user_id FROM users WHERE is_blocked=0 AND has_left=0 {cond}") as c:
            rows=await c.fetchall()
    return [r[0] for r in rows if not is_admin(r[0])]

def bc_label(aud):
    if aud.startswith("sub:"):
        t=topic_item(aud[4:]); return "🔔 "+(t["title"] if t else aud[4:])
    if aud.startswith("src:"): return "🎯 "+SOURCE_LABELS.get(aud[4:],aud[4:])
    return BC_AUDIENCE.get(aud,BC_AUDIENCE["all"])[0]

async def bc_save():
    if _bc_job is None:
        try: os.unlink(BROADCAST_FILE)
        except FileNotFoundError: pass
        except Exception as e: logger.error(f"bc unlink: {e}")
        return True
    return await _wj(BROADCAST_FILE,_bc_job)

async def bc_load():
    global _bc_job
    d=await _rj(BROADCAST_FILE,lambda:None)
    if isinstance(d,dict) and isinstance(d.get("queue"),list) and d.get("status") in ("pending","running"):
        _bc_job=d
        logger.info(f"broadcast: کار نیمه‌تمام بازیابی شد — {d.get('i',0)}/{len(d['queue'])}")
    else:
        _bc_job=None

def bc_when_text(ts):
    t=datetime.fromtimestamp(ts,IRAN_TZ)
    j=jdatetime.datetime.fromgregorian(datetime=t)
    return f"{to_fa(j.day)} {MONTH_FA[j.month]} ساعت {to_fa(t.strftime('%H:%M'))}"

def bc_status_text():
    """خلاصه‌ی کار جاری برای صفحه‌ی پخش."""
    j=_bc_job
    if not j: return None
    n=len(j["queue"])
    if j["status"]=="pending" and j.get("run_at"):
        return (f"<b>⏰ پخش زمان‌بندی‌شده</b>\n{HR}\n"
                f"🎯 {esc(bc_label(j['audience']))} — {to_fa(n)} نفر\n"
                f"🕐 ارسال در {esc(bc_when_text(j['run_at']))}\n\n"
                f"{esc(_fit(j['text'] or '🖼 (تصویر)',300))}")
    return (f"<b>📢 پخش در حال اجرا</b>\n{HR}\n"
            f"🎯 {esc(bc_label(j['audience']))}\n"
            f"✔️ {to_fa(j['ok'])}  ❌ {to_fa(j['fail'])}  ·  {to_fa(j['i'])}/{to_fa(n)}")

def bc_status_kb():
    j=_bc_job
    if not j: return InlineKeyboardMarkup(_nav())
    cb="bc_kill" if j["status"]=="pending" else "bc_stop"
    lbl="🗑 لغو پخش زمان‌بندی‌شده" if j["status"]=="pending" else "🛑 توقف پخش"
    return InlineKeyboardMarkup(_nav([InlineKeyboardButton(lbl,callback_data=cb)],
                                     [InlineKeyboardButton("🔄 بروزرسانی",callback_data="broadcast")]))

async def bc_aud_kb():
    """انتخاب مخاطب — تعداد هر گروه کنار نامش."""
    rows=[]
    for k,(lbl,_) in BC_AUDIENCE.items():
        rows.append([InlineKeyboardButton(f"{lbl} · {to_fa(len(await bc_uids(k)))}",
                                          callback_data=f"bc_aud_{k}")])
    for t in topics:
        n=await sub_count(t["id"])
        if n: rows.append([InlineKeyboardButton(
            f"🔔 {t['title']} · {to_fa(n)}",callback_data=f"bc_aud_sub:{t['id']}")])
    for src,cnt in await source_stats():
        if src and src!="—" and cnt:
            n=len(await bc_uids("src:"+src))
            if n: rows.append([InlineKeyboardButton(
                f"🎯 {SOURCE_LABELS.get(src,src)} · {to_fa(n)}",callback_data=f"bc_aud_src:{src}")])
    return InlineKeyboardMarkup(_nav(*rows))

def bc_confirm_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ارسال فوری",callback_data="bc_go")],
        [InlineKeyboardButton("⏰ زمان‌بندی",callback_data="bc_when")],
        [InlineKeyboardButton("↩️ انصراف",callback_data="bc_no")]])

def bc_when_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏰ ۱ ساعت دیگر",callback_data="bc_in_60"),
         InlineKeyboardButton("⏰ ۳ ساعت دیگر",callback_data="bc_in_180")],
        [InlineKeyboardButton("🌅 فردا ساعت ۱۰:۰۰",callback_data="bc_in_t10"),
         InlineKeyboardButton("🕐 ساعت دلخواه",callback_data="bc_in_ask")],
        [InlineKeyboardButton("↩️ انصراف",callback_data="bc_no")]])

def bc_next_at(hh,mm):
    """نزدیک‌ترین رخداد بعدیِ این ساعت به وقت تهران."""
    now=datetime.now(IRAN_TZ)
    t=now.replace(hour=hh,minute=mm,second=0,microsecond=0)
    if t<=now: t+=timedelta(days=1)
    return t.timestamp()

async def bc_create(ctx,by,run_at=None):
    """ساخت کار پخش از پیش‌نویسِ داخل user_data."""
    global _bc_job
    aud=ctx.user_data.get("bc_aud","all")
    queue=await bc_uids(aud)
    _bc_job={"id":secrets.token_hex(4),"text":ctx.user_data.get("bc_text","") or "",
             "photo":ctx.user_data.get("bc_photo"),"audience":aud,"queue":queue,
             "i":0,"ok":0,"fail":0,"gone":0,"by":by,"run_at":run_at,
             "status":"pending" if run_at else "running",
             "created":gregorian_now(),"msg_id":None}
    for k in ("bc_aud","bc_text","bc_photo"): ctx.user_data.pop(k,None)
    await bc_save()
    return _bc_job

def bc_start(bot):
    global _bc_task
    if _bc_task is None or _bc_task.done():
        _bc_task=asyncio.ensure_future(bc_run(bot))

async def bc_run(bot):
    """ارسال از همان نفری که مانده بود. تنها جایی که _bc_job پاک می‌شود."""
    global _bc_job,_bc_cancel
    job=_bc_job
    if not job: return
    job["status"]="running"; _bc_cancel=False
    q=job["queue"]; total=len(q)
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 توقف پخش",callback_data="bc_stop")]])

    async def status(txt,markup=kb):
        try:
            if job.get("msg_id"):
                await bot.edit_message_text(txt,chat_id=job["by"],
                                            message_id=job["msg_id"],reply_markup=markup)
            else:
                m=await bot.send_message(job["by"],txt,reply_markup=markup)
                job["msg_id"]=m.message_id
        except Exception: pass

    async def send_one(uid):
        if job["photo"]:
            await bot.send_photo(uid,photo=job["photo"],caption=job["text"] or None)
        else:
            await bot.send_message(uid,job["text"])

    await status(f"📢 در حال ارسال به {to_fa(total)} نفر…")
    try:
        while job["i"]<total:
            if _bc_cancel:
                job["status"]="canceled"
                _bc_job=None; _bc_cancel=False; await bc_save()
                await status(f"🛑 پخش متوقف شد\n✔️ {to_fa(job['ok'])}  ❌ {to_fa(job['fail'])}",None)
                return
            uid=q[job["i"]]
            try:
                await send_one(uid); job["ok"]+=1
            except Forbidden:
                # ربات را بلاک/حذف کرده — علامت بزن تا پخش‌های بعدی وقت تلف نکنند
                job["gone"]+=1; job["fail"]+=1
                await mark_left(uid)
            except Exception as e:
                retry=getattr(e,"retry_after",None)
                if retry:
                    await asyncio.sleep(float(retry)+1)
                    try: await send_one(uid); job["ok"]+=1
                    except Exception: job["fail"]+=1
                else: job["fail"]+=1
            job["i"]+=1
            await asyncio.sleep(0.05)   # همیشه — وگرنه زنجیره‌ی خطا API را می‌کوبد
            if job["i"]%20==0 or job["i"]==total:
                await bc_save()
                await status(f"📢 {to_fa(job['ok'])}✔️ {to_fa(job['fail'])}❌  "
                             f"{to_fa(job['i'])}/{to_fa(total)}",
                             kb if job["i"]<total else None)
    except asyncio.CancelledError:
        await bc_save(); raise
    except Exception as e:
        # کار پاک نمی‌شود تا حلقه‌ی زمان‌بند دوباره از همین‌جا ادامه دهد
        logger.error(f"broadcast: {e}",exc_info=True)
        await bc_save()
        await status(f"⚠️ پخش موقتاً متوقف شد ({to_fa(job['i'])}/{to_fa(total)}) — "
                     f"خودکار ادامه پیدا می‌کند.",None)
        return
    job["status"]="done"
    summary=(f"✅ پخش تمام شد\n"
             f"🎯 {bc_label(job['audience'])}\n"
             f"✔️ رسید: {to_fa(job['ok'])}   ❌ نرسید: {to_fa(job['fail'])}")
    if job["gone"]:
        summary+=(f"\n🚪 {to_fa(job['gone'])} نفر ربات را بلاک/حذف کرده بودند — "
                  f"از فهرست پخش کنار گذاشته شدند.")
    _bc_job=None; _bc_cancel=False; await bc_save()
    await status(summary,None)

_BC_MAX_TRIES = 5   # سقف تلاش برای یک کار — جلوگیری از حلقه‌ی بی‌پایان

async def _bc_loop(bot):
    """هر ۲۰ ثانیه: کارِ نیمه‌تمام را از سر بگیر، کارِ زمان‌بندی‌شده را سر وقت اجرا کن."""
    global _bc_job
    await asyncio.sleep(8)          # بگذار راه‌اندازی کامل شود
    announced=set(); tries={}
    while True:
        try:
            job=_bc_job
            if job and (_bc_task is None or _bc_task.done()):
                if not job.get("run_at") or time.time()>=job["run_at"]:
                    n=tries[job["id"]]=tries.get(job["id"],0)+1
                    if n>_BC_MAX_TRIES:
                        # کاری که پشت‌سرهم می‌ترکد نباید تا ابد تلاش کند
                        logger.error(f"broadcast {job['id']}: بعد از {n-1} تلاش رها شد")
                        left=len(job["queue"])-job["i"]
                        by=job["by"]; _bc_job=None; await bc_save()
                        try: await bot.send_message(by,
                            f"⚠️ پخش بعد از چند تلاش ناموفق رها شد — "
                            f"{to_fa(left)} نفر باقی مانده بودند. لطفاً دوباره امتحان کنید.")
                        except Exception: pass
                        continue
                    if job["i"]>0 and job["id"] not in announced:
                        announced.add(job["id"])
                        try: await bot.send_message(job["by"],
                            f"♻️ پخش نیمه‌تمام از سر گرفته شد "
                            f"({to_fa(job['i'])}/{to_fa(len(job['queue']))}).")
                        except Exception: pass
                    job["msg_id"]=None
                    bc_start(bot)
        except Exception as e: logger.error(f"bc_loop: {e}")
        await asyncio.sleep(20)

# ── backup
_backup_registry: list = []  # [{"msg_id": int, "file_id": str, "date": str}]
MAX_BACKUPS = 5

async def load_backup_registry():
    """لیست بکاپ‌های خودکار باید ری‌استارت را دوام بیاورد — وگرنه دقیقاً وقتی
    به بازگردانی نیاز دارید (بعد از کرش) لیست خالی است."""
    global _backup_registry
    data = await _rj(BACKUPS_FILE, list)
    if isinstance(data, list): _backup_registry = data
    logger.info(f"backups: {len(_backup_registry)} بکاپ خودکار بارگذاری شد")

async def save_backup_registry(): await _wj(BACKUPS_FILE, _backup_registry)

async def send_backup(bot,label="بک‌آپ"):
    global _backup_registry
    ts=shamsi_now().replace(" ","_").replace("—","-").replace(":","-")
    buf=io.BytesIO()
    files=[(DATA_FILE,"data.json"),(BANNER_FILE,"banner.json"),(WORKHOURS_FILE,"workhours.json"),
           (BUTTONS_FILE,"buttons.json"),(SETTINGS_FILE,"settings.json"),(STATS_FILE,"stats.json"),
           (MENU_FILE,"menu.json"),(PLACES_FILE,"places.json"),(ADMINS_FILE,"admins.json"),
           (FAQ_FILE,"faq.json"),(UNMATCHED_FILE,"unmatched.json"),
           (PAGES_FILE,"pages.json"),(TOPICS_FILE,"topics.json"),(DB_FILE,"users.db")]
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as zf:
        for fp,name in files:
            try:
                async with aiofiles.open(fp,"rb") as f: zf.writestr(name,await f.read())
            except Exception as e: logger.warning(f"backup skip {fp}: {e}")
    buf.seek(0)
    msg=await bot.send_document(OWNER_ID,document=buf,filename=f"backup_{ts}.zip",
                                caption=f"💾 {label} — {shamsi_now()}")
    _backup_registry.append({"msg_id":msg.message_id,"file_id":msg.document.file_id,"date":shamsi_now()})
    # اگر بیشتر از MAX_BACKUPS داریم، قدیمی‌ترین را حذف کن
    while len(_backup_registry)>MAX_BACKUPS:
        old=_backup_registry.pop(0)
        try: await bot.delete_message(OWNER_ID,old["msg_id"])
        except Exception as e: logger.debug(f"backup delete old: {e}")
    await save_backup_registry()

BACKUP_WEEKDAY = 6       # جمعه (در jdatetime: ۰=شنبه … ۶=جمعه)
BACKUP_HOUR    = 3       # ۳ بامداد به وقت تهران
BACKUP_MAX_GAP = 7       # اگر ربات جمعه خاموش بود، بیشتر از این تعداد روز نگذرد

def _backup_due(now):
    """آیا وقت بکاپ هفتگی است؟

    تاریخِ آخرین بکاپ در settings.json می‌ماند، پس ری‌استارت باعث نمی‌شود
    دوباره بکاپ بیاید — قبلاً این حالت در حافظه بود و هر ری‌استارت بعد از
    ساعت هدف، یک بکاپ تکراری می‌فرستاد.
    """
    today=now.strftime("%Y-%m-%d")
    last=settings.get("last_auto_backup") or ""
    if last==today: return False,today
    j=jdatetime.datetime.fromgregorian(datetime=now)
    if j.weekday()==BACKUP_WEEKDAY and now.hour>=BACKUP_HOUR: return True,today
    # اگر ربات روز مقرر خاموش بوده، بکاپ نباید بی‌نهایت عقب بیفتد
    try:
        if not last: return True,today
        gap=(now.date()-datetime.strptime(last,"%Y-%m-%d").date()).days
        if gap>=BACKUP_MAX_GAP: return True,today
    except Exception:
        return True,today
    return False,today

async def weekly_digest():
    """خلاصه‌ی هفته برای مالک — کنار بکاپ جمعه می‌رود.

    رسیدنش خودش یعنی ربات زنده است؛ و آن خط آخر مستقیم می‌گوید سؤال
    آماده‌ی بعدی را درباره‌ی چه بنویسی.
    """
    since="-7 days"
    newu=await _cnt("SELECT COUNT(*) FROM users WHERE joined_at>=datetime('now',?,'localtime')",(since,))
    act =await _cnt("SELECT COUNT(*) FROM users WHERE last_seen>=datetime('now',?,'localtime')",(since,))
    msgs=await _cnt("SELECT COUNT(*) FROM events WHERE key=? AND ts>=datetime('now',?,'localtime')",
                    (EV_MSG,since))
    openn=await open_count()
    out=[f"<b>📊 هفته‌ی گذشته — {esc(shamsi_now().split('—')[0].strip())}</b>",HR,
         f"🆕 {to_fa(newu)} مشتری جدید  ·  📅 {to_fa(act)} فعال  ·  💬 {to_fa(msgs)} پیام"]
    if openn: out.append(f"⏳ {to_fa(openn)} پیام هنوز بی‌جواب")
    async with db.execute(
        "SELECT key,COUNT(*) c FROM events WHERE key<>? AND ts>=datetime('now',?,'localtime') "
        "GROUP BY key ORDER BY c DESC LIMIT 3",(EV_MSG,since)) as c:
        tops=await c.fetchall()
    if tops:
        out.append("👀 پربازدید: "+"، ".join(
            f"{event_label(k)} ({to_fa(n)})"
            for k,n in tops))
    srcs=[r for r in await source_stats() if r[0]!="—"]
    if srcs: out.append("🎯 بیشترین ورودی: "+SOURCE_LABELS.get(srcs[0][0],srcs[0][0]))
    if topics:
        subs=[(t["title"],await sub_count(t["id"])) for t in topics]
        subs=[x for x in subs if x[1]]
        if subs:
            out.append("🔔 مشترک‌ها: "+"، ".join(f"{t} ({to_fa(n)})" for t,n in subs))
    hot=[u for u in unmatched_sorted() if u.get("count",1)>1][:1]
    if hot:
        out += [HR,f"❓ پرتکرارترین سؤال بی‌پاسخ: «{esc(_fit(hot[0]['text'],60))}» "
                   f"×{to_fa(hot[0].get('count',1))}",
                "برایش یک سؤال آماده بنویسید تا از این به بعد خودکار جواب بگیرد."]
    return _fit("\n".join(out),TEXT_LIMIT)

async def _auto_backup_loop(bot):
    """هفته‌ای یک‌بار — جمعه ساعت ۳ بامداد به وقت تهران."""
    await asyncio.sleep(60)          # بگذار راه‌اندازی تمام شود
    while True:
        try:
            due,today=_backup_due(datetime.now(IRAN_TZ))
            if due:
                await send_backup(bot,label="بک‌آپ هفتگی")
                settings["last_auto_backup"]=today; await save_settings()
                logger.info("✅ بکاپ هفتگی ارسال شد")
                if get_setting("weekly_digest"):
                    try:
                        await bot.send_message(OWNER_ID,await weekly_digest(),
                                               parse_mode="HTML")
                    except Exception as e: logger.error(f"digest: {e}")
        except Exception as e:
            logger.error(f"auto_backup: {e}")
        await asyncio.sleep(1800)

BACKUP_MAP = {"data.json":DATA_FILE,"banner.json":BANNER_FILE,"workhours.json":WORKHOURS_FILE,
              "buttons.json":BUTTONS_FILE,"settings.json":SETTINGS_FILE,"stats.json":STATS_FILE,
              "menu.json":MENU_FILE,"places.json":PLACES_FILE,"admins.json":ADMINS_FILE,
              "faq.json":FAQ_FILE,"unmatched.json":UNMATCHED_FILE,
              "pages.json":PAGES_FILE,"topics.json":TOPICS_FILE,"users.db":DB_FILE}
SQLITE_MAGIC = b"SQLite format 3\x00"
MAX_RESTORE_BYTES = 200 * 1024 * 1024   # سقف ایمنی برای فایل‌های داخل ZIP

async def _safety_snapshot():
    """قبل از بازگردانی، وضعیت فعلی را کنار می‌گذارد تا اگر بکاپ خراب بود برگردیم."""
    path = os.path.join(os.path.dirname(os.path.abspath(DB_FILE)), "pre_restore.zip")
    try:
        with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as zf:
            for name,fp in BACKUP_MAP.items():
                if os.path.exists(fp): zf.write(fp,name)
        return path
    except Exception as e:
        logger.warning(f"safety snapshot ناموفق: {e}"); return None

async def restore_backup(bot,file_id):
    """بازگردانی بکاپ.

    نکته حیاتی: users.db در حالت WAL باز است. اگر فایل را زیر پای اتصالِ باز
    عوض کنیم، فایل‌های users.db-wal / -shm قدیمی روی داده‌ی تازه اعمال می‌شوند
    و بازگردانی عملاً بی‌اثر می‌ماند. پس باید اتصال بسته، WAL پاک، و دوباره
    باز شود.
    """
    global db, _seen_uids, _block_cache
    try:
        f=await bot.get_file(file_id); buf=io.BytesIO()
        await f.download_to_memory(buf); buf.seek(0)
        with zipfile.ZipFile(buf,"r") as zf:
            members=[i for i in zf.infolist() if i.filename in BACKUP_MAP]
            if not members:
                return False,"این فایل ZIP هیچ‌کدام از فایل‌های بکاپ را ندارد."
            total=sum(i.file_size for i in members)
            if total>MAX_RESTORE_BYTES:
                return False,f"حجم بکاپ غیرعادی است ({total//1024//1024} مگابایت) — بازگردانی انجام نشد."
            payload={i.filename:zf.read(i.filename) for i in members}

        # اعتبارسنجی پیش از دست‌زدن به هر فایلی
        if "users.db" in payload and not payload["users.db"].startswith(SQLITE_MAGIC):
            return False,"فایل users.db داخل ZIP یک دیتابیس معتبر نیست."
        for name in ("data.json","banner.json","workhours.json","buttons.json","settings.json","stats.json","menu.json","places.json"):
            if name in payload:
                try: json.loads(payload[name].decode("utf-8"))
                except Exception: return False,f"فایل {name} داخل ZIP خراب است."

        snapshot=await _safety_snapshot()

        # اتصال را ببند تا جایگزینی users.db امن باشد
        if "users.db" in payload and db is not None:
            try: await db.close()
            except Exception as e: logger.warning(f"بستن دیتابیس: {e}")
            db=None

        restored=[]
        for name,data_bytes in payload.items():
            async with aiofiles.open(BACKUP_MAP[name],"wb") as out: await out.write(data_bytes)
            restored.append(name)

        if "users.db" in payload:
            # WAL/SHM قدیمی متعلق به دیتابیس قبلی‌اند و باید بروند
            for suffix in ("-wal","-shm"):
                try: os.remove(DB_FILE+suffix)
                except FileNotFoundError: pass
                except Exception as e: logger.warning(f"حذف {DB_FILE+suffix}: {e}")
            _seen_uids={}; _block_cache={}
            await init_db()

        await load_pages(); await load_topics()
        await load_data(); await load_banners(); await load_workhours()
        await load_buttons(); await load_settings(); await load_stats(); await load_menu(); await load_places()
        # از فایل‌های تازه دوباره خوانده شوند
        await load_admins(); await load_faq(); await load_unmatched()
        # نرمال‌سازی فرمت فایل‌ها روی دیسک (جلوگیری از مشکل فرمت قدیمی بعد از restart)
        await save_banners(); await save_buttons()
        if snapshot: logger.info(f"بکاپ ایمنی پیش از بازگردانی: {snapshot}")
        return True,restored
    except Exception as e:
        logger.error(f"restore: {e}",exc_info=True)
        # اگر اتصال بسته مانده، دوباره بازش کن تا ربات فلج نشود
        if db is None:
            try: await init_db()
            except Exception as e2: logger.error(f"بازگشایی دیتابیس ناموفق: {e2}")
        return False,str(e)

# ════════════════════════════════════════════════
#  HANDLERS — cmd_start / cmd_admin
# ════════════════════════════════════════════════
def merge_kb(kb,rows):
    """دکمه‌های لینکِ بخش + دکمه‌های پیشنهادیِ دستیار در یک کیبورد.
    تلگرام به هر پیام فقط یک کیبورد inline می‌دهد، پس باید یکی شوند."""
    rows=[r for r in (rows or []) if r]
    if not rows: return kb
    base=[list(r) for r in kb.inline_keyboard] if kb else []
    return InlineKeyboardMarkup(base+rows)

async def send_section(msg,key,title=None,uid=None,extra_rows=None):
    """کارت یک بخش — از منو، از لینک مستقیم، یا از دستیار؛ همه همین‌جا."""
    await record_stat(key,uid)
    title=title or SECTION_NAMES.get(key,key)
    kb=merge_kb(user_sec_kb(key),extra_rows)
    # لوکیشن فعال → یک کارت واحد: نقشه + نام + آدرس + دکمه‌های بخش.
    # (تلگرام اجازه نمی‌دهد venue همراه عکس یا caption باشد، پس همین کارت
    #  جای متن و بنر را می‌گیرد.)
    if place_active(key) and await send_place(msg,key,kb=kb):
        return
    content=strip_button_links(responses.get(key,"") or "",key)
    if not content.strip() and section_links(key):
        content="از دکمه‌های زیر استفاده کنید 👇"
    await send_banner(msg,build_msg(title,content,key),key,kb=kb)

async def notify_kb(uid):
    mine=await user_subs(uid)
    rows=[[InlineKeyboardButton(("✅ " if t["id"] in mine else "➕ ")+t["title"],
                                callback_data=f"sub_{t['id']}")] for t in topics]
    return InlineKeyboardMarkup(rows) if rows else None

async def send_notify(msg,uid,title=None):
    """صفحه‌ی اطلاع‌رسانی — کاربر خودش انتخاب می‌کند از چه چیزی خبردار شود."""
    await record_stat("notify",uid)
    kb=await notify_kb(uid)
    if not kb:
        await msg.reply_text("فعلاً موضوعی برای اطلاع‌رسانی تنظیم نشده.",
                             reply_markup=main_menu()); return
    body=strip_button_links(responses.get("notify","") or "","notify")
    if not body.strip():
        body=("از چه چیزی خبردار شوید؟ روی هرکدام بزنید تا روشن یا خاموش شود.\n"
              "هر وقت خواستید می‌توانید لغوش کنید — و ما فقط درباره‌ی همین‌ها "
              "پیام می‌دهیم، نه بیشتر.")
    await send_banner(msg,build_msg(title or SECTION_NAMES["notify"],body,"notify"),
                      "notify",kb=kb)

# ── لینک‌های ورودی
BOT_USERNAME = ""        # در post_init پر می‌شود

def deep_link(src="",section=""):
    u=BOT_USERNAME or "<نام‌ربات>"
    arg=(src or "")+(f"-{section}" if section else "")
    return f"https://t.me/{u}?start={arg}" if arg else f"https://t.me/{u}"

def parse_start_arg(arg):
    """«insta» → فقط منبع.  «insta-3» → منبع + بخشی که باید باز شود.

    کلیدِ بخش‌های سفارشی «p_xxxx» است و خط تیره ندارد، پس اولین «-» مرز
    امنی بین منبع و بخش است.
    """
    src,_,sec=(arg or "").partition("-")
    if sec not in SECTION_NAMES or sec in ("welcome",): sec=""
    return src,sec

async def cmd_start(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    user=update.effective_user; is_new=False
    async with db.execute("SELECT user_id FROM users WHERE user_id=?",(user.id,)) as c: is_new=(await c.fetchone()) is None
    await save_user(user)
    await mark_left(user.id,0)   # اگر قبلاً ربات را بلاک کرده بود و برگشته، دوباره فعالش کن
    # t.me/<bot>?start=insta      → می‌فهمیم مشتری از کجا آمده
    # t.me/<bot>?start=insta-3     → علاوه بر منبع، مستقیم همان بخش باز می‌شود
    deep_sec=""
    if getattr(ctx,"args",None):
        src,deep_sec=parse_start_arg(ctx.args[0])
        if src: await set_source(user.id,src)
    if get_setting("notify_new_user") and is_new:
        await notify_admins(ctx.bot,
            f"🆕 کاربر جدید!\n👤 {user.first_name or'—'}\n"
            f"{'@'+user.username if user.username else'—'}\n🆔 {user.id}")
    name=(user.first_name or "").strip()
    wt=strip_button_links(responses.get("welcome","") or "","welcome")
    head=f"سلام {esc(name)} 👋" if name else "سلام 👋"
    parts=[f"<b>{head}</b>",f"به <b>{esc(SHOP_NAME)}</b> خوش آمدید",HR]
    st=status_line()
    if st: parts.append(st)
    if wt: parts += ["",esc(wt)]
    if not get_setting("assistant"): parts += ["","از منوی پایین انتخاب کنید 👇"]
    full=_fit("\n".join(parts),TEXT_LIMIT)
    # منوی پایین همیشه باید ست شود — تلگرام هر پیام را فقط با یک نوع کیبورد
    # می‌پذیرد، پس اگر بخش خوش‌آمد لینک داشته باشد، لینک‌ها جدا می‌روند.
    await send_banner(update.message,full,"welcome",kb=main_menu())
    links=user_sec_kb("welcome")
    if links:
        await update.message.reply_text("🔗 دسترسی سریع:",reply_markup=links)
    if get_setting("assistant") and get_setting("faq_auto") and not deep_sec:
        await send_assistant_intro(update.message,ctx.bot)
    # لینک استوری اینستاگرام درباره‌ی اقساط بود؟ همان کارت را باز کن،
    # نه اینکه مشتری دنبال دکمه‌اش بگردد.
    if deep_sec=="notify":
        await send_notify(update.message,user.id)
    elif deep_sec:
        await send_section(update.message,deep_sec,uid=user.id)

# کارت معرفی دستیار — بعد از خوش‌آمد. مشتری باید از همان اول بفهمد لازم نیست
# دنبال دکمه بگردد: می‌تواند مثل چت با یک آدم بنویسد.
ASSIST_INTRO = ("🤖 <b>دستیار هوشمند {shop}</b>\n{hr}\n"
                "سلام! من دستیار هوشمند فروشگاهم و هر ساعتی از شبانه‌روز جوابتون رو "
                "می‌دم ⚡️\n\n"
                "لازم نیست دنبال دکمه بگردید؛ سؤالتون رو <b>همین پایین تایپ کنید</b>، "
                "مثل چت با یک آدم:\n\n"
                "💬 <i>«سلام، آیفون ۱۳ پرو قیمتش چنده؟»</i>\n"
                "💬 <i>«قسطی با چک میشه خرید؟»</i>\n"
                "💬 <i>«گوشی خودمو معاوضه می‌کنید؟»</i>\n\n"
                "هر جا لازم باشه، همکارهام همین‌جا وارد گفتگو می‌شن 🙋‍♂️\n\n"
                "یا یکی از این‌ها رو بزنید 👇")
INTRO_QUICK = (("💰 قیمت‌های امروز","i_price"),("💳 شرایط اقساط","i_install"),
               ("🔄 معاوضه","i_tradein"),("📍 آدرس و ساعت","i_address"))

async def send_assistant_intro(msg,bot):
    btns=[InlineKeyboardButton(t,callback_data=f"ai_{i}") for t,i in INTRO_QUICK
          if (it:=faq_item(i)) and it.get("enabled",True)]
    rows=[btns[i:i+2] for i in range(0,len(btns),2)]
    await _typing(bot,msg.chat_id,200)
    try:
        await msg.reply_text(ASSIST_INTRO.format(shop=esc(SHOP_NAME),hr=HR),parse_mode="HTML",
                             reply_markup=InlineKeyboardMarkup(rows) if rows else main_menu())
    except Exception as e: logger.warning(f"assistant intro: {e}")

async def cmd_help(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    st=status_line()
    body=[]
    if st: body += [st,""]
    if get_setting("assistant") and get_setting("faq_auto"):
        body += ["🤖 <b>دستیار هوشمند</b>",
                 "سؤالتون رو مثل چت با یک آدم همین‌جا تایپ کنید — قیمت، اقساط، "
                 "گارانتی، رجیستری، معاوضه، ارسال، آدرس و… دستیار همون لحظه جواب "
                 "می‌ده و هر جا لازم باشه همکارهامون وارد گفتگو می‌شن.","",
                 "📎 عکس و ویس هم مستقیم به همکاران ما می‌رسد.",""]
    else:
        body += ["از منوی پایین صفحه، بخش موردنظرتان را انتخاب کنید.","",
                 "💬 <b>سؤالی دارید؟</b>",
                 "همین‌جا بنویسید — متن، عکس یا ویس. پیام شما مستقیم به همکاران ما "
                 "می‌رسد و پاسخ را در همین گفتگو می‌گیرید.",""]
    body += [
             "🔄 /start — نمایش دوباره‌ی منو"]
    await update.message.reply_text(
        _fit(f"<b>ℹ️ راهنمای {esc(SHOP_NAME)}</b>\n{HR}\n"+"\n".join(body),TEXT_LIMIT),
        parse_mode="HTML",reply_markup=main_menu(),disable_web_page_preview=True)

async def cmd_badword(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    """/badword — فهرست کلمه‌هایی که مدیر خودش اضافه کرده
    /badword کلمه — افزودن  ·  /badword - کلمه — حذف"""
    if not is_admin(update.effective_user.id): return
    extra=settings.setdefault("bad_words_extra",[])
    args=list(getattr(ctx,"args",None) or [])
    if not args:
        lst="\n".join(f"• {esc(w)}" for w in extra) or "— هنوز چیزی اضافه نکرده‌اید"
        return await update.message.reply_text(
            f"<b>🛡 کلمه‌های توهین‌آمیزِ افزوده</b>\n{HR}\n"
            f"فهرست اصلی (صدها کلمه و عبارت فارسی، فینگلیش و انگلیسی) داخل ربات است؛ "
            f"اینجا فقط چیزهایی است که خودتان اضافه کرده‌اید.\n\n{lst}\n\n"
            "➕ <code>/badword کلمه</code>\n➖ <code>/badword - کلمه</code>",parse_mode="HTML")
    remove=args[0] in ("-","حذف")
    word=" ".join(args[1:] if remove else args).strip()
    if not word: return await update.message.reply_text("کلمه را بعد از دستور بنویسید.")
    if remove:
        if word in extra: extra.remove(word); await save_settings()
        return await update.message.reply_text(f"➖ «{word}» برداشته شد.")
    if word not in extra: extra.append(word); await save_settings()
    await update.message.reply_text(f"➕ «{word}» اضافه شد — از این به بعد تذکر می‌گیرد.")

async def cmd_test(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    """/test — مدیر مثل مشتری با دستیار حرف بزند (روشن/خاموش)."""
    uid=update.effective_user.id
    if not is_admin(uid): return
    if uid in test_mode:
        test_mode.discard(uid)
        return await update.message.reply_text(
            "🧪 حالت آزمایش خاموش شد. برگشتید به حالت مدیر.",reply_markup=main_menu())
    test_mode.add(uid)
    await update.message.reply_text(TEST_HELP,parse_mode="HTML",reply_markup=main_menu())

async def cmd_ask(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    """/ask <جمله> — مدیر ببیند دستیار یک جمله را چطور می‌فهمد، بی‌آنکه چیزی
    ثبت یا برای کسی فرستاده شود."""
    user=update.effective_user
    if not is_admin(user.id): return
    text=" ".join(getattr(ctx,"args",None) or []).strip()
    if not text:
        return await update.message.reply_text(
            "مثال:\n/ask سلام، آیفون ۱۳ قسطی میشه؟\n/ask کجایید؟\n/ask واسه ۱۴ چی؟")
    a=brain.analyze(text,brain_intents())
    it=a["intent"]
    dbg=(f"🔎 فهم دستیار\n"
         f"• نیت: {faq_title(it) if it else '— (به همکار سپرده می‌شود)'}"
         +(f" · امتیاز {a['score']:.2f}" if it else "")+
         (f"\n• محصول: {a['product']}" if a["product"] else "")+
         (f"\n• روزمره: {'، '.join(sorted(a['tags']))}" if a["tags"] else "")+
         ("\n• ادامه‌ی بحث قبلی" if a["followup"] else "")+
         "\n━━━━━━━━━━━━━━━\nجوابی که مشتری می‌گیرد 👇")
    await update.message.reply_text(dbg)
    await assistant_reply(update,ctx,text,user,dry=True)

async def cmd_admin(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ دسترسی ندارید")
    await show_home(update.message,edit=False)

# ════════════════════════════════════════════════
#  USER CALLBACKS
# ════════════════════════════════════════════════
async def user_cb(query,ctx):
    data=query.data

    if data=="wh_weekly":
        table=wh_full_table(); sep="━"*15
        msg=f"{sep}\n📆 ساعت کار هفتگی مجموعه\n{sep}\n{table}\n{sep}"
        kb=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 برگشت",callback_data="wh_back_today")]])
        await query.message.reply_text(msg,reply_markup=kb); return

    if data.startswith("sub_"):
        tid=data[4:]; t=topic_item(tid)
        if not t: return
        on=await sub_toggle(query.from_user.id,tid)
        try:
            await query.message.edit_reply_markup(
                reply_markup=await notify_kb(query.from_user.id))
        except Exception: pass
        try: await query.answer("🔔 خبرتان می‌کنیم" if on else "🔕 دیگر خبر نمی‌دهیم")
        except Exception: pass
        return

    if data.startswith("ai_"):
        it=faq_item(data[3:]); u=query.from_user
        if not it or not it.get("enabled",True): return
        await _typing(ctx.bot,query.message.chat_id)
        await run_intent(query.message,it,u,ctx.bot)
        if (it.get("action") or "")=="human" and not is_admin(u.id):
            await notify_handoff(ctx.bot,u)
        return

    if data=="wh_back_today":
        wh=wh_today_block() or""
        msg=f"🕐 ساعت کاری استوک لند\n{wh}"
        kb=InlineKeyboardMarkup([[InlineKeyboardButton("📆 ساعت کار هفتگی مجموعه",callback_data="wh_weekly")]])
        await safe_edit(query.message,msg,reply_markup=kb); return

# ════════════════════════════════════════════════
#  MAIN CALLBACK DISPATCHER
# ════════════════════════════════════════════════
# پیشوندهایی که هم ادمین هم کاربر دسترسی دارد
_USER_CB_PREFIXES = ("wh_weekly","wh_back_today","sub_","ai_")

async def callbacks(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    global _bc_job,_bc_cancel
    query=update.callback_query
    data=query.data; uid=query.from_user.id

    # ── محافظت اسپم
    if not is_admin(uid):
        _s=spam_check(uid)
        if _s=='block':
            await query.answer(); return
        if _s=='warn':
            await query.answer("🐢 لطفاً کمی آرام‌تر کلیک کنید.",show_alert=True); return
    if not is_admin(uid):
        if await is_blocked(uid):
            await query.answer("⛔ دسترسی شما مسدود شده است."); return

    # ── مسیریابی کاربران — answer یکبار اینجا فراخوانی می‌شه
    if data.startswith(_USER_CB_PREFIXES) or not is_admin(uid):
        # sub_ خودش answer می‌زند تا بازخوردش («خبرتان می‌کنیم») دیده شود؛
        # بقیه همین‌جا یک‌بار answer می‌گیرند.
        if not data.startswith("sub_"): await query.answer()
        try: await user_cb(query,ctx)
        except Exception as e:
            logger.error(f"user_cb uid={uid} data={data}: {e}",exc_info=True)
            try: await query.answer()
            except Exception: pass
            try: await query.message.reply_text("❌ خطا. دوباره امتحان کنید.")
            except Exception: pass
        return

    # ════ ADMIN — هر handler خودش answer می‌زنه تا show_alert درست کار کنه
    try:
        if data in (HOME_CB,"back_to_admin"):
            await query.answer()
            await show_home(query.message)

        elif data=="pending":
            await query.answer()
            rows=await open_list()
            await safe_edit(query.message,await pending_text(),
                            reply_markup=pending_kb(bool(rows)),parse_mode="HTML")

        elif data=="pend_ping":
            n=await ping_open(ctx.bot,uid)
            await query.answer(f"{to_fa(n)} پیام در چت بالا آمد." if n
                               else "پیام بی‌جوابی نیست.",show_alert=True)

        elif data=="tp_menu":
            await query.answer()
            await safe_edit(query.message,await topics_text(),
                            reply_markup=topics_kb(),parse_mode="HTML")

        elif data=="tp_add":
            await query.answer()
            ctx.user_data["mode"]="tp_add"
            await query.message.reply_text(
                "🔔 نام موضوع را بنویسید — همان چیزی که کاربر می‌بیند.\n\n"
                "مثال:  💰 لیست قیمت تازه",reply_markup=cancel_menu())

        elif data.startswith("tp_dl_"):
            tid=data[6:]; t=topic_item(tid)
            if not t: await query.answer("یافت نشد!",show_alert=True); return
            topics[:] = [x for x in topics if x["id"]!=tid]
            await db.execute("DELETE FROM subs WHERE topic=?",(tid,)); await db.commit()
            await save_topics()
            await query.answer("🗑 موضوع و مشترک‌هایش حذف شد.",show_alert=True)
            await safe_edit(query.message,await topics_text(),
                            reply_markup=topics_kb(),parse_mode="HTML")

        elif data=="faq_test":
            on=uid not in test_mode
            (test_mode.add if on else test_mode.discard)(uid)
            await query.answer("🧪 روشن شد — مثل مشتری بنویسید" if on else "🧪 خاموش شد")
            await safe_edit(query.message,faq_menu_text(),
                            reply_markup=faq_menu_kb(uid),parse_mode="HTML")
            if on: await query.message.reply_text(TEST_HELP,parse_mode="HTML",reply_markup=main_menu())

        elif data=="faq_menu":
            await query.answer()
            await safe_edit(query.message,faq_menu_text(),
                            reply_markup=faq_menu_kb(uid),parse_mode="HTML")

        elif data=="faq_add":
            await query.answer()
            ctx.user_data.update({"mode":"faq_keys","faq_id":None})
            await query.message.reply_text(
                "🔑 کلیدواژه‌ها را با کاما بنویسید — هر کدام در پیام مشتری باشد، "
                "این پاسخ می‌رود.\n\nمثال:  گارانتی، ضمانت، وارانتی",
                reply_markup=cancel_menu())

        elif data.startswith("faq_v_"):
            it=faq_item(data[6:])
            if not it: await query.answer("یافت نشد!",show_alert=True); return
            await query.answer()
            await safe_edit(query.message,faq_view_text(it),
                            reply_markup=faq_view_kb(it),parse_mode="HTML")

        elif data.startswith("faq_ek_"):
            it=faq_item(data[7:])
            if not it: await query.answer("یافت نشد!",show_alert=True); return
            await query.answer()
            ctx.user_data.update({"mode":"faq_keys","faq_id":it["id"]})
            await query.message.reply_text(
                f"🔑 کلیدواژه‌های فعلی: {'، '.join(it.get('keys',[]))}\n\nکلیدواژه‌های جدید:",
                reply_markup=cancel_menu())

        elif data.startswith("faq_ea_"):
            it=faq_item(data[7:])
            if not it: await query.answer("یافت نشد!",show_alert=True); return
            await query.answer()
            ctx.user_data.update({"mode":"faq_ans","faq_id":it["id"]})
            await query.message.reply_text("📝 پاسخ جدید:",reply_markup=cancel_menu())

        elif data.startswith("faq_ep_"):
            it=faq_item(data[7:])
            if not it: await query.answer("یافت نشد!",show_alert=True); return
            await query.answer()
            ctx.user_data.update({"mode":"faq_photo","faq_id":it["id"]})
            k1=(it.get("keys") or [None])[0]
            await query.message.reply_text(
                "🖼 عکس را بفرستید (مثلاً لیست قیمت امروز).\n"
                + (f"\n♻️ دفعه‌ی بعد لازم نیست از پنل بیایید — کافی است عکس را با "
                   f"کپشن #{k1} بفرستید." if k1 else ""),
                reply_markup=cancel_menu())

        elif data.startswith("faq_dp_"):
            it=faq_item(data[7:])
            if not it: await query.answer("یافت نشد!",show_alert=True); return
            it.pop("photo",None); it.pop("photo_at",None); await save_faq()
            await query.answer("🗑 عکس حذف شد.",show_alert=True)
            await safe_edit(query.message,faq_view_text(it),
                            reply_markup=faq_view_kb(it),parse_mode="HTML")

        elif data=="unm_menu":
            await query.answer()
            await safe_edit(query.message,unmatched_text(),
                            reply_markup=unmatched_kb(),parse_mode="HTML")

        elif data=="unm_clear":
            unmatched.clear(); await save_unmatched()
            await query.answer("🗑 فهرست پاک شد.",show_alert=True)
            await safe_edit(query.message,unmatched_text(),
                            reply_markup=unmatched_kb(),parse_mode="HTML")

        elif data.startswith("unm_at_"):
            # «این سؤال یعنی همان نیت» — با یک تپ، دستیار از این به بعد می‌فهمدش
            uid_,_,iid=data[7:].partition("_")
            u=unmatched_by_id(uid_); it=faq_item(iid)
            if not u or not it: await query.answer("یافت نشد!",show_alert=True); return
            it.setdefault("examples",[])
            if u["text"] not in it["examples"]: it["examples"].append(u["text"])
            unmatched[:] = [x for x in unmatched if x.get("id")!=uid_]
            await save_faq(); await save_unmatched()
            await query.answer(f"✅ یاد گرفت: این یعنی «{faq_title(it)}»",show_alert=True)
            await safe_edit(query.message,unmatched_text(),
                            reply_markup=unmatched_kb(),parse_mode="HTML")

        elif data.startswith("unm_new_"):
            u=unmatched_by_id(data[8:])
            if not u: await query.answer("یافت نشد!",show_alert=True); return
            await query.answer()
            ctx.user_data.update({"mode":"faq_keys","faq_id":None})
            await query.message.reply_text(
                f"❓ سؤال مشتری:\n«{u['text']}»\n\n"
                f"🔑 کلیدواژه‌های نیت تازه را با کاما بنویسید — کلمه‌هایی که در "
                f"پیام‌های مشابه تکرار می‌شوند:",reply_markup=cancel_menu())

        elif data.startswith("unm_"):
            u=unmatched_by_id(data[4:])
            if not u: await query.answer("یافت نشد!",show_alert=True); return
            await query.answer()
            rows=[[InlineKeyboardButton(f"➕ یعنی {_fit(faq_title(x),22)}",
                                        callback_data=f"unm_at_{u['id']}_{x['id']}")]
                  for x in faq if x.get("enabled",True)][:14]
            rows.append([InlineKeyboardButton("🆕 نیت تازه بساز",callback_data=f"unm_new_{u['id']}")])
            await safe_edit(query.message,
                f"❓ سؤال مشتری:\n«{esc(u['text'])}»\n{HR}\n"
                "این سؤال یعنی کدام نیت؟ با یک تپ، دستیار از این به بعد جمله‌های "
                "شبیه این را هم می‌فهمد.",parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(_nav(*rows,back="unm_menu")))

        elif data.startswith("faq_ac_"):
            it=faq_item(data[7:])
            if not it: await query.answer("یافت نشد!",show_alert=True); return
            await query.answer()
            opts=[("n","")]+[(c,c) for c in ("hours","prices","notify","human")]
            opts+=[(f"s:{k}",f"section:{k}") for k in section_order()
                   if k not in ("welcome","workhours","notify")]
            rows=[[InlineKeyboardButton(("✅ " if (it.get("action") or "")==a else "")+action_label(a),
                                        callback_data=f"faq_as_{it['id']}_{c}")] for c,a in opts]
            await safe_edit(query.message,
                f"⚙️ دستیار بعد از متنِ «{esc(faq_title(it))}» چه کاری انجام دهد؟",
                parse_mode="HTML",reply_markup=InlineKeyboardMarkup(_nav(*rows,back=f"faq_v_{it['id']}")))

        elif data.startswith("faq_as_"):
            # کلید بخش‌های سفارشی هم ممکن است «_» داشته باشد؛ پس «_s:» اول
            if "_s:" in data: iid,_,code=data[7:].partition("_s:"); code="s:"+code
            else: iid,_,code=data[7:].rpartition("_")
            it=faq_item(iid)
            if not it: await query.answer("یافت نشد!",show_alert=True); return
            a={"n":""}.get(code,code)
            if a.startswith("s:"): a="section:"+a[2:]
            it["action"]=a; await save_faq()
            await query.answer("✅ "+action_label(a),show_alert=True)
            await safe_edit(query.message,faq_view_text(it),
                            reply_markup=faq_view_kb(it),parse_mode="HTML")

        elif data.startswith("faq_tg_"):
            it=faq_item(data[7:])
            if not it: await query.answer("یافت نشد!",show_alert=True); return
            it["enabled"]=not it.get("enabled",True); await save_faq()
            await query.answer("🟢 فعال شد" if it["enabled"] else "⚫️ غیرفعال شد",show_alert=True)
            await safe_edit(query.message,faq_view_text(it),
                            reply_markup=faq_view_kb(it),parse_mode="HTML")

        elif data.startswith("faq_dl_"):
            fid=data[7:]
            faq[:] = [x for x in faq if x.get("id")!=fid]; await save_faq()
            await query.answer("🗑 حذف شد.",show_alert=True)
            await safe_edit(query.message,faq_menu_text(),
                            reply_markup=faq_menu_kb(uid),parse_mode="HTML")

        elif data=="adm_content":
            await query.answer()
            n_btn=sum(len(get_sec_btns(k).get("items",[])) for k in SECTION_NAMES)
            n_ban=sum(1 for k in SECTION_NAMES if get_banner(k).get("file_id"))
            en=sum(1 for m in menu_cfg if m.get("enabled",True))
            await safe_edit(query.message,
                "✏️ محتوای ربات\n"+"─"*20+
                f"\n🧩 {to_fa(en)} دکمه در منوی اصلی فعال است"
                f"\n📝 {to_fa(len(SECTION_NAMES))} بخش  ·  🖼 {to_fa(n_ban)} بنر  ·  🔗 {to_fa(n_btn)} لینک",
                reply_markup=content_kb())

        elif data in ("adm_stats","dash","stats_page"):
            await query.answer()
            await safe_edit(query.message,await stats_text(),reply_markup=stats_kb())

        elif data=="stats_reset":
            stats.clear(); await save_stats()
            await query.answer("✅ آمار صفر شد",show_alert=True)
            await safe_edit(query.message,await stats_text(),reply_markup=stats_kb())

        elif data=="broadcast":
            await query.answer()
            if _bc_job:
                await safe_edit(query.message,bc_status_text(),
                                reply_markup=bc_status_kb(),parse_mode="HTML")
            else:
                await safe_edit(query.message,
                    "<b>📣 پیام همگانی</b>\n"+HR+
                    "\nاول انتخاب کنید پیام به چه کسانی برسد:",
                    reply_markup=await bc_aud_kb(),parse_mode="HTML")

        elif data.startswith("bc_aud_"):
            aud=data[7:]
            n=len(await bc_uids(aud))
            if not n:
                await query.answer("این گروه الان کاربری ندارد.",show_alert=True); return
            await query.answer()
            ctx.user_data.update({"mode":"broadcast","bc_aud":aud})
            await query.message.reply_text(
                f"🎯 مخاطب: {bc_label(aud)} — {to_fa(n)} نفر\n\n"
                f"حالا پیام را بفرستید (متن یا عکس با کپشن):",
                reply_markup=cancel_menu())

        elif data=="bc_go":
            await query.answer()
            if not ctx.user_data.get("bc_text") and not ctx.user_data.get("bc_photo"):
                await safe_edit(query.message,"⏳ این پیش‌نویس دیگر معتبر نیست. از نو شروع کنید.",
                                reply_markup=None); return
            if _bc_job:
                await safe_edit(query.message,"⚠️ یک پخش دیگر در جریان است — اول آن را تمام یا لغو کنید.",
                                reply_markup=None); return
            job=await bc_create(ctx,uid)
            await safe_edit(query.message,
                f"🚀 پخش شروع شد — {to_fa(len(job['queue']))} نفر.",reply_markup=None)
            bc_start(ctx.bot)

        elif data=="bc_when":
            await query.answer()
            await safe_edit(query.message,"⏰ چه زمانی ارسال شود؟",reply_markup=bc_when_kb())

        elif data in ("bc_in_60","bc_in_180","bc_in_t10"):
            await query.answer()
            if not ctx.user_data.get("bc_text") and not ctx.user_data.get("bc_photo"):
                await safe_edit(query.message,"⏳ این پیش‌نویس دیگر معتبر نیست. از نو شروع کنید.",
                                reply_markup=None); return
            if _bc_job:
                await safe_edit(query.message,"⚠️ یک پخش دیگر در جریان است.",reply_markup=None); return
            run_at=(bc_next_at(10,0) if data=="bc_in_t10"
                    else time.time()+(60 if data=="bc_in_60" else 180)*60)
            job=await bc_create(ctx,uid,run_at=run_at)
            await safe_edit(query.message,
                f"⏰ زمان‌بندی شد — {bc_when_text(run_at)}\n"
                f"🎯 {bc_label(job['audience'])} · {to_fa(len(job['queue']))} نفر\n\n"
                f"تا آن لحظه می‌توانید از «📣 پیام همگانی» لغوش کنید.",reply_markup=None)

        elif data=="bc_in_ask":
            await query.answer()
            ctx.user_data["mode"]="bc_time"
            await query.message.reply_text(
                "🕐 ساعت ارسال را به شکل ۲۴ساعته بنویسید — مثلاً 09:30 یا 21:00\n"
                "(اگر از الان گذشته باشد، فردا همان ساعت ارسال می‌شود.)",
                reply_markup=cancel_menu())

        elif data=="bc_no":
            await query.answer("انصراف داده شد.")
            for k in ("mode","bc_aud","bc_text","bc_photo"): ctx.user_data.pop(k,None)
            await safe_edit(query.message,"↩️ پخش لغو شد.",reply_markup=None)

        elif data=="bc_stop":
            _bc_cancel=True
            await query.answer("🛑 در حال توقف پخش…",show_alert=True)

        elif data=="bc_kill":
            if _bc_job and _bc_job["status"]=="pending":
                _bc_job=None; await bc_save()
                await query.answer("🗑 پخش زمان‌بندی‌شده لغو شد.",show_alert=True)
                await show_home(query.message)
            else:
                await query.answer("این پخش دیگر قابل لغو نیست.",show_alert=True)

        elif data.startswith("backup") and not is_owner(uid):
            await query.answer("⛔ بک‌آپ و بازگردانی فقط دستِ مالک ربات است.",show_alert=True)

        elif data=="backup":
            await query.answer()
            await safe_edit(query.message,backup_text(),reply_markup=backup_kb())

        elif data=="backup_get":
            await query.answer()
            await safe_edit(query.message,"💾 در حال تهیه...",reply_markup=None)
            await send_backup(ctx.bot)
            await safe_edit(query.message,"✅ بک‌آپ ارسال شد.\n\n"+backup_text(),
                            reply_markup=backup_kb())

        elif data.startswith("backup_auto_"):
            # فقط تأیید — بازگردانی کل کاربران و تنظیمات را جایگزین می‌کند
            idx=int(data[12:])
            registry_rev=list(reversed(_backup_registry))
            if idx>=len(registry_rev):
                await query.answer("❌ بکاپ یافت نشد.",show_alert=True); return
            entry=registry_rev[idx]
            await query.answer()
            await safe_edit(query.message,
                f"⚠️ بازگردانی از بکاپ {entry['date']}\n"+"─"*18+
                "\n\nتمام کاربران، متن‌ها و تنظیمات فعلی با نسخه‌ی این "
                "بکاپ جایگزین می‌شوند.\n\n"
                "(از وضعیت فعلی یک نسخه‌ی ایمنی در pre_restore.zip نگه داشته می‌شود.)",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ بله، بازگردان",callback_data=f"backup_do_{idx}")],
                    [InlineKeyboardButton("↩️ انصراف",callback_data="backup")]]))

        elif data.startswith("backup_do_"):
            idx=int(data[10:])
            registry_rev=list(reversed(_backup_registry))
            if idx>=len(registry_rev):
                await query.answer("❌ بکاپ یافت نشد.",show_alert=True); return
            entry=registry_rev[idx]
            await query.answer()
            await safe_edit(query.message,f"⏳ در حال بازگردانی از {entry['date']}...",reply_markup=None)
            ok,result=await restore_backup(ctx.bot,entry["file_id"])
            if ok:
                await safe_edit(query.message,f"✅ بازگردانی شد.\nفایل‌ها: {', '.join(result)}",reply_markup=backup_kb())
            else:
                await safe_edit(query.message,f"❌ خطا: {result}",reply_markup=backup_kb())

        elif data=="backup_import":
            await query.answer()
            ctx.user_data["mode"]="backup_restore"
            await query.message.reply_text(
                "📥 فایل ZIP بک‌آپ را ارسال کنید.\n\n"
                "⚠️ محتوای فایل جایگزین کاربران، متن‌ها و تنظیمات فعلی می‌شود.",
                reply_markup=cancel_menu())

        # ── مدیریت بخش‌ها — یکپارچه برای تمام بخش‌ها
        elif data=="sections":
            await query.answer()
            await safe_edit(query.message,"📋 مدیریت بخش‌ها"+pages_hint(),
                            reply_markup=sections_kb())

        # ── مدیریت منوی اصلی ──
        elif data=="menu_mgr":
            await query.answer()
            en=sum(1 for m in menu_cfg if m.get("enabled",True))
            await safe_edit(query.message,
                f"🎛 مدیریت منوی اصلی\n{'─'*18}\n"
                f"دکمه فعال: {to_fa(en)} از {to_fa(len(menu_cfg))}\n\n"
                f"روی هر دکمه بزنید تا تنظیمش کنید:",
                reply_markup=menu_mgr_kb())

        elif data.startswith("mi_"):
            await query.answer()
            key=data[3:]; m=menu_item(key)
            if not m: return
            st="🟢 فعال" if m.get("enabled",True) else "⚫️ غیرفعال"
            w_txt="تمام‌صفحه" if m.get("width","half")=="full" else "نصف‌صفحه"
            await safe_edit(query.message,
                f"🎛 دکمه: {m['label']}\n{'─'*18}\nوضعیت: {st}\nعرض: {w_txt}",
                reply_markup=menu_item_kb(key))

        elif data.startswith("mtg_"):
            key=data[4:]; m=menu_item(key)
            if not m: return
            m["enabled"]=not m.get("enabled",True); await save_menu()
            await query.answer("🟢 روشن شد" if m["enabled"] else "⚫️ خاموش شد",show_alert=True)
            st="🟢 فعال" if m["enabled"] else "⚫️ غیرفعال"
            await safe_edit(query.message,f"🎛 دکمه: {m['label']}\n{'─'*18}\nوضعیت: {st}",reply_markup=menu_item_kb(key))

        elif data.startswith("mw_"):
            key=data[3:]; m=menu_item(key)
            if not m: return
            m["width"]="full" if m.get("width","half")=="half" else "half"; await save_menu()
            await query.answer("📐 تمام‌صفحه شد" if m["width"]=="full" else "📐 نصف‌صفحه شد",show_alert=True)
            w_txt="تمام‌صفحه" if m["width"]=="full" else "نصف‌صفحه"
            st="🟢 فعال" if m.get("enabled",True) else "⚫️ غیرفعال"
            await safe_edit(query.message,f"🎛 دکمه: {m['label']}\n{'─'*18}\nوضعیت: {st}\nعرض: {w_txt}",reply_markup=menu_item_kb(key))

        elif data.startswith("mnm_"):
            await query.answer()
            key=data[4:]; m=menu_item(key)
            if not m: return
            ctx.user_data.update({"mode":"menu_rename","menu_key":key})
            await query.message.reply_text(
                f"✏️ نام فعلی: {m['label']}\n\nنام جدید را بفرستید (با ایموجی دلخواه):",
                reply_markup=cancel_menu())

        elif data.startswith("mup_") or data.startswith("mdn_"):
            key=data[4:]; up=data.startswith("mup_")
            items=menu_sorted()
            idx=next((i for i,x in enumerate(items) if x["key"]==key),None)
            if idx is None: return
            swap=idx-1 if up else idx+1
            if 0<=swap<len(items):
                items[idx]["order"],items[swap]["order"]=items[swap]["order"],items[idx]["order"]
                await save_menu()
            await query.answer("⬆️ بالا رفت" if up else "⬇️ پایین رفت")
            await safe_edit(query.message,"🎛 مدیریت منوی اصلی\nترتیب بروزرسانی شد:",reply_markup=menu_mgr_kb())

        elif data.startswith("msw_"):
            key=data[4:]; partner=menu_row_partner(key)
            if not partner:
                await query.answer("این دکمه جفت ندارد",show_alert=True); return
            m=menu_item(key); p=menu_item(partner)
            m["order"],p["order"]=p["order"],m["order"]; await save_menu()
            await query.answer("↔️ جای دو دکمه عوض شد",show_alert=True)
            st="🟢 فعال" if m.get("enabled",True) else "⚫️ غیرفعال"
            w_txt="تمام‌صفحه" if m.get("width","half")=="full" else "نصف‌صفحه"
            await safe_edit(query.message,f"🎛 دکمه: {m['label']}\n{'─'*18}\nوضعیت: {st}\nعرض: {w_txt}",reply_markup=menu_item_kb(key))

        elif data=="menu_reset":
            await query.answer()
            await safe_edit(query.message,
                "♻️ بازگردانی منو به حالت پیش‌فرض\n\n"
                "نام، ترتیب و عرض همه دکمه‌ها به حالت اولیه برمی‌گردد.\nمطمئن هستید؟",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("♻️ بله، بازگردانی کن",callback_data="menu_reset_ok")],
                    [InlineKeyboardButton("↩️ انصراف",callback_data="menu_mgr")]]))

        elif data=="menu_reset_ok":
            await reset_menu()
            await query.answer("♻️ منو به حالت پیش‌فرض برگشت",show_alert=True)
            en=sum(1 for m in menu_cfg if m.get("enabled",True))
            await safe_edit(query.message,
                f"🎛 مدیریت منوی اصلی\n{'─'*18}\nدکمه فعال: {to_fa(en)} از {to_fa(len(menu_cfg))}\n\n✅ به حالت پیش‌فرض بازگشت.",
                reply_markup=menu_mgr_kb())

        elif data.startswith("sec_link_"):
            key=data[9:]
            if key not in SECTION_NAMES:
                await query.answer("یافت نشد!",show_alert=True); return
            await query.answer()
            rows=[(lbl,deep_link(src,key)) for src,lbl in
                  (("insta","📸 اینستاگرام"),("site","🌐 سایت"),
                   ("qr","🔳 QR مغازه"),("card","🪧 کارت ویزیت"))]
            body="\n\n".join(f"{lbl}\n<code>{esc(u)}</code>" for lbl,u in rows)
            await safe_edit(query.message,
                f"🔗 لینک مستقیم «{esc(SECTION_NAMES.get(key,key))}»\n{HR}\n"
                f"هرکدام را در جای خودش بگذارید: با یک تپ، مشتری مستقیم همین "
                f"بخش را می‌بیند و منبع ورودش هم ثبت می‌شود.\n\n{body}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(_nav(back=f"sec_{key}")))

        elif data.startswith("sec_") and not any(data.startswith(p) for p in["sec_text_","sec_ban_","sec_btns_","sec_loc_","sec_link_"]):
            await query.answer()
            key=data[4:]
            from telegram.error import BadRequest
            txt_ok="✅" if responses.get(key,"") not in ("","تنظیم نشده") else "❌"
            ban_ok="✅ فعال" if get_banner(key).get("active") and get_banner(key).get("file_id") else "❌"
            btn_ok=f"{len(get_sec_btns(key).get('items',[]))} {'✅' if get_sec_btns(key).get('enabled') else '❌'}"
            try: await safe_edit(query.message,
                f"📋 بخش: {SECTION_NAMES.get(key,key)}\n{'─'*14}"
                f"\n✏️ متن: {txt_ok}\n🖼 بنر: {ban_ok}\n🔘 دکمه: {btn_ok}",
                reply_markup=section_kb(key))
            except BadRequest: await query.message.reply_text(f"📋 {SECTION_NAMES.get(key,key)}",reply_markup=section_kb(key))

        elif data=="page_add":
            await query.answer()
            ctx.user_data["mode"]="page_add"
            await query.message.reply_text(
                "📄 نام بخش تازه را بنویسید — همان چیزی که روی دکمه‌ی منو دیده می‌شود.\n\n"
                "مثال:  🛍 محصولات",reply_markup=cancel_menu())

        elif data.startswith("page_dl_"):
            key=data[8:]; pg=page_item(key)
            if not pg: await query.answer("یافت نشد!",show_alert=True); return
            await query.answer()
            await safe_edit(query.message,
                f"🗑 حذف بخش «{esc(pg['title'])}»؟\n{HR}\n"
                "متن، بنر، دکمه‌ها و لوکیشن این بخش هم پاک می‌شوند و از منو "
                "برداشته می‌شود. بخش‌های دیگر دست‌نخورده می‌مانند.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🗑 بله، حذف کن",callback_data=f"page_dok_{key}")],
                    [InlineKeyboardButton("↩️ انصراف",callback_data=f"sec_{key}")]]))

        elif data.startswith("page_dok_"):
            key=data[9:]; pg=page_item(key)
            if not pg: await query.answer("یافت نشد!",show_alert=True); return
            pages[:] = [x for x in pages if x["key"]!=key]
            for store,saver in ((responses,save_data),(banners,save_banners),
                                (buttons,save_buttons),(places,save_places)):
                if store is not None and key in store:
                    store.pop(key,None); await saver()
            stats.pop(key,None); await save_stats()
            menu_cfg[:] = [m for m in menu_cfg if m.get("key")!=key]
            await save_menu(); await save_pages()
            await query.answer("🗑 بخش حذف شد.",show_alert=True)
            await safe_edit(query.message,"📝 بخش‌های ربات"+pages_hint(),
                            reply_markup=sections_kb())

        elif data.startswith("page_menu_"):
            key=data[10:]; pg=page_item(key)
            if not pg: await query.answer("یافت نشد!",show_alert=True); return
            m=menu_item(key)
            if m:
                m["enabled"]=not m.get("enabled",True)
            else:
                nxt=max([x.get("order",0) for x in menu_cfg] or [0])+1
                menu_cfg.append({"key":key,"label":pg["title"],"order":nxt,
                                 "enabled":True,"width":"half"})
                m=menu_item(key)
            await save_menu()
            await query.answer("✅ به منو اضافه شد" if m.get("enabled",True)
                               else "⚫️ از منو برداشته شد",show_alert=True)
            await safe_edit(query.message,f"📋 بخش: {SECTION_NAMES.get(key,key)}\n{'─'*14}",
                            reply_markup=section_kb(key))

        elif data.startswith("sec_text_"):
            key=data[9:]
            await query.answer()
            ctx.user_data.update({"mode":"edit_text","edit_key":key})
            await query.message.reply_text(f"✏️ متن فعلی:\n\n{responses.get(key,'تنظیم نشده')}\n\nمتن جدید:",reply_markup=cancel_menu())

        elif data.startswith("sec_loc_"):
            await query.answer()
            key=data[8:]
            await safe_edit(query.message,place_text(key),reply_markup=place_kb(key))
            pl=places.get(key) or {}
            if pl.get("lat") is not None:
                try: await send_place_preview(query.message,key)
                except Exception as e: logger.debug(f"place preview: {e}")

        elif data.startswith("loc_up_"):
            await query.answer()
            key=data[7:]; ctx.user_data.update({"mode":"loc_up","loc_key":key})
            await query.message.reply_text(
                "📍 حالا موقعیت را بفرستید:\n\n"
                "۱) روی 📎 (گیره) کنار فیلد تایپ بزنید\n"
                "۲) گزینه‌ی «Location / موقعیت مکانی» را انتخاب کنید\n"
                "۳) پین را دقیقاً روی فروشگاه بگذارید و بفرستید\n\n"
                "می‌توانید لوکیشن فوروارد‌شده از جای دیگر را هم بفرستید.",
                reply_markup=cancel_menu())

        elif data.startswith("loc_tg_"):
            key=data[7:]; pl=get_place(key)
            pl["active"]=not pl.get("active",False); await save_places()
            await query.answer("🟢 فعال شد" if pl["active"] else "⚫️ غیرفعال شد",show_alert=True)
            await safe_edit(query.message,place_text(key),reply_markup=place_kb(key))

        elif data.startswith("loc_ed_"):
            await query.answer()
            key=data[7:]; ctx.user_data.update({"mode":"loc_ed","loc_key":key})
            pl=get_place(key)
            await query.message.reply_text(
                f"✏️ عنوان و آدرس نقشه را در یک خط بنویسید، با «|» جدا شده:\n\n"
                f"مثال:\n{SHOP_NAME} | قم، عمار یاسر، بازار سلام، طبقه اول واحد F11\n\n"
                f"فعلی: {pl.get('title') or SHOP_NAME} | {pl.get('address') or '—'}",
                reply_markup=cancel_menu())

        elif data.startswith("loc_dl_"):
            key=data[7:]; places.pop(key,None); await save_places()
            await query.answer("🗑 حذف شد",show_alert=True)
            await safe_edit(query.message,place_text(key),reply_markup=place_kb(key))

        elif data.startswith("sec_ban_"):
            await query.answer()
            key=data[8:]; b=get_banner(key)
            await safe_edit(query.message,banner_text(key),reply_markup=banner_kb(key))
            # پیش‌نمایش با نسخه‌ی کوچک — سریع و کم‌حجم
            th=b.get("thumb_id") or b.get("file_id")
            if th:
                try: await query.message.reply_photo(photo=th,caption=f"👁 پیش‌نمایش بنر «{SECTION_NAMES.get(key,key)}»")
                except Exception as e: logger.debug(f"thumb preview: {e}")

        elif data.startswith("ban_up_"):
            await query.answer()
            key=data[7:]; ctx.user_data.update({"mode":"ban_up","ban_key":key})
            await query.message.reply_text(f"📤 عکس بنر «{SECTION_NAMES.get(key,key)}» را ارسال کنید:",reply_markup=cancel_menu())

        elif data.startswith("ban_tg_"):
            key=data[7:]; b=get_banner(key)
            if not b.get("file_id"): await query.answer("ابتدا عکس آپلود کنید!",show_alert=True); return
            b["active"]=not b.get("active",False); await save_banners()
            await query.answer("✅ فعال شد" if b["active"] else"⚫️ غیرفعال شد",show_alert=True)
            await safe_edit(query.message,banner_text(key),reply_markup=banner_kb(key))

        elif data.startswith("ban_dl_"):
            key=data[7:]; banners[key]={"file_id":None,"active":False}; await save_banners()
            await query.answer("🗑 حذف شد.",show_alert=True)
            await safe_edit(query.message,banner_text(key),reply_markup=banner_kb(key))

        elif data.startswith("sec_btns_"):
            key=data[9:]
            await query.answer()
            sec=get_sec_btns(key)
            await safe_edit(query.message,
                f"🔘 دکمه‌های {SECTION_NAMES.get(key,key)}\n"
                f"{'✅ فعال' if sec.get('enabled') else '❌ غیرفعال'} | {to_fa(len(sec.get('items',[])))} عدد",
                reply_markup=sec_btns_kb(key))

        elif data.startswith("btn_tg_"):
            key=data[7:]
            sec=get_sec_btns(key); sec["enabled"]=not sec.get("enabled",False); await save_buttons()
            await query.answer("✅ فعال" if sec["enabled"] else"❌ غیرفعال",show_alert=True)
            await safe_edit(query.message,f"🔘 {SECTION_NAMES.get(key,key)} | {'✅' if sec['enabled'] else '❌'}",reply_markup=sec_btns_kb(key))

        elif data.startswith("btn_auto_"):
            key=data[9:]
            sec=get_sec_btns(key)
            have={(x.get("url") or "").rstrip("/").lower() for x in sec.get("items",[])}
            added=[]
            for title,url in extract_links(responses.get(key,"")):
                if url.rstrip("/").lower() in have: continue
                sec["items"].append({"id":new_btn_id(),"title":title,"url":url})
                have.add(url.rstrip("/").lower()); added.append(title)
            if not added:
                await query.answer("همه‌ی لینک‌های این متن از قبل دکمه دارند.",show_alert=True); return
            sec["enabled"]=True
            await save_buttons()
            await query.answer(f"✅ {to_fa(len(added))} دکمه ساخته شد",show_alert=True)
            await safe_edit(query.message,
                "✨ دکمه‌های زیر از روی لینک‌های متن ساخته شدند:\n"+"─"*20+
                "\n"+"\n".join(f"• {t}" for t in added)+
                "\n\n🧹 این لینک‌ها دیگر به‌صورت متن آبی نمایش داده نمی‌شوند —"
                " دکمه جایشان را گرفته. (متن اصلی دست‌نخورده است.)",
                reply_markup=sec_btns_kb(key))

        elif data.startswith("btn_add_"):
            key=data[8:]
            await query.answer()
            ctx.user_data.update({"mode":"btn_add_t","btn_key":key})
            await query.message.reply_text(f"➕ دکمه جدید برای «{SECTION_NAMES.get(key,key)}»\nعنوان:",reply_markup=cancel_menu())

        elif data.startswith("btn_ed_"):
            parts=data[7:].split("_",1); key,bid=parts[0],parts[1]
            sec=get_sec_btns(key); item=next((x for x in sec.get("items",[]) if x["id"]==bid),None)
            if not item: await query.answer("یافت نشد!",show_alert=True); return
            await query.answer()
            ctx.user_data.update({"mode":"btn_ed_t","btn_key":key,"btn_id":bid})
            await query.message.reply_text(f"✏️ «{item['title']}»\nعنوان جدید (یا . بدون تغییر):",reply_markup=cancel_menu())

        elif data.startswith("btn_dl_"):
            parts=data[7:].split("_",1); key,bid=parts[0],parts[1]
            sec=get_sec_btns(key); sec["items"]=[x for x in sec.get("items",[]) if x["id"]!=bid]; await save_buttons()
            await query.answer("🗑 حذف شد.",show_alert=True)
            await safe_edit(query.message,f"🔘 {SECTION_NAMES.get(key,key)}",reply_markup=sec_btns_kb(key))

        elif data=="noop": await query.answer()

        # ── ساعت کاری
        elif data=="wh_menu":
            await query.answer()
            en="✅ فعال" if workhours.get("enabled") else"❌ غیرفعال"
            await safe_edit(query.message,f"🕐 ساعت کاری — {en}\n\n{wh_full_table()}",reply_markup=wh_kb())

        elif data=="wh_toggle":
            workhours["enabled"]=not workhours.get("enabled",True); await save_workhours()
            await query.answer("✅ فعال" if workhours["enabled"] else"❌ غیرفعال",show_alert=True)
            await safe_edit(query.message,f"🕐 ساعت کاری\n{wh_full_table()}",reply_markup=wh_kb())

        elif data.startswith("wh_day_"):
            await query.answer()
            dk=data[7:]; day=workhours["schedule"].get(dk,{"open":False,"shifts":[]})
            st2="\n".join(f"  • {to_fa(s['from'])} تا {to_fa(s['to'])}" for s in day.get("shifts",[])) or"  ندارد"
            await safe_edit(query.message,f"🕐 {DAY_FA.get(dk,dk)}\n{'✅ باز' if day.get('open') else '❌ تعطیل'}\n{st2}",reply_markup=wh_day_kb(dk))

        elif data.startswith("wh_dtg_"):
            dk=data[7:]; day=workhours["schedule"].get(dk,{"open":False,"shifts":[]})
            day["open"]=not day.get("open",False); workhours["schedule"][dk]=day; await save_workhours()
            await query.answer("✅ باز" if day["open"] else"❌ تعطیل",show_alert=True)
            await safe_edit(query.message,f"🕐 {DAY_FA.get(dk,dk)} | {'✅ باز' if day['open'] else '❌ تعطیل'}",reply_markup=wh_day_kb(dk))

        elif data.startswith("wh_sh_"):
            await query.answer()
            dk=data[6:]; ctx.user_data.update({"mode":"wh_shifts","wh_day":dk})
            await query.message.reply_text(f"🕐 {DAY_FA.get(dk,dk)}:\nمثال: 11:00-14:00,17:00-23:00",reply_markup=cancel_menu())

        elif data=="wh_mop":
            await query.answer()
            ctx.user_data["mode"]="wh_mop"
            await query.message.reply_text(f"✏️ پیام باز:\n\n{workhours.get('msg_open','')}\n\nپیام جدید:",reply_markup=cancel_menu())

        elif data=="wh_mcl":
            await query.answer()
            ctx.user_data["mode"]="wh_mcl"
            await query.message.reply_text(f"✏️ پیام بسته:\n\n{workhours.get('msg_closed','')}\n\nپیام جدید:",reply_markup=cancel_menu())

        # ── تنظیمات
        elif data=="settings_menu":
            await query.answer()
            await safe_edit(query.message,settings_text(),reply_markup=settings_kb(is_owner(uid)))

        elif data=="adm_admins":
            if not is_owner(uid):
                await query.answer("⛔ فقط مالک ربات به این بخش دسترسی دارد.",show_alert=True); return
            await query.answer()
            await safe_edit(query.message,await admins_text(),
                            reply_markup=admins_kb(),parse_mode="HTML")

        elif data=="adm_add":
            if not is_owner(uid):
                await query.answer("⛔ فقط مالک ربات می‌تواند مدیر اضافه کند.",show_alert=True); return
            await query.answer()
            ctx.user_data["mode"]="adm_add"
            await query.message.reply_text(
                "➕ افزودن مدیر\n"
                "یکی از این دو کار را بکنید:\n"
                "• آیدی عددی او را بفرستید (از @userinfobot)\n"
                "• یا یکی از پیام‌های <b>متنی</b>‌اش را برای من فوروارد کنید\n\n"
                "او باید حداقل یک‌بار ربات را استارت کرده باشد.",parse_mode="HTML",
                reply_markup=cancel_menu())

        elif data.startswith("adm_del_"):
            if not is_owner(uid):
                await query.answer("⛔ فقط مالک ربات می‌تواند مدیر حذف کند.",show_alert=True); return
            try: tgt=int(data[8:])
            except ValueError:
                await query.answer("آیدی نامعتبر.",show_alert=True); return
            ok=await del_admin(tgt)
            await query.answer("🗑 حذف شد." if ok else "این مدیر از پنل حذف نمی‌شود.",show_alert=True)
            await safe_edit(query.message,await admins_text(),
                            reply_markup=admins_kb(),parse_mode="HTML")

        elif data.startswith("stg_"):
            key=data[4:]; settings[key]=not get_setting(key); await save_settings()
            on=get_setting(key)
            if key=="store_open":
                await query.answer("🟢 فروشگاه باز شد" if on else "🔴 فروشگاه بسته شد",show_alert=True)
            else:
                await query.answer("✅ فعال شد" if on else "⚫️ غیرفعال شد",show_alert=True)
            # از هر صفحه‌ای آمده، همان‌جا بماند
            if "⚙️ تنظیمات" in (query.message.text or ""):
                await safe_edit(query.message,settings_text(),reply_markup=settings_kb(is_owner(uid)))
            else:
                await show_home(query.message)

        # ── کاربران
        elif data=="users_menu":
            await query.answer()
            t=await total_users(); bl=await blk_count()
            await safe_edit(query.message,f"👥 کاربران\nکل: {to_fa(t)} | بلاک: {to_fa(bl)}",reply_markup=users_menu_kb())

        elif data=="users_search":
            await query.answer()
            ctx.user_data["mode"]="users_search"
            await query.message.reply_text("🔍 نام، آیدی یا یوزرنیم:",reply_markup=cancel_menu())

        elif data.startswith("ul_"):
            await query.answer()
            parts=data.split("_"); ft=parts[1]; off=int(parts[2])
            flt={"today":"WHERE DATE(last_seen)=DATE('now','localtime')","week":"WHERE last_seen>=datetime('now','-7 days','localtime')","blocked":"WHERE is_blocked=1"}
            total=await _cnt(f"SELECT COUNT(*) FROM users {flt.get(ft,'')}")
            rows=await get_users_page(off,15,ft)
            label={"all":"همه","today":"امروز","week":"هفته","blocked":"بلاک"}.get(ft,"")
            await safe_edit(query.message,f"👥 {label}\n{to_fa(off+1)} تا {to_fa(min(off+15,total))} از {to_fa(total)}:",reply_markup=users_list_kb(rows,off,ft,total))

        elif data.startswith("uv_"):
            uid2=int(data[3:])
            async with db.execute("SELECT user_id,first_name,username,joined_at,last_seen,is_blocked,has_left FROM users WHERE user_id=?",(uid2,)) as c: row=await c.fetchone()
            if not row: await query.answer("یافت نشد!",show_alert=True); return
            await query.answer()
            sep="─"*20
            status="🚫 بلاک‌شده توسط شما" if row[5] else ("🚪 ربات را بلاک/حذف کرده" if row[6] else "✅ فعال")
            utxt=(f"👤 {row[1] or'—'}"
                  f"\n{'@'+row[2] if row[2] else'بدون یوزرنیم'}"
                  f"\n🆔 {row[0]}"
                  f"\n{sep}"
                  f"\n📅 عضویت: {row[3]}"
                  f"\n🕐 آخرین فعالیت: {row[4]}"
                  f"\n{sep}"
                  f"\n{status}")
            await safe_edit(query.message,utxt,reply_markup=udetail_kb(uid2,bool(row[5])))

        elif data.startswith("utog_"):
            uid2=int(data[5:])
            async with db.execute("SELECT is_blocked FROM users WHERE user_id=?",(uid2,)) as c: row=await c.fetchone()
            if not row: return
            await set_block(uid2,0 if row[0] else 1)
            await query.answer("✅ رفع بلاک" if row[0] else"🚫 بلاک شد",show_alert=True)
            async with db.execute("SELECT user_id,first_name,username,joined_at,last_seen,is_blocked FROM users WHERE user_id=?",(uid2,)) as c: row=await c.fetchone()
            await safe_edit(query.message,f"👤 {row[1] or'—'}\n🆔 {row[0]}\n{'🚫 بلاک' if row[5] else '✅ فعال'}",reply_markup=udetail_kb(uid2,bool(row[5])))

        else:
            await query.answer()

    except Exception as e:
        logger.error(f"admin callback error data={data}: {e}",exc_info=True)
        try: await query.answer()
        except Exception: pass
        try: await query.message.reply_text("❌ خطا در پردازش درخواست.")
        except Exception: pass

# ════════════════════════════════════════════════
#  TEXT HANDLER
# ════════════════════════════════════════════════
async def text_handler(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    user=update.effective_user; text=update.message.text.strip()
    await save_user(user)
    if not is_admin(user.id):
        _s=spam_check(user.id)
        if _s=='block': return
        if _s=='warn': return await update.message.reply_text("🐢 لطفاً آرام‌تر پیام دهید.")
        if await is_blocked(user.id): return
    if text=="❌ لغو عملیات":
        ctx.user_data.clear(); return await update.message.reply_text("❌ لغو شد.",reply_markup=main_menu())
    mode=ctx.user_data.get("mode")

    # ════ ADMIN ════
    if is_admin(user.id):
        if mode=="edit_text":
            key=ctx.user_data.pop("edit_key",None); ctx.user_data.pop("mode",None)
            saved=True
            if key:
                responses[key]=text; saved=await save_data()
            await update.message.reply_text(
                "✅ ذخیره شد." if saved else
                "⚠️ متن در حافظه اعمال شد ولی روی دیسک ذخیره نشد!\n"
                "فضای دیسک یا دسترسی نوشتن سرور را بررسی کنید — با ری‌استارت از بین می‌رود.",
                reply_markup=main_menu()); return
        if mode=="menu_rename":
            key=ctx.user_data.pop("menu_key",None); ctx.user_data.pop("mode",None)
            m=menu_item(key)
            if m and text:
                m["label"]=text
                # بخش سفارشی: نامش هم باید همراه دکمه عوض شود، وگرنه پنل و
                # منو دو اسم متفاوت نشان می‌دهند
                pg=page_item(key)
                if pg: pg["title"]=text; await save_pages()
                await save_menu()
                await update.message.reply_text(f"✅ نام دکمه به «{text}» تغییر کرد.",reply_markup=main_menu())
                await update.message.reply_text(f"🎛 دکمه: {m['label']}",reply_markup=menu_item_kb(key))
            else:
                await update.message.reply_text("✅ ذخیره شد.",reply_markup=main_menu())
            return
        if mode=="broadcast":
            ctx.user_data.pop("mode",None)
            ctx.user_data["bc_text"]=text; ctx.user_data.pop("bc_photo",None)
            aud=ctx.user_data.get("bc_aud","all"); n=len(await bc_uids(aud))
            await update.message.reply_text("👁 پیش‌نمایش پیام:",reply_markup=main_menu())
            await update.message.reply_text(text)
            await update.message.reply_text(
                f"🎯 {bc_label(aud)} — {to_fa(n)} نفر\nچه کار کنم؟",
                reply_markup=bc_confirm_kb())
            return
        if mode=="tp_add":
            ctx.user_data.pop("mode",None)
            title=text.strip()[:40]
            if len(title)<2:
                ctx.user_data["mode"]="tp_add"
                await update.message.reply_text("❌ نام کوتاه است. دوباره بنویسید:",
                                                reply_markup=cancel_menu()); return
            if any(t["title"]==title for t in topics):
                await update.message.reply_text("❌ موضوعی با همین نام هست.",
                                                reply_markup=main_menu()); return
            topics.append({"id":new_topic_id(),"title":title}); await save_topics()
            await update.message.reply_text(f"✅ موضوع «{title}» اضافه شد.",
                                            reply_markup=main_menu())
            await update.message.reply_text(await topics_text(),parse_mode="HTML",
                                            reply_markup=topics_kb()); return

        if mode=="page_add":
            ctx.user_data.pop("mode",None)
            title=text.strip()[:40]
            if len(title)<2:
                ctx.user_data["mode"]="page_add"
                await update.message.reply_text("❌ نام کوتاه است. دوباره بنویسید:",
                                                reply_markup=cancel_menu()); return
            if any(p["title"]==title for p in pages) or title in BASE_SECTIONS.values():
                await update.message.reply_text("❌ بخشی با همین نام وجود دارد.",
                                                reply_markup=main_menu()); return
            key=new_page_key()
            pages.append({"key":key,"title":title})
            responses[key]=""
            nxt=max([x.get("order",0) for x in menu_cfg] or [0])+1
            menu_cfg.append({"key":key,"label":title,"order":nxt,
                             "enabled":True,"width":"half"})
            await save_pages(); await save_data(); await save_menu()
            await update.message.reply_text(
                f"✅ بخش «{title}» ساخته شد و به منو اضافه شد.\n"
                f"حالا متن، بنر و لینک‌هایش را بگذارید 👇",reply_markup=main_menu())
            await update.message.reply_text(f"📋 بخش: {title}\n{'─'*14}",
                                            reply_markup=section_kb(key)); return

        if mode=="faq_keys":
            fid=ctx.user_data.get("faq_id")
            keys=[k.strip() for k in text.replace("،",",").split(",") if k.strip()]
            keys=[k for k in keys if len(faq_norm(k).strip())>=2]
            if not keys:
                await update.message.reply_text(
                    "❌ حداقل یک کلیدواژه‌ی ۲ حرفی یا بیشتر لازم است.\n"
                    "مثال:  گارانتی، ضمانت",reply_markup=cancel_menu()); return
            if fid:
                it=faq_item(fid); ctx.user_data.pop("mode",None); ctx.user_data.pop("faq_id",None)
                if not it:
                    await update.message.reply_text("❌ یافت نشد.",reply_markup=main_menu()); return
                it["keys"]=keys; await save_faq()
                await update.message.reply_text("✅ کلیدواژه‌ها ذخیره شد.",reply_markup=main_menu())
                await update.message.reply_text(faq_view_text(it),parse_mode="HTML",
                                                reply_markup=faq_view_kb(it)); return
            # سؤال جدید — حالا نوبت پاسخ
            ctx.user_data.update({"mode":"faq_ans","faq_keys":keys})
            await update.message.reply_text(
                f"🔑 {'، '.join(keys)}\n\n📝 حالا پاسخ را بنویسید.\n"
                f"لینک بنویسید، خودش دکمه می‌شود.",reply_markup=cancel_menu()); return

        if mode=="faq_ans":
            fid=ctx.user_data.pop("faq_id",None)
            keys=ctx.user_data.pop("faq_keys",None)
            ctx.user_data.pop("mode",None)
            if fid:
                it=faq_item(fid)
                if not it:
                    await update.message.reply_text("❌ یافت نشد.",reply_markup=main_menu()); return
                it["answer"]=text
            else:
                it={"id":new_btn_id(),"keys":keys or [],"answer":text,"enabled":True,"hits":0}
                faq.append(it)
            await save_faq()
            await update.message.reply_text("✅ ذخیره شد.",reply_markup=main_menu())
            await update.message.reply_text(faq_view_text(it),parse_mode="HTML",
                                            reply_markup=faq_view_kb(it)); return

        if mode=="adm_add":
            ctx.user_data.pop("mode",None)
            if not is_owner(user.id):
                await update.message.reply_text("⛔ فقط مالک ربات می‌تواند مدیر اضافه کند.",
                                                reply_markup=main_menu()); return
            tgt=None
            fo=getattr(update.message,"forward_origin",None)
            su=getattr(fo,"sender_user",None) if fo else None
            if su: tgt=su.id
            else:
                d=text.translate(FA_DIGITS).strip()
                if d.isdigit(): tgt=int(d)
            if not tgt:
                await update.message.reply_text(
                    "❌ آیدی عددی پیدا نشد.\n"
                    "اگر پیام را فوروارد کردید و جواب نداد، یعنی حریم خصوصی طرف "
                    "بسته است — آیدی عددی‌اش را دستی بفرستید.",reply_markup=main_menu()); return
            known=await user_label(tgt)
            if not await add_admin(tgt):
                await update.message.reply_text("ℹ️ این شخص از قبل مدیر است.",
                                                reply_markup=main_menu()); return
            note="" if known!="—" else ("\n⚠️ این کاربر هنوز ربات را استارت نکرده — "
                                        "تا وقتی /start نزند پیامی از ربات نمی‌گیرد.")
            await update.message.reply_text(
                f"✅ مدیر جدید اضافه شد.\n👤 {known}\n🆔 {tgt}{note}",reply_markup=main_menu())
            try:
                await ctx.bot.send_message(tgt,
                    f"👮 شما به‌عنوان مدیر {SHOP_NAME} اضافه شدید.\n"
                    f"برای باز کردن پنل، دستور /admin را بزنید.")
            except Exception: pass
            return
        if mode=="bc_time":
            ctx.user_data.pop("mode",None)
            hhmm=text.translate(FA_DIGITS).replace(".",":").replace("،",":").strip()
            if not HHMM_RE.match(hhmm):
                ctx.user_data["mode"]="bc_time"
                await update.message.reply_text(
                    "❌ ساعت را به شکل ۲۴ساعته بنویسید — مثلاً 09:30",
                    reply_markup=cancel_menu()); return
            if not ctx.user_data.get("bc_text") and not ctx.user_data.get("bc_photo"):
                await update.message.reply_text("⏳ پیش‌نویس منقضی شده. از نو شروع کنید.",
                                                reply_markup=main_menu()); return
            if _bc_job:
                await update.message.reply_text("⚠️ یک پخش دیگر در جریان است.",
                                                reply_markup=main_menu()); return
            h,m=[int(x) for x in hhmm.split(":")]
            run_at=bc_next_at(h,m)
            job=await bc_create(ctx,user.id,run_at=run_at)
            await update.message.reply_text(
                f"⏰ زمان‌بندی شد — {bc_when_text(run_at)}\n"
                f"🎯 {bc_label(job['audience'])} · {to_fa(len(job['queue']))} نفر",
                reply_markup=main_menu()); return
        if mode=="users_search":
            ctx.user_data.pop("mode",None); rows=await search_users(text)
            if not rows: await update.message.reply_text("❌ یافت نشد.",reply_markup=main_menu()); return
            lines=[f"{'🚫 ' if r[4] else ''}{r[1] or'—'} | {r[0]} | {'@'+r[2] if r[2] else'—'}" for r in rows]
            await update.message.reply_text("🔍 نتایج:\n\n"+"\n".join(lines),reply_markup=main_menu()); return
        if mode=="btn_add_t":
            ctx.user_data.update({"btn_title":text,"mode":"btn_add_u"})
            await update.message.reply_text("🔗 لینک:",reply_markup=cancel_menu()); return
        if mode=="btn_add_u":
            url=normalize_url(text)
            if not url:
                # حالت را نگه می‌داریم تا ادمین دوباره وارد کند — لینک نامعتبر
                # کل بخش را برای همه کاربران خراب می‌کند
                await update.message.reply_text(
                    "❌ لینک معتبر نیست.\nمثال: https://instagram.com/stockland یا t.me/stlandd",
                    reply_markup=cancel_menu()); return
            key=ctx.user_data.pop("btn_key",None); title=ctx.user_data.pop("btn_title","دکمه"); ctx.user_data.pop("mode",None)
            sec=get_sec_btns(key); sec["items"].append({"id":new_btn_id(),"title":title,"url":url})
            if not sec.get("enabled"): sec["enabled"]=True
            await save_buttons()
            await update.message.reply_text(f"✅ «{title}» اضافه شد.",reply_markup=sec_btns_kb(key)); return
        if mode=="btn_ed_t":
            ctx.user_data.update({"btn_new_t":None if text=="." else text,"mode":"btn_ed_u"})
            await update.message.reply_text("🔗 لینک جدید (یا . بدون تغییر):",reply_markup=cancel_menu()); return
        if mode=="btn_ed_u":
            key=ctx.user_data.pop("btn_key",None); bid=ctx.user_data.pop("btn_id",None)
            nt=ctx.user_data.pop("btn_new_t",None); ctx.user_data.pop("mode",None)
            sec=get_sec_btns(key)
            for it in sec.get("items",[]):
                if it["id"]==bid:
                    if nt: it["title"]=nt
                    if text!=".": it["url"]=text if text.startswith("http") else f"https://{text}"
            await save_buttons(); await update.message.reply_text("✅ ویرایش شد.",reply_markup=main_menu()); return
        if mode=="loc_ed":
            key=ctx.user_data.pop("loc_key",None); ctx.user_data.pop("mode",None)
            pl=get_place(key) if key else None
            if pl is None:
                await update.message.reply_text("❌ خطا.",reply_markup=main_menu()); return
            parts=[x.strip() for x in text.split("|",1)]
            pl["title"]=parts[0] or SHOP_NAME
            pl["address"]=parts[1] if len(parts)>1 else ""
            await save_places()
            await update.message.reply_text("✅ ذخیره شد.",reply_markup=main_menu())
            await update.message.reply_text(place_text(key),reply_markup=place_kb(key)); return

        if mode=="wh_shifts":
            dk=ctx.user_data.get("wh_day")
            bad="❌ فرمت اشتباه!\nساعت‌ها باید به شکل HH:MM باشند.\nمثال: 11:00-14:00,17:00-23:00"
            try:
                parts=[p.strip() for p in text.translate(FA_DIGITS).split(",") if p.strip()]
                sh=[{"from":p.split("-")[0].strip(),"to":p.split("-")[1].strip()} for p in parts]
            except Exception:
                await update.message.reply_text(bad,reply_markup=cancel_menu()); return
            if not sh or not all(valid_shift(x) for x in sh):
                # حالت را نگه می‌داریم تا ادمین بتواند دوباره تلاش کند
                await update.message.reply_text(bad,reply_markup=cancel_menu()); return
            if dk not in workhours.get("schedule",{}):
                ctx.user_data.pop("mode",None); ctx.user_data.pop("wh_day",None)
                await update.message.reply_text("❌ روز نامعتبر.",reply_markup=main_menu()); return
            ctx.user_data.pop("mode",None); ctx.user_data.pop("wh_day",None)
            workhours["schedule"][dk]["shifts"]=sh; await save_workhours()
            note="\n\n🌙 شیفت نیمه‌شب‌گذر ثبت شد." if any(x["from"]>x["to"] for x in sh) else ""
            await update.message.reply_text(f"✅ ذخیره شد.{note}",reply_markup=main_menu())
            return
        if mode=="wh_mop":
            ctx.user_data.pop("mode",None); workhours["msg_open"]=text; await save_workhours()
            await update.message.reply_text("✅",reply_markup=main_menu()); return
        if mode=="wh_mcl":
            ctx.user_data.pop("mode",None); workhours["msg_closed"]=text; await save_workhours()
            await update.message.reply_text("✅",reply_markup=main_menu()); return

    # ════ user menu ════
    # تشخیص دکمه از روی label (که ممکن است ادمین تغییرش داده باشد)
    pressed = next((m for m in menu_cfg if m["label"]==text and m.get("enabled",True)), None)
    mkey = pressed["key"] if pressed else None

    if mkey=="workhours":
        await record_stat("wh_page",user.id)
        if not workhours.get("enabled",True): await update.message.reply_text("🕐 ساعت کاری تنظیم نشده.",reply_markup=main_menu()); return
        wh=wh_today_block() or ""
        msg=build_msg(text,wh,"workhours")
        kb=InlineKeyboardMarkup([[InlineKeyboardButton("📆 برنامه‌ی هفتگی",callback_data="wh_weekly")]])
        await send_banner(update.message,msg,"workhours",kb=kb); return

    if mkey=="notify":
        await send_notify(update.message,user.id,text); return

    # بخش‌های متنی — پایه (۱ تا ۷) و سفارشی (p_...)
    if mkey and (mkey in MENU_ITEMS or is_custom(mkey)):
        await send_section(update.message,mkey,text,user.id); return

    # پیام آزاد کاربر — اول ببینیم سؤال آماده‌ای جوابش را دارد یا نه.
    # متنِ آزادِ خودِ مدیر از این مسیر کنار می‌رود: نه پاسخ خودکار می‌گیرد،
    # نه فهرست «سؤال‌های بی‌پاسخ» را با پیام‌های داخلی آلوده می‌کند.
    if is_admin(user.id):
        if user.id in test_mode:
            # حالت آزمایش: همان جوابِ مشتری، بی‌آنکه چیزی ثبت یا فرستاده شود
            if await check_abuse(update,ctx,text,user,dry=True): return
            if get_setting("assistant") and get_setting("faq_auto"):
                await assistant_reply(update,ctx,text,user,dry=True)
            else:
                await update.message.reply_text("⚫️ دستیار هوشمند در تنظیمات خاموش است.")
            return
        await update.message.reply_text(
            "پیامِ مدیر به دستیار نمی‌رود — دستیار فقط به مشتری‌ها جواب می‌دهد.\n"
            "🧪 برای امتحانش مثل یک مشتری: /test\n"
            "/admin برای پنل · /start برای منو",
            reply_markup=main_menu())
        return
    if await check_abuse(update,ctx,text,user): return
    # گفت‌وگو دستِ همکار است؟ دستیار کنار می‌کشد و پیام مستقیم به او می‌رسد
    if in_human_mode(user.id):
        if await forward_to_admin(update,ctx,ack=False): return
    if get_setting("assistant") and get_setting("faq_auto"):
        if await assistant_reply(update,ctx,text,user): return
        await update.message.reply_text(
            "متوجه نشدم 🙏 سؤالتون رو جور دیگه بنویسید یا از منوی پایین انتخاب کنید.",
            reply_markup=main_menu())
        return
    hit=faq_match(text) if get_setting("faq_auto") else None
    if hit:
        hit["hits"]=hit.get("hits",0)+1; await save_faq()
        await send_faq(update.message,hit)
        await forward_to_admin(update,ctx,auto=hit)
        return
    await log_unmatched(text,user)
    if await forward_to_admin(update,ctx): return
    await update.message.reply_text(
        "لطفاً یکی از گزینه‌های منوی زیر را انتخاب کنید 👇",reply_markup=main_menu())

async def forward_to_admin(update:Update,ctx:ContextTypes.DEFAULT_TYPE,kind="",auto=None,
                           ack=True,ack_lead="",count=True):
    """پیام مشتری (هر نوعی) را برای ادمین فوروارد و به مشتری تأیید می‌دهد.

    فوروارد برای همه‌ی انواع پیام کار می‌کند — متن، عکس، ویس، ویدیو، فایل،
    مخاطب. قبلاً فقط متن وصل بود و بقیه بی‌صدا دور ریخته می‌شد.
    """
    user=update.effective_user
    if is_admin(user.id) or not get_setting("forward_user_msgs"): return False
    msg=update.message
    if msg is None: return False
    if count:      # دستیار خودش یک‌بار شمرده؛ دوباره‌شماری آمار را دو برابر می‌کرد
        try: await record_event(user.id,EV_MSG)
        except Exception as e: logger.debug(f"record_event msg: {e}")
    uname=f"@{user.username}" if user.username else "—"
    card=(f"<b>💬 {esc(kind or 'پیام')} از مشتری</b>\n{HR}\n"
          f"👤 {esc(user.first_name or '—')}  ·  {esc(uname)}\n🆔 <code>{user.id}</code>")
    ctx_card=""
    try: ctx_card=await customer_card(user.id)
    except Exception as e: logger.debug(f"customer_card: {e}")
    if ctx_card: card += f"\n{HR}\n{ctx_card}"
    if auto:
        # مدیر باید بداند مشتری همین حالا یک جواب گرفته — تا جواب تکراری ندهد
        card += f"\n✅ پاسخ خودکار داده شد: «{esc(faq_title(auto))}»"
    card += "\n↩️ برای پاسخ، روی همین پیام ریپلای کنید."
    delivered=0
    # به همه‌ی مدیرها می‌رود تا هرکس زودتر دید جواب بدهد؛ خطای یکی
    # نباید جلوی بقیه را بگیرد.
    for aid in admin_ids():
        try:
            fwd=await ctx.bot.forward_message(aid,msg.chat_id,msg.message_id)
            note=await ctx.bot.send_message(aid,card,parse_mode="HTML",
                                            reply_to_message_id=fwd.message_id)
            # ریپلای روی هرکدام از این دو پیام باید کار کند
            await link_thread(aid,fwd.message_id,user.id)
            await link_thread(aid,note.message_id,user.id)
            delivered+=1
        except Exception as e:
            logger.error(f"forward user msg → {aid}: {e}")
    if not delivered: return False
    if auto:
        # مشتری همین الان پاسخ گرفت — نه تأیید اضافه لازم دارد، نه باید در
        # صف «بی‌جواب» بنشیند و دو ساعت بعد یادآوری بی‌مورد بفرستد.
        return True
    await mark_open(user.id)
    # وسط گفت‌وگوی زنده با همکار، «پیام شما دریافت شد» بعد از هر جمله فقط مزاحم است
    if not ack: return True
    if ack_lead:
        # لحن دستیار: یک پیام کوتاه و انسانی، نه کارت رسمی
        tail=("پیامتون رسید و همکارم به‌زودی همین‌جا جواب می‌ده." if is_open() else
              f"الان خارج از ساعت کاری هستیم؛ همکارم {next_open_text() or 'به‌محض بازگشایی'} "
              "همین‌جا جوابتون رو می‌ده.")
        try: await msg.reply_text(f"{ack_lead}\n{tail}",reply_markup=main_menu())
        except Exception as e: logger.error(f"ack to user: {e}")
        return True
    # تأیید آگاه از ساعت کاری — «به‌زودی پاسخ می‌دهیم» ساعت ۳ بامداد دروغ است
    if is_open():
        body="همکاران ما به‌زودی پاسخ می‌دهند. 🙏"
    else:
        nx=next_open_text()
        body=("🔴 الان خارج از ساعت کاری هستیم.\n"
              + (f"پاسخ شما {nx} ارسال می‌شود. 🙏" if nx
                 else "به‌محض شروع ساعت کاری پاسخ می‌دهیم. 🙏"))
    try:
        await msg.reply_text(f"<b>✅ پیام شما دریافت شد</b>\n{HR}\n{body}",
                             parse_mode="HTML",reply_markup=main_menu())
    except Exception as e:
        logger.error(f"ack to user: {e}")
    return True

class _ProxyChat:
    """کمترین چیزی که send_faq لازم دارد تا به‌جای «پاسخ در همین چت»،
    برای چتِ مشتری بفرستد."""
    def __init__(self,bot,chat_id): self.bot=bot; self.chat_id=chat_id
    async def reply_text(self,text,**kw):  return await self.bot.send_message(self.chat_id,text,**kw)
    async def reply_photo(self,photo,**kw): return await self.bot.send_photo(self.chat_id,photo=photo,**kw)

async def _ok_mark(bot,msg,fallback="✅ ارسال شد"):
    """تأیید بی‌سروصدا با ری‌اکشن؛ اگر نشد، یک پیام کوتاه."""
    try:
        await bot.set_message_reaction(chat_id=msg.chat_id,message_id=msg.message_id,
                                       reaction="👍")
    except Exception:
        try: await msg.reply_text(fallback)
        except Exception: pass

async def reply_relay(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    """پاسخ مدیر با همان کار طبیعی تلگرام: ریپلای روی پیام مشتری.

    هیچ پنل یا حالت جداگانه‌ای در کار نیست — مدیر در چت خودش با ربات
    روی پیام فوروارد‌شده ریپلای می‌زند و همان پیام (متن، عکس، ویس، فایل…)
    عیناً برای مشتری می‌رود. اگر ریپلای به رشته‌ی شناخته‌شده‌ای نباشد،
    این هندلر کاری نمی‌کند و پیام مسیر عادی خودش را می‌رود.
    """
    msg=update.message; user=update.effective_user
    if msg is None or user is None or not is_admin(user.id): return
    src=msg.reply_to_message
    if src is None: return
    target=await thread_user(user.id,src.message_id)
    if target is None: return          # ریپلای بی‌ربط — بگذار بقیه رسیدگی کنند
    # میان‌بر: به‌جای تایپ دوباره‌ی متن، فقط #کلیدواژه — همان جواب آماده می‌رود.
    # با دو مدیر یعنی جواب‌ها یکدست هم می‌مانند.
    body=(msg.text or "").strip()
    if get_setting("faq_shortcut") and body.startswith("#") and len(body.split())==1:
        it=faq_by_key(body[1:])
        if not it:
            await msg.reply_text(
                f"❌ سؤال آماده‌ای با کلیدواژه‌ی «{body[1:]}» نیست. "
                f"فهرست: پنل ← محتوای ربات ← سؤال‌های آماده")
            raise ApplicationHandlerStop
        try:
            await send_faq(_ProxyChat(ctx.bot,target),it,footer=False)
        except Forbidden:
            await mark_left(target)
            await msg.reply_text("🚪 این مشتری ربات را بلاک یا حذف کرده — پیام به او نمی‌رسد.")
            raise ApplicationHandlerStop
        except Exception as e:
            logger.error(f"faq shortcut → {target}: {e}")
            await msg.reply_text(f"❌ ارسال نشد: {e}"); raise ApplicationHandlerStop
        it["hits"]=it.get("hits",0)+1; await save_faq()
        await link_thread(user.id,msg.message_id,target)
        await mark_answered(target); set_human(target)
        await _ok_mark(ctx.bot,msg,f"✅ «{faq_title(it)}» ارسال شد")
        raise ApplicationHandlerStop
    try:
        # copy_message یعنی پیام بدون برچسب «فوروارد از» می‌رسد — انگار
        # خودِ فروشگاه نوشته. همه‌ی انواع پیام را هم پشتیبانی می‌کند.
        await ctx.bot.copy_message(chat_id=target,from_chat_id=msg.chat_id,
                                   message_id=msg.message_id)
    except Forbidden:
        await mark_left(target)
        await msg.reply_text("🚪 این مشتری ربات را بلاک یا حذف کرده — پیام به او نمی‌رسد.")
        raise ApplicationHandlerStop
    except Exception as e:
        logger.error(f"relay → {target}: {e}")
        await msg.reply_text(f"❌ ارسال نشد: {e}")
        raise ApplicationHandlerStop
    # پاسخ خودِ مدیر هم به همین مشتری گره می‌خورد تا رشته ادامه پیدا کند
    await link_thread(user.id,msg.message_id,target)
    await mark_answered(target); set_human(target)
    await _ok_mark(ctx.bot,msg)
    raise ApplicationHandlerStop


# ════════════════════════════════════════════════
#  دستیار هوشمند — گفت‌وگوی طبیعی بدون API
# ════════════════════════════════════════════════
# فهمِ پیام در brain.py است؛ اینجا فقط تصمیم می‌گیریم چه بفرستیم.
# دستیار فقط از داده‌ی خودِ ربات حرف می‌زند (متن بخش‌ها، نیت‌ها، ساعت کاری،
# لیست قیمت) و اگر نفهمد، حدس نمی‌زند: پیام را به همکار می‌سپارد.

# «کار»ی که هر نیت انجام می‌دهد، علاوه بر متنش
ACTIONS = {"":       "💬 فقط متن پاسخ",
           "hours":  "🕐 ساعت کاری امروز",
           "prices": "💰 لیست قیمت (عکس تاریخ‌دار)",
           "notify": "🔔 صفحه‌ی اطلاع‌رسانی",
           "human":  "🧑‍💼 سپردن به همکار"}

def action_label(a):
    a=a or ""
    if a.startswith("section:"):
        return "📋 نمایش بخش «"+SECTION_NAMES.get(a[8:],a[8:])+"»"
    return ACTIONS.get(a,a)

# نیت‌های پیش‌فرض استوک‌لند — با اطلاعات واقعی فروشگاه. هرکدام که «کار»ش
# نمایش یک بخش است، متنش را از همان بخش پنل می‌خواند (اقساط، آدرس، شبکه‌ها،
# سایت، پشتیبانی)؛ پس اگر متن بخش را در پنل عوض کنید، جواب دستیار هم عوض
# می‌شود. هر نیت را می‌شود از پنل ویرایش، خاموش یا حذف کرد.
_SHOP_LINE = ("آیفون، آیپد، مک‌بوک، اپل‌واچ، ایرپاد و لوازم جانبی — هم آک (نو و پلمب) "
              "با گارانتی شرکتی، هم کارکرده‌ی تمیز با ۷ روز مهلت تست.")
DEFAULT_INTENTS = [
  {"id":"i_price","button":"💰 لیست قیمت","action":"prices",
   "keys":["قیمت","لیست قیمت","چند تومن","چند تومنه","نرخ روز","قیمتا","چقدر","چنده"],
   "examples":["قیمت گوشیاتون چنده","لیست قیمتتون رو بفرستید","قیمت امروز چنده"],
   "answer":"قیمت روز {product} 👇\n---\nلیست قیمت امروز {product} 👇\n---\nاینم قیمت‌های امروز 👇",
   "suggest":["i_install","i_registry","i_human"]},
  {"id":"i_stock","button":"📦 موجودی","action":"",
   "keys":["موجودی","موجود","موجوده","دارید","دارین"],
   "examples":["الان موجود دارید","این مدل رو دارید"],
   "answer":"موجودی {product} لحظه‌ای عوض می‌شه 🙂 تو سایت و پیج به‌روزش می‌کنیم.\n---\n"
            "موجودی {product} رو تو سایت و پیج به‌روز نگه می‌داریم 🙂",
   "suggest":["i_site","i_social"],
   "offer":"بدم همکارم همین الان موجودی رو براتون چک کنه؟","offer_to":"i_human"},
  {"id":"i_products","button":"🍏 محصولات ما","action":"",
   "keys":["محصولات","چه محصولاتی","چی میفروشید","چیا دارید","چه مدل هایی"],
   "examples":["چه گوشی هایی دارید","چیا میفروشید","فقط ایفون دارید"],
   "answer":"تو استوک‌لند تخصصی محصولات اپل داریم 🍏\n\n• آیفون\n• آیپد\n• مک‌بوک\n• اپل‌واچ\n"
            "• ایرپاد\n• لوازم جانبی\n\nهم آک (نو و پلمب) با گارانتی شرکتی، "
            "هم کارکرده‌ی تمیز با ۷ روز مهلت تست.",
   "suggest":["i_price","i_site"]},
  {"id":"i_android","button":"🤖 گوشی غیر اپل","action":"",
   "keys":["سامسونگ","شیائومی","اندروید","گلکسی","هواوی","پوکو","ناتینگ"],
   "answer":"ما تخصصی فقط محصولات اپل کار می‌کنیم 🍏 آیفون، آیپد، مک‌بوک، اپل‌واچ، "
            "ایرپاد و لوازم جانبی.",
   "suggest":["i_products","i_price"]},
  {"id":"i_accessory","button":"🎧 لوازم جانبی","action":"",
   "keys":["لوازم جانبی","قاب","گلس","شارژر","کابل","هندزفری","محافظ صفحه","کلگی"],
   "answer":"لوازم جانبی اپل هم داریم 👌 شارژر، کابل، قاب، گلس و…\n"
            "برای مدل و موجودی، همکارم دقیق راهنمایی‌تون می‌کنه.",
   "suggest":["i_human"],
   "offer":"بدم به همکارم که موجودی رو بگه؟","offer_to":"i_human"},
  {"id":"i_condition","button":"✨ آک یا کارکرده","action":"",
   "keys":["اک","پلمب","استوک","کارکرده","دست دوم","کار کرده","نو"],
   "examples":["گوشیاتون نو هستن","استوک تمیز دارید","فرق اک با استوک چیه"],
   "answer":"هر دو رو داریم 🙂\n\n📦 آک: نو و پلمب، با گارانتی شرکتی خودش\n"
            "🔍 کارکرده (استوک): تمیز و بررسی‌شده، با ۷ روز مهلت تست",
   "suggest":["i_price","i_warranty"]},
  {"id":"i_registry","button":"📶 رجیستری","action":"",
   "keys":["رجیستر","رجیستری","رجیستر شده","ریجستر","رجستر"],
   "examples":["ایفوناتون رجیستر شدن","رجیستر نشده دارید"],
   "answer":"هر دو نوع رو داریم: رجیستر شده و رجیستر نشده 📶\n"
            "قیمت هر کدوم تو لیست قیمت جدا مشخص شده.",
   "suggest":["i_human"],
   "offer":"لیست قیمت امروز رو بفرستم؟","offer_to":"i_price"},
  {"id":"i_install","button":"💳 خرید اقساطی","action":"section:3",
   "keys":["قسط","اقساط","چک","طلا","شرایط خرید","پیش پرداخت","بدون ضامن"],
   "examples":["با چک میشه خرید","شرایط قسطی چطوره","طلا میگیرید"],
   "answer":"","suggest":["i_payment","i_human"],
   "offer":"لیست قیمت امروز رو هم ببینید؟","offer_to":"i_price"},
  {"id":"i_payment","button":"💳 روش پرداخت","action":"",
   "keys":["پرداخت","کارتخوان","کارت به کارت","نقدی","نقد","درگاه","پوز","روش پرداخت"],
   "examples":["چطوری پول رو بدم","با کارت میشه حساب کرد"],
   "answer":"پرداخت به چند روش ممکنه 💳\n\n• کارتخوان، حضوری در فروشگاه\n• کارت به کارت\n"
            "• درگاه آنلاین سایت\n• اقساطی با چک یا طلا",
   "suggest":["i_install","i_site"]},
  {"id":"i_warranty","button":"🛡 گارانتی","action":"",
   "keys":["گارانتی","گارانتی شرکتی","ضمانت سلامت"],
   "examples":["گوشیاتون گارانتی دارن","کارکرده ها ضمانت دارن"],
   "answer":"📦 گوشی‌های آک (نو و پلمب) گارانتی شرکتی خودشون رو دارن.\n"
            "🔍 گوشی‌های کارکرده هم ۷ روز مهلت تست دارن؛ اگه تو این یه هفته ایراد فنی "
            "دیدید، با همکارم هماهنگ کنید.",
   "suggest":["i_return","i_human"]},
  {"id":"i_return","button":"↩️ مهلت تست و مرجوعی","action":"",
   "keys":["مرجوع","مرجوعی","پس بدم","پس دادن","برگردونم","عودت","مهلت تست","تست"],
   "examples":["اگه خراب بود میتونم پس بدم","چند روز وقت دارم تست کنم"],
   "answer":"۷ روز مهلت تست دارید 🙂 اگه تو این مدت ایراد فنی دیدید، با همکارم هماهنگ "
            "کنید تا بررسی بشه.",
   "suggest":["i_warranty","i_human"]},
  {"id":"i_shipping","button":"🚚 ارسال","action":"",
   "keys":["ارسال","شهرستان","شهر دیگه","ارسال رایگان","ارسال دارید","میفرستید","میفرستین"],
   "examples":["به شهرستان هم میفرستید","برای تهران میفرستید","میتونید بفرستید برام"],
   "answer":"به سراسر ایران ارسال داریم 🚚\nبرای هزینه و زمان رسیدن به شهرتون، همکارم "
            "دقیق راهنمایی‌تون می‌کنه.",
   "suggest":["i_payment"],
   "offer":"بدم به همکارم که هماهنگ کنه؟","offer_to":"i_human"},
  {"id":"i_tradein","button":"🔄 معاوضه و فروش گوشی","action":"",
   "keys":["تعویض","معاوضه","میخرید","بفروشم","خرید کارکرده","عوض کنم"],
   "examples":["گوشی خودمو بیارم شما میخرید","گوشی قدیمیمو میخرید",
               "گوشیمو با ایفون جدید عوض میکنید"],
   "answer":"هم معاوضه داریم، هم گوشی کارکرده‌تون رو می‌خریم 🔄\n"
            "قیمتش بعد از دیدن و بررسی گوشی مشخص می‌شه؛ می‌تونید حضوری بیارید فروشگاه، "
            "یا مدل و وضعیتش رو همین‌جا بنویسید تا همکارم راهنمایی‌تون کنه.",
   "suggest":["i_address","i_human"]},
  {"id":"i_software","button":"🛠 خدمات نرم‌افزاری","action":"section:4",
   "keys":["اپل ایدی","اپلایدی","apple id","ایکلود","icloud","نصب برنامه","انتقال اطلاعات",
           "نرم افزار","نصب"],
   "examples":["اپل ایدی میسازید","برنامه نصب میکنید","اطلاعات گوشی قبلیمو منتقل میکنید"],
   "answer":"خدمات نرم‌افزاری هم داریم 🛠\n\n• ساخت اپل‌آیدی\n• نصب برنامه\n"
            "• انتقال اطلاعات از گوشی قبلی\n\nبرای هماهنگی 👇",
   "suggest":["i_human"]},
  {"id":"i_address","button":"📍 آدرس و مسیر","action":"section:5",
   "keys":["ادرس","لوکیشن","کجا","مسیر","نقشه","حضوری","مغازه","فروشگاه کجاست",
           "چطوری بیام","چجوری بیام","کجا بیام"],
   "answer":"","suggest":["i_hours"]},
  {"id":"i_hours","button":"🕐 ساعت کاری","action":"hours",
   "keys":["ساعت کاری","ساعت کار","ساعت چند","تا ساعت","از ساعت چند","تا کی",
           "چه ساعتی","باز","بسته","تعطیل"],
   "answer":"","suggest":["i_address"],
   "offer":"آدرس و مسیر مغازه رو هم براتون بفرستم؟","offer_to":"i_address"},
  {"id":"i_site","button":"🌐 سایت","action":"section:2",
   "keys":["سایت","ادرس سایت","خرید انلاین","سفارش انلاین"],"answer":""},
  {"id":"i_social","button":"📸 اینستاگرام و کانال","action":"section:1",
   "keys":["اینستاگرام","کانال","شبکه اجتماعی","شبکه های اجتماعی","بله","روبیکا"],"answer":""},
  {"id":"i_about","button":"🏬 درباره‌ی استوک‌لند","action":"",
   "keys":["درباره استوک لند"],
   "examples":["استوک لند چیه","شما کی هستید","چیکار میکنید","کارتون چیه"],
   "answer":"استوک‌لند فروشگاه تخصصی محصولات اپل در قمه 🍏\n"+_SHOP_LINE+
            "\nفروش نقدی و اقساطی (چک و طلا) و ارسال به سراسر ایران.",
   "suggest":["i_address","i_social"]},
  {"id":"i_notify","button":"🔔 خبرم کن","action":"notify",
   "keys":["خبرم کنید","خبرم کن","اطلاع بدید","تخفیف","جشنواره"],
   "answer":"حتماً 🙂 هر موضوعی که می‌خواید خبرش رو بگیرید انتخاب کنید 👇"},
  {"id":"i_phone","button":"📞 شماره تماس","action":"section:4",
   "keys":["شماره","شماره تماس","تلفن","زنگ","تماس","پشتیبانی","شمارتون","تلفن مغازه","شماره مغازه"],
   "answer":"","suggest":["i_human"]},
  {"id":"i_human","button":"🧑‍💼 صحبت با همکار","action":"human",
   "keys":["همکار","صحبت کنم","کسی هست","حرف بزنم","ادم واقعی"],
   "examples":["میخوام با یکی حرف بزنم","یکی جواب بده","با خود فروشنده کار دارم"],
   "answer":"حتماً 🙏 پیامتون رو به همکارم دادم و خودش همین‌جا جوابتون رو می‌ده.\n---\n"
            "چشم 🙏 به همکارم خبر دادم؛ به‌زودی همین‌جا جوابتون رو می‌ده."},
]
QUICK_INTENTS = ["i_price","i_install","i_address","i_human"]   # زیر سلام و احوال‌پرسی

# ── به‌روزرسانی نیت‌های پیش‌فرض بدون دست زدن به کارِ ادمین
# هر نیت پیش‌فرض یک «عکس» از نسخه‌ای که کاشته شده نگه می‌دارد (_seed). در
# نسخه‌ی تازه، هر فیلدی که ادمین دست نزده (هنوز برابر همان عکس است) به‌روز
# می‌شود؛ هر فیلدی که خودش نوشته دست‌نخورده می‌ماند. در کلیدواژه‌ها و
# جمله‌های نمونه، فقط موردهای تازه اضافه می‌شوند — چیزی که ادمین پاک کرده
# برنمی‌گردد. نیتی که ادمین حذف کرده هم دوباره ساخته نمی‌شود.
SEED_VERSION = 2
_SEED_SCALARS = ("button","answer","action","suggest","offer","offer_to","enabled")
_SEED_LISTS = ("keys","examples")

def _seed_h(v):
    return hashlib.sha1(json.dumps(v,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:10]

def _seed_snapshot(d):
    return {"h":{f:_seed_h(d.get(f,True if f=="enabled" else None)) for f in _SEED_SCALARS},
            **{f:list(d.get(f,[])) for f in _SEED_LISTS}}

# نسخه‌ی ۱ (پیش از ذخیره‌ی _seed) — فقط برای ارتقای نصب‌های قبلی
_SEED_V1 = {
  'i_price':{"h": {"button": "a4ffba70ce", "answer": "9b0bc4d62a", "action": "58fc4e0e6b", "suggest": "dd93a11665", "offer": "2be88ca424", "offer_to": "2be88ca424", "enabled": "5ffe533b83"}, "keys": ["قیمت", "لیست قیمت", "چند تومن", "چند تومنه", "نرخ روز", "قیمتا", "چقدر", "چنده"], "examples": []},
  'i_stock':{"h": {"button": "7724634990", "answer": "e1ffc610b8", "action": "7db8b8b5df", "suggest": "fb737964ce", "offer": "2be88ca424", "offer_to": "2be88ca424", "enabled": "5ffe533b83"}, "keys": ["موجودی", "موجود", "موجوده", "دارید", "دارین"], "examples": []},
  'i_install':{"h": {"button": "fb5121618e", "answer": "dd29ecf524", "action": "684482763c", "suggest": "fb737964ce", "offer": "4dee737341", "offer_to": "39f17ffeea", "enabled": "5ffe533b83"}, "keys": ["قسط", "اقساط", "چک", "طلا", "شرایط خرید", "پیش پرداخت", "بدون ضامن"], "examples": []},
  'i_address':{"h": {"button": "a188c160b7", "answer": "dd29ecf524", "action": "42379e30bd", "suggest": "7f48788959", "offer": "2be88ca424", "offer_to": "2be88ca424", "enabled": "5ffe533b83"}, "keys": ["ادرس", "لوکیشن", "کجا", "مسیر", "نقشه", "حضوری", "مغازه", "فروشگاه کجاست", "چطوری بیام", "چجوری بیام", "کجا بیام"], "examples": []},
  'i_hours':{"h": {"button": "d69e4a06a6", "answer": "dd29ecf524", "action": "f333e3fb14", "suggest": "ebcdd6edef", "offer": "00da6ffb58", "offer_to": "530cd3b605", "enabled": "5ffe533b83"}, "keys": ["ساعت کاری", "ساعت کار", "ساعت چند", "تا ساعت", "از ساعت چند", "تا کی", "چه ساعتی", "باز", "بسته", "تعطیل"], "examples": []},
  'i_site':{"h": {"button": "97f49cec50", "answer": "dd29ecf524", "action": "3b46d3f7f3", "suggest": "2be88ca424", "offer": "2be88ca424", "offer_to": "2be88ca424", "enabled": "5ffe533b83"}, "keys": ["سایت", "ادرس سایت", "خرید انلاین", "سفارش انلاین"], "examples": []},
  'i_social':{"h": {"button": "cb80b69145", "answer": "dd29ecf524", "action": "7db8b8b5df", "suggest": "2be88ca424", "offer": "2be88ca424", "offer_to": "2be88ca424", "enabled": "5ffe533b83"}, "keys": ["اینستاگرام", "کانال", "شبکه اجتماعی", "شبکه های اجتماعی"], "examples": []},
  'i_notify':{"h": {"button": "6fa3f3e463", "answer": "62ed694b3f", "action": "3faa602f31", "suggest": "2be88ca424", "offer": "2be88ca424", "offer_to": "2be88ca424", "enabled": "5ffe533b83"}, "keys": ["خبرم کنید", "خبرم کن", "اطلاع بدید", "تخفیف", "جشنواره"], "examples": []},
  'i_human':{"h": {"button": "c067ea5750", "answer": "660fef9b6a", "action": "353f64ee59", "suggest": "2be88ca424", "offer": "2be88ca424", "offer_to": "2be88ca424", "enabled": "5ffe533b83"}, "keys": ["همکار", "تماس", "شماره", "زنگ", "صحبت کنم", "کسی هست", "پشتیبانی"], "examples": []},
  'i_warranty':{"h": {"button": "621c00e6ce", "answer": "21ac6d5ce7", "action": "2be88ca424", "suggest": "11115ef936", "offer": "2be88ca424", "offer_to": "2be88ca424", "enabled": "7cb6efb98b"}, "keys": ["گارانتی", "ضمانت اصالت", "اصالت"], "examples": []},
  'i_shipping':{"h": {"button": "3bdba9ee14", "answer": "26a2eb31cf", "action": "2be88ca424", "suggest": "11115ef936", "offer": "2be88ca424", "offer_to": "2be88ca424", "enabled": "7cb6efb98b"}, "keys": ["ارسال", "شهرستان", "شهر دیگه", "ارسال رایگان"], "examples": []},
  'i_tradein':{"h": {"button": "e20e514ef8", "answer": "44011de9b0", "action": "2be88ca424", "suggest": "11115ef936", "offer": "2be88ca424", "offer_to": "2be88ca424", "enabled": "7cb6efb98b"}, "keys": ["تعویض", "معاوضه", "کارکرده", "میخرید", "بفروشم", "دست دوم"], "examples": ["گوشی خودمو بیارم شما میخرید", "گوشی قدیمیمو میخرید"]},
}

def _upgrade_intent(it,d):
    """فیلدهای دست‌نخورده‌ی یک نیت پیش‌فرض را به نسخه‌ی تازه می‌برد."""
    base=it.get("_seed") or _SEED_V1.get(it["id"])
    if not base: return False
    changed=False
    for f in _SEED_SCALARS:
        cur=it.get(f,True if f=="enabled" else None)
        new=d.get(f,True if f=="enabled" else None)
        if _seed_h(cur)==base["h"].get(f) and cur!=new:
            if new is None: it.pop(f,None)
            else: it[f]=list(new) if isinstance(new,list) else new
            changed=True
    for f in _SEED_LISTS:
        cur=list(it.get(f,[])); old=set(base.get(f,[]))
        if cur==base.get(f,[]): merged=list(d.get(f,[]))
        else: merged=cur+[x for x in d.get(f,[]) if x not in old and x not in cur]
        if merged!=cur:
            if merged: it[f]=merged
            else: it.pop(f,None)
            changed=True
    snap=_seed_snapshot(d)
    if it.get("_seed")!=snap: it["_seed"]=snap; changed=True
    return changed

async def seed_intents():
    """نیت‌های پیش‌فرض را می‌کارد یا به نسخه‌ی تازه می‌برد.

    هرچه ادمین خودش نوشته محترم است: اگر سؤال آماده‌ای با همان کلیدواژه‌ها
    دارد و متنش واقعی است، پیش‌فرضِ هم‌کلید اضافه نمی‌شود. فقط نمونه‌های
    خالیِ نسخه‌های قبلی («… را اینجا بنویسید») جایشان را به نسخه‌ی کامل
    می‌دهند."""
    if settings.get("assistant_seed_v",0)>=SEED_VERSION: return
    # نصبی که نسخه‌ی ۱ را کاشته بود: همه‌ی آن شناسه‌ها «دیده شده‌اند» —
    # اگر الان نیستند یعنی ادمین حذفشان کرده
    seen=set(settings.get("assistant_ids") or
             (_SEED_V1.keys() if settings.get("assistant_seeded") else ()))
    ours={d["id"] for d in DEFAULT_INTENTS}
    changed=False
    for d in DEFAULT_INTENTS:
        it=faq_item(d["id"])
        if it:
            changed|=_upgrade_intent(it,d); seen.add(d["id"]); continue
        if d["id"] in seen: continue
        seen.add(d["id"])
        dkeys={brain.norm(k) for k in d["keys"]}
        clash=[x for x in faq if x.get("id") not in ours
               and dkeys & {brain.norm(k) for k in x.get("keys",[])}]
        real=[x for x in clash if x.get("enabled",True) or PLACEHOLDER_MARK not in x.get("answer","")]
        if real: continue
        for x in clash: faq.remove(x)
        it={k:(list(v) if isinstance(v,list) else v) for k,v in d.items()}
        it.setdefault("enabled",True); it.setdefault("hits",0)
        it["_seed"]=_seed_snapshot(d)
        faq.append(it); changed=True
    settings.update(assistant_seeded=True,assistant_seed_v=SEED_VERSION,
                    assistant_ids=sorted(seen))
    await save_settings()
    if changed:
        await save_faq(); logger.info(f"assistant: نیت‌های پیش‌فرض نسخه‌ی {SEED_VERSION}")

def brain_intents():
    return [x for x in faq if x.get("enabled",True)]

# ── حافظه‌ی کوتاه گفت‌وگو (در حافظه؛ با ری‌استارت پاک می‌شود و اشکالی ندارد)
brain_ctx: dict = {}      # uid → {"intent","ts","offer","offer_ts"}
human_until: dict = {}    # uid → تا کِی گفت‌وگو دست همکار است
CTX_TTL, OFFER_TTL, HUMAN_TTL = 15*60, 10*60, 30*60

def in_human_mode(uid): return human_until.get(uid,0)>time.time()

def set_human(uid):
    """همکار وارد گفت‌وگو شد: دستیار برای این مشتری کنار می‌کشد تا
    وسط حرفِ آدم‌ها جواب خودکار نپرد."""
    human_until[uid]=time.time()+HUMAN_TTL; brain_ctx.pop(uid,None)

def suggest_rows(item=None,ids=None):
    ids=ids if ids is not None else (item.get("suggest") or [] if item else [])
    btns=[]
    for i in ids:
        it=faq_item(i)
        if it and it.get("enabled",True) and (it.get("answer") or it.get("action")):
            btns.append(InlineKeyboardButton(faq_title(it),callback_data=f"ai_{it['id']}"))
    return [btns[i:i+2] for i in range(0,len(btns),2)]

async def _typing(bot,chat_id,n=80):
    """«در حال نوشتن…» برای یک لحظه — جواب فوری و بی‌مکث، ماشینی به نظر می‌رسد."""
    if not get_setting("typing_delay"): return
    try:
        await bot.send_chat_action(chat_id=chat_id,action="typing")
        await asyncio.sleep(min(1.4,0.45+n/400))
    except Exception: pass

def _join(*parts): return "\n\n".join(p for p in parts if p and p.strip())

async def run_intent(msg,item,user,bot,lead="",product="",dry=False):
    """یک نیت را اجرا می‌کند: متن (چندشکلی، پرشده) + کارِ نیت + پیشنهادها."""
    uid=user.id
    values={"name":(user.first_name or "").strip()[:20],"product":product,
            "shop":SHOP_NAME,"status":status_line() or "","hours":wh_today_block() or ""}
    answer=brain.fill(brain.pick_variant(item.get("answer",""),product=product),**values)
    action=item.get("action") or ""
    rows=suggest_rows(item)
    if not dry:
        item["hits"]=item.get("hits",0)+1; await save_faq()
        if not action.startswith("section:"):
            try: await record_event(uid,f"ai:{item['id']}")
            except Exception as e: logger.debug(f"ai event: {e}")

    if action.startswith("section:") and action[8:] in SECTION_NAMES:
        pre=_join(lead,answer)
        if pre: await msg.reply_text(pre,reply_markup=main_menu())
        await send_section(msg,action[8:],uid=None if dry else uid,extra_rows=rows)
    elif action=="hours":
        body=_join(lead,answer,status_line() or "",wh_today_block() or "")
        rows=rows+[[InlineKeyboardButton("📆 برنامه‌ی هفتگی",callback_data="wh_weekly")]]
        await msg.reply_text(body or "🕐",reply_markup=InlineKeyboardMarkup(rows))
    elif action=="prices":
        pic=item if item.get("photo") else next(
            (x for x in faq if x.get("photo") and any(brain.norm(k)==brain.PRICE_KEY
                                                      for k in x.get("keys",[]))),None)
        if pic:
            shown=dict(pic); shown["answer"]=answer or pic.get("answer","")
            await send_faq(msg,shown,chat=True,lead=lead,values=values,extra_rows=rows)
        else:
            await msg.reply_text(_join(lead,"قیمت‌های روز رو همیشه تو سایت به‌روز داریم 👇"),
                                 reply_markup=main_menu())
            await send_section(msg,"2",uid=None if dry else uid,extra_rows=rows)
    elif action=="notify":
        pre=_join(lead,answer)
        if pre: await msg.reply_text(pre,reply_markup=main_menu())
        await send_notify(msg,uid)
    elif action=="human":
        await msg.reply_text(_join(lead,answer) or "🙏",reply_markup=main_menu())
        if not dry: set_human(uid)
    else:
        await send_faq(msg,item,chat=True,lead=lead,values=values,extra_rows=rows)

    # پیشنهادِ قدم بعد به شکل سؤال: «آدرس رو هم بفرستم؟» — جوابِ «آره»ی
    # مشتری همین را اجرا می‌کند
    c={"intent":item["id"],"ts":time.time(),
       "product":product or (brain_ctx.get(uid) or {}).get("product","")}
    to=faq_item(item.get("offer_to") or "")
    if item.get("offer") and to and to.get("enabled",True):
        await msg.reply_text(item["offer"],reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("👍 بله",callback_data=f"ai_{to['id']}")]]))
        c.update(offer=to["id"],offer_ts=time.time())
    brain_ctx[uid]=c

async def notify_handoff(bot,user,why="درخواست صحبت با همکار"):
    """وقتی مشتری با دکمه (نه با پیام) همکار را خواست، پیامی نیست که فوروارد
    شود؛ یک کارت برای مدیرها می‌رود که روی همان ریپلای بزنند."""
    card=(f"<b>🧑‍💼 {esc(why)}</b>\n{HR}\n"
          f"👤 {esc(user.first_name or '—')}"+(f"  ·  @{esc(user.username)}" if user.username else "")+
          f"\n🆔 <code>{user.id}</code>")
    try:
        extra=await customer_card(user.id)
        if extra: card+=f"\n{HR}\n{extra}"
    except Exception: pass
    card+="\n↩️ برای پاسخ، روی همین پیام ریپلای کنید."
    for aid in admin_ids():
        try:
            m=await bot.send_message(aid,card,parse_mode="HTML")
            await link_thread(aid,m.message_id,user.id)
        except Exception as e: logger.error(f"handoff → {aid}: {e}")
    await mark_open(user.id)

async def assistant_reply(update,ctx,text,user,dry=False):
    """پاسخ دستیار به یک پیام متنی مشتری. True یعنی رسیدگی شد.

    ترتیب: پاسخِ «آره/نه» به پیشنهاد قبلی → نیتِ پیام → ادامه‌ی بحث قبلی →
    حرفِ روزمره → و اگر هیچ‌کدام، صادقانه به همکار سپردن."""
    msg=update.message; uid=user.id; now=time.time()
    a=brain.analyze(text,brain_intents())
    tags=a["tags"]; c=brain_ctx.get(uid) or {}
    name=(user.first_name or "").strip()[:20]
    hour=datetime.now(IRAN_TZ).hour
    lead=""
    if "greet" in tags: lead=brain.greet_line(name,hour,text=text)
    if "tired" in tags: lead=_join(lead,brain.say("tired"))
    if not dry:
        try: await record_event(uid,EV_MSG)
        except Exception as e: logger.debug(f"ev msg: {e}")

    # ۱) «آره» / «نه» به پیشنهاد قبلی
    if c.get("offer") and now-c.get("offer_ts",0)<OFFER_TTL and ("yes" in tags or "no" in tags):
        if "yes" in tags and faq_item(c["offer"]):
            await _typing(ctx.bot,msg.chat_id)
            await run_intent(msg,faq_item(c["offer"]),user,ctx.bot,lead=lead,dry=dry)
        else:
            brain_ctx.pop(uid,None)
            await msg.reply_text(_join(lead,brain.say("no")),reply_markup=main_menu())
        return True

    # ۲) نیت پیام، یا ادامه‌ی بحث قبلی («واسه ۱۴ چی؟»)
    item=a["intent"]; follow=""
    fresh=now-c.get("ts",0)<CTX_TTL
    prod=brain.carry_product(text,c.get("product","") if fresh else "")
    if not item and (a["followup"] or prod) and c.get("intent") and fresh:
        item=faq_item(c["intent"])
        if item and prod: follow=f"برای {prod} 👇"
    if item:
        await _typing(ctx.bot,msg.chat_id,len(item.get("answer","")))
        await run_intent(msg,item,user,ctx.bot,lead=_join(lead,follow),
                         product=prod,dry=dry)
        if not dry:
            if (item.get("action") or "")=="human":
                await forward_to_admin(update,ctx,ack=False,count=False)
            elif get_setting("ai_cc_admin"):
                await forward_to_admin(update,ctx,auto=item,count=False)
        return True

    # ۳) فقط حرف روزمره: سلام، مرسی، خداحافظ، خوبی؟، «رباتی؟»
    if tags and not a["rest"]:
        lines=[lead] if lead else []
        quick=None
        if "who" in tags:
            lines.append(brain.who_reply(SHOP_NAME)); quick=suggest_rows(ids=["i_human"])
        if "how" in tags: lines.append(brain.say("how"))
        if "thanks" in tags: lines.append(brain.say("thanks"))
        if "bye" in tags: lines.append(brain.say("bye"))
        if "laugh" in tags: lines.append(brain.say("laugh"))
        if "no" in tags: lines.append(brain.say("no"))
        if ("yes" in tags or ("greet" in tags and len(lines)==1)
                or ("tired" in tags and len(lines)<=1)):
            lines.append(brain.say("greet_only" if ("greet" in tags or "tired" in tags)
                                   else "yes_nothing"))
            quick=suggest_rows(ids=QUICK_INTENTS)
        await _typing(ctx.bot,msg.chat_id)
        await msg.reply_text(_join(*lines) or "🙂",
                             reply_markup=InlineKeyboardMarkup(quick) if quick else main_menu())
        return True

    # ۴) نفهمیدم — حدس نمی‌زنیم؛ به همکار می‌سپاریم
    if dry:
        await msg.reply_text(_join(lead,random.choice(brain.UNKNOWN_LEADS),
                                   "(در حالت واقعی، پیام برای همکار فرستاده می‌شد)"))
        return True
    await log_unmatched(text,user)
    return await forward_to_admin(update,ctx,count=False,
                                  ack_lead=_join(lead,random.choice(brain.UNKNOWN_LEADS)))

# ════════════════════════════════════════════════
#  برخورد با توهین
# ════════════════════════════════════════════════
# بار اول تذکر محترمانه، بار دوم هشدار، بار سوم (در ۲۴ ساعت) گفتگو یک ساعت
# متوقف می‌شود و مدیرها خبردار می‌شوند. پیام توهین‌آمیز نه جواب خودکار
# می‌گیرد و نه برای همکارها فوروارد می‌شود. شمارش در حافظه است.
abuse_hits: dict = {}     # uid → [زمان‌ها]
muted_until: dict = {}    # uid → تا کِی پیام‌هایش نادیده گرفته می‌شود
ABUSE_WINDOW, MUTE_MIN = 24*3600, 60

def is_muted(uid): return muted_until.get(uid,0)>time.time()

async def check_abuse(update,ctx,text,user,dry=False):
    """True یعنی پیام رسیدگی شد (توهین بود یا کاربر موقتاً ساکت است) و
    نباید جلوتر برود."""
    if not get_setting("profanity_filter"): return False
    uid=user.id; msg=update.message
    if not dry and is_muted(uid): return True
    hit=profanity.find(text,settings.get("bad_words_extra") or ())
    if not hit: return False
    if dry:
        await msg.reply_text(random.choice(profanity.WARN_1)+
                             f"\n\n🧪 (حالت آزمایش — تشخیص: «{hit}»)")
        return True
    now=time.time()
    hits=[t for t in abuse_hits.get(uid,[]) if now-t<ABUSE_WINDOW]+[now]
    abuse_hits[uid]=hits
    try: await record_event(uid,EV_ABUSE)
    except Exception as e: logger.debug(f"ev abuse: {e}")
    brain_ctx.pop(uid,None)
    if len(hits)==1: body=random.choice(profanity.WARN_1)
    elif len(hits)==2: body=profanity.WARN_2
    else:
        muted_until[uid]=now+MUTE_MIN*60; abuse_hits[uid]=[]
        body=profanity.MUTED.format(minutes=to_fa(MUTE_MIN))
        card=(f"<b>⛔️ گفتگو با یک مشتری {to_fa(MUTE_MIN)} دقیقه متوقف شد</b>\n{HR}\n"
              f"دلیل: سه پیام توهین‌آمیز در ۲۴ ساعت\n"
              f"👤 {esc(user.first_name or '—')}"+(f"  ·  @{esc(user.username)}" if user.username else "")+
              f"\n🆔 <code>{uid}</code>\n💬 «{esc(_fit(text,120))}»\n"
              "↩️ اگر لازم است، روی همین پیام ریپلای کنید.")
        for aid in admin_ids():
            try:
                m=await ctx.bot.send_message(aid,card,parse_mode="HTML")
                await link_thread(aid,m.message_id,uid)
            except Exception as e: logger.error(f"abuse → {aid}: {e}")
    try: await msg.reply_text(body,reply_markup=main_menu())
    except Exception as e: logger.error(f"abuse reply: {e}")
    return True

def event_label(k):
    """برچسب خوانای یک رویداد برای کارت شناخت و گزارش هفتگی."""
    if k=="wh_page": return "🕐 ساعت کاری"
    if k.startswith("ai:"):
        it=faq_item(k[3:]); return f"💬 {faq_title(it)}" if it else "💬 پرسش"
    return SECTION_NAMES.get(k,k)

# نوع پیام → برچسبی که در اعلان ادمین می‌آید
_KIND_BY_ATTR = (("voice","🎤 ویس"),("video_note","🎥 ویدیو پیام"),("video","🎬 ویدیو"),
                 ("audio","🎵 صوت"),("photo","🖼 عکس"),("document","📎 فایل"),
                 ("contact","📇 مخاطب"),("sticker","🙂 استیکر"))

async def user_media_handler(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    """رسانه‌ای که مشتری می‌فرستد — عکس، ویس، ویدیو، فایل، مخاطب."""
    user=update.effective_user
    if is_admin(user.id): return          # مسیر ادمین در هندلرهای اختصاصی است
    await save_user(user)
    if await is_blocked(user.id): return
    if spam_check(user.id)!='ok': return
    msg=update.message
    if await check_abuse(update,ctx,msg.caption or "",user): return
    kind=next((lbl for attr,lbl in _KIND_BY_ATTR if getattr(msg,attr,None)),"پیام")
    if not await forward_to_admin(update,ctx,kind,ack=not in_human_mode(user.id)):
        await msg.reply_text(
            "لطفاً یکی از گزینه‌های منوی زیر را انتخاب کنید 👇",reply_markup=main_menu())

# ════════════════════════════════════════════════
#  PHOTO HANDLER
# ════════════════════════════════════════════════
async def photo_handler(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    user=update.effective_user
    # PTB در هر گروه فقط اولین هندلرِ منطبق را اجرا می‌کند؛ چون این هندلر
    # زودتر ثبت شده، عکسِ مشتری باید همین‌جا به مسیر فوروارد سپرده شود
    # وگرنه بی‌صدا دور ریخته می‌شود.
    if not is_admin(user.id):
        return await user_media_handler(update,ctx)
    mode=ctx.user_data.get("mode"); photo=update.message.photo[-1]
    if mode=="ban_up":
        key=ctx.user_data.pop("ban_key",None); ctx.user_data.pop("mode",None)
        if not key: await update.message.reply_text("❌ خطا.",reply_markup=main_menu()); return
        sizes=update.message.photo
        big=sizes[-1]                                   # نسخه‌ی اصلی (سنگین)
        main=pick_photo(sizes) or big                   # نسخه‌ی بهینه برای ارسال
        thumb=pick_photo(sizes,THUMB_MAX_W) or main     # پیش‌نمایش پنل
        b=get_banner(key)
        if b.get("uid") and b["uid"]==main.file_unique_id:
            b["active"]=True; await save_banners()
            await update.message.reply_text(
                "ℹ️ همین تصویر از قبل ثبت شده بود — دوباره آپلود نشد، فقط فعال شد.",
                reply_markup=main_menu()); return
        b.update({"file_id":main.file_id,"uid":main.file_unique_id,
                  "w":getattr(main,"width",0),"h":getattr(main,"height",0),
                  "thumb_id":thumb.file_id,"active":True})
        await save_banners()
        saved=""
        if getattr(big,"file_size",0) and getattr(main,"file_size",0) and main.file_id!=big.file_id:
            saved=(f"\n📉 به‌جای {human_kb(big.file_size)}، نسخه‌ی "
                   f"{human_kb(main.file_size)} استفاده می‌شود.")
        await update.message.reply_text(
            f"✅ بنر «{SECTION_NAMES.get(key,key)}» ثبت شد.\n"
            f"📐 {to_fa(getattr(main,'width',0))}×{to_fa(getattr(main,'height',0))}"
            f"{saved}\n\n♻️ این تصویر فقط یک‌بار آپلود می‌شود و از این پس بدون "
            f"آپلود مجدد برای کاربران ارسال می‌گردد.",
            reply_markup=main_menu()); return
    if mode=="faq_photo":
        fid=ctx.user_data.pop("faq_id",None); ctx.user_data.pop("mode",None)
        it=faq_item(fid)
        if not it:
            await update.message.reply_text("❌ یافت نشد.",reply_markup=main_menu()); return
        await faq_set_photo(update.message,it)
        return
    if mode=="broadcast":
        ctx.user_data.pop("mode",None); caption=update.message.caption or""
        bc=pick_photo(update.message.photo) or photo   # سبک‌تر = ارسال سریع‌تر به همه
        ctx.user_data["bc_text"]=caption; ctx.user_data["bc_photo"]=bc.file_id
        aud=ctx.user_data.get("bc_aud","all"); n=len(await bc_uids(aud))
        await update.message.reply_text(
            f"👁 پیش‌نمایش بالا.\n🎯 {bc_label(aud)} — {to_fa(n)} نفر\nچه کار کنم؟",
            reply_markup=bc_confirm_kb())
        return
    # میان‌بر: عکس با کپشن #کلیدواژه → عکسِ همان سؤال آماده عوض می‌شود.
    # کارِ روزانه‌ی «لیست قیمت امروز» را یک‌مرحله‌ای می‌کند.
    cap=(update.message.caption or "").strip()
    if cap.startswith("#"):
        it=faq_by_key(cap[1:].strip())
        if it:
            await faq_set_photo(update.message,it); return
        await update.message.reply_text(
            f"❌ سؤال آماده‌ای با کلیدواژه‌ی «{cap[1:].strip()}» پیدا نشد.",
            reply_markup=main_menu()); return
async def faq_set_photo(msg,it):
    """عکس سؤال آماده.

    برخلاف بنرها اینجا بزرگ‌ترین نسخه را برمی‌داریم: پای لیست قیمت،
    خوانا بودن متنِ داخل عکس از چند کیلوبایت صرفه‌جویی مهم‌تر است.
    """
    pic=msg.photo[-1]
    it["photo"]=pic.file_id; it["photo_at"]=gregorian_now()
    if not it.get("enabled",True):
        it["enabled"]=True            # عکس گذاشتی یعنی می‌خواهی استفاده شود
    await save_faq()
    size=f"  ·  {human_kb(pic.file_size)}" if getattr(pic,"file_size",0) else ""
    await msg.reply_text(
        f"✅ عکس «{faq_title(it)}» ثبت شد — {faq_photo_stamp(it)}{size}\n"
        f"📐 {to_fa(getattr(pic,'width',0))}×{to_fa(getattr(pic,'height',0))}\n"
        f"♻️ فقط یک‌بار آپلود می‌شود و از این پس بدون آپلود دوباره ارسال می‌گردد.",
        reply_markup=main_menu())

# ════════════════════════════════════════════════
#  LOCATION HANDLER — ثبت لوکیشن بخش‌ها
# ════════════════════════════════════════════════
async def location_handler(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    user=update.effective_user
    if not is_admin(user.id): return
    if ctx.user_data.get("mode")!="loc_up": return
    key=ctx.user_data.pop("loc_key",None); ctx.user_data.pop("mode",None)
    if not key:
        await update.message.reply_text("❌ خطا.",reply_markup=main_menu()); return
    msg=update.message
    # هم «موقعیت مکانی» ساده و هم «مکان/Venue» فورواردشده پشتیبانی می‌شود
    ven=getattr(msg,"venue",None)
    loc=getattr(msg,"location",None) or (ven.location if ven else None)
    if not loc:
        await update.message.reply_text("❌ موقعیت دریافت نشد.",reply_markup=main_menu()); return
    pl=get_place(key)
    pl["lat"]=loc.latitude; pl["lon"]=loc.longitude; pl["active"]=True
    if ven:
        pl["title"]=ven.title or pl.get("title") or SHOP_NAME
        pl["address"]=ven.address or pl.get("address") or ""
    else:
        pl.setdefault("title",SHOP_NAME) or None
        if not pl.get("title"): pl["title"]=SHOP_NAME
        if not pl.get("address"):
            # متن همان بخش (بدون لینک نقشه) به‌عنوان آدرس پیش‌فرض — چون از این
            # پس متن جداگانه‌ای ارسال نمی‌شود و همه‌چیز داخل کارت است
            body=strip_map_links(responses.get(key,"") or "").strip()
            pl["address"]=" ".join(body.split())[:255]
    ok=await save_places()
    await update.message.reply_text(
        ("✅ لوکیشن ثبت و فعال شد." if ok else "⚠️ ثبت شد ولی روی دیسک ذخیره نشد!")
        + "\n\nاز این پس وقتی کاربر این بخش را باز کند، نقشه داخل خودِ تلگرام"
          " برایش می‌آید — بدون نیاز به لینک بیرونی.",
        reply_markup=main_menu())
    try: await send_place_preview(update.message,key)
    except Exception as e: logger.error(f"preview after set: {e}")
    await update.message.reply_text(place_text(key),reply_markup=place_kb(key))

# ════════════════════════════════════════════════
#  DOCUMENT HANDLER (backup import)
# ════════════════════════════════════════════════
async def document_handler(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    user=update.effective_user
    if not is_admin(user.id):
        return await user_media_handler(update,ctx)   # فایل مشتری گم نشود
    mode=ctx.user_data.get("mode")
    if mode!="backup_restore": return
    if not is_owner(user.id):
        ctx.user_data.pop("mode",None)
        return await update.message.reply_text("⛔ بازگردانی فقط دستِ مالک ربات است.",
                                               reply_markup=main_menu())
    ctx.user_data.pop("mode",None)
    doc=update.message.document
    if not doc.file_name.endswith(".zip"):
        await update.message.reply_text("❌ فقط فایل ZIP قابل قبول است.",reply_markup=main_menu()); return
    await update.message.reply_text("⏳ در حال بازگردانی...")
    ok,result=await restore_backup(ctx.bot,doc.file_id)
    if ok: await update.message.reply_text(f"✅ بک‌آپ بازگردانی شد.\nفایل‌ها: {', '.join(result)}",reply_markup=main_menu())
    else: await update.message.reply_text(f"❌ خطا: {result}",reply_markup=main_menu())

# ════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════
def _spawn(coro,name):
    """تسک پس‌زمینه با گزارش مرگ.

    با ensure_future خالی، اگر تسکی استثنا بدهد پایتون فقط هنگام جمع‌آوری
    زباله یک هشدار می‌دهد و عملاً بی‌صدا می‌میرد — یعنی یک قابلیت تا
    ری‌استارت بعدی از کار می‌افتد و کسی نمی‌فهمد.
    """
    t=asyncio.ensure_future(coro)
    def _done(f):
        try: f.result()
        except asyncio.CancelledError: pass
        except Exception as e:
            logger.error(f"⛔ تسک پس‌زمینه‌ی «{name}» متوقف شد: {e}",exc_info=True)
    t.add_done_callback(_done)
    return t

async def post_init(app):
    await init_db(); await load_pages(); await load_topics(); await load_data(); await load_banners()
    await load_workhours(); await load_buttons(); await load_settings()
    await load_stats(); await load_menu(); await load_places(); await load_backup_registry()
    await load_admins(); await bc_load(); await load_faq(); await load_unmatched()
    _spawn(_spam_cleanup_loop(),"پاکسازی")
    _spawn(_stats_flush_loop(),"ذخیره‌ی آمار")
    _spawn(_auto_backup_loop(app.bot),"بکاپ هفتگی")
    _spawn(_bc_loop(app.bot),"پخش همگانی")
    _spawn(_pending_loop(app.bot),"پیام‌های بی‌جواب")
    global BOT_USERNAME
    try:
        me=await app.bot.get_me(); BOT_USERNAME=me.username or ""
    except Exception as e: logger.warning(f"get_me: {e}")
    try:
        await app.bot.set_my_commands([BotCommand("start","شروع و نمایش منو"),
                                       BotCommand("help","راهنما")])
        # چیزی که کاربر پیش از زدن Start می‌بیند
        if get_setting("assistant"):
            short=(f"🤖 دستیار هوشمند {SHOP_NAME} — قیمت، اقساط، گارانتی، معاوضه و آدرس؛ "
                   "فقط بپرسید")
            desc=(f"🤖 دستیار هوشمند {SHOP_NAME}\n\n"
                  "سؤالتان را مثل چت با یک آدم بنویسید؛ همان لحظه جواب می‌گیرید ⚡️\n\n"
                  "💬 «آیفون ۱۳ پرو قیمتش چنده؟»\n"
                  "💬 «قسطی با چک میشه خرید؟»\n"
                  "💬 «رجیستر شده دارید؟»\n"
                  "💬 «گوشیمو معاوضه می‌کنید؟»\n\n"
                  "قیمت روز، اقساط، گارانتی، ارسال به سراسر ایران، آدرس و ساعت کاری — "
                  "و هر جا لازم باشد، همکاران ما همین‌جا وارد گفتگو می‌شوند.\n\n"
                  "برای شروع «Start» را بزنید.")
        else:
            short=f"پشتیبانی {SHOP_NAME} — آدرس، ساعت کاری، شبکه‌های اجتماعی و پاسخ به سؤالات شما"
            desc=(f"به پشتیبانی {SHOP_NAME} خوش آمدید 👋\n\n"
                  "اینجا می‌توانید:\n"
                  "• آدرس فروشگاه و موقعیت روی نقشه را ببینید\n"
                  "• از ساعت کاری امروز باخبر شوید\n"
                  "• به سایت و شبکه‌های اجتماعی ما دسترسی داشته باشید\n"
                  "• شرایط خرید اقساطی را بخوانید\n"
                  "• سؤالتان را بپرسید و از همکاران ما پاسخ بگیرید\n\n"
                  "برای شروع دکمه‌ی «Start» را بزنید.")
        await app.bot.set_my_short_description(short[:120])
        await app.bot.set_my_description(desc[:512])
    except Exception as e: logger.warning(f"معرفی ربات: {e}")
    logger.info("✅ ربات راه‌اندازی شد")

async def on_error(update:object,ctx:ContextTypes.DEFAULT_TYPE):
    """هر خطای گرفته‌نشده — به ادمین گزارش می‌شود و کاربر بی‌پاسخ نمی‌ماند."""
    if isinstance(ctx.error,Conflict):
        logger.error("⛔ Conflict — یک نسخه دیگر از همین ربات هم‌زمان در حال اجراست. "
                     "با `systemctl status telegram-bot` و `pgrep -af bot.py` بررسی کنید "
                     "و نسخه اضافی را ببندید.")
        return
    logger.error("خطای گرفته‌نشده:",exc_info=ctx.error)
    # ۱) کاربر بی‌پاسخ نماند
    try:
        if isinstance(update,Update) and update.effective_message:
            await update.effective_message.reply_text(
                "❌ خطایی رخ داد. لطفاً دوباره تلاش کنید یا /start را بزنید.")
    except Exception: pass
    # ۲) ادمین خبردار شود (با محدودیت نرخ تا در خطای پیاپی اسپم نشود)
    global _last_err_report
    now=time.time()
    if now-_last_err_report < _ERR_REPORT_GAP: return
    _last_err_report=now
    try:
        tb="".join(traceback.format_exception(type(ctx.error),ctx.error,ctx.error.__traceback__))[-1200:]
        who=""
        if isinstance(update,Update) and update.effective_user:
            u=update.effective_user; who=f"\n👤 {u.first_name or'—'} | 🆔 {u.id}"
        await ctx.bot.send_message(OWNER_ID,f"⚠️ خطای ربات{who}\n\n<pre>{html.escape(tb)}</pre>",
                                   parse_mode="HTML")
    except Exception as e: logger.error(f"گزارش خطا به ادمین نرسید: {e}")

async def post_shutdown(app):
    """قبل از خاموش‌شدن — flush داده‌ها و بستن دیتابیس.

    بستن db حیاتی است: aiosqlite یک رشته‌ی non-daemon می‌سازد، پس اگر اتصال
    باز بماند پروسه هرگز خارج نمی‌شود. systemd آن‌وقت تا TimeoutStopSec صبر
    می‌کند (پیش‌فرض ۹۰ ثانیه) و سرویس در حالت deactivating گیر می‌کند؛ در همان
    فاصله نسخه‌ی جدید با نسخه‌ی قدیمی روی getUpdates تداخل (Conflict) پیدا
    می‌کند و ربات عملاً از کار می‌افتد.
    """
    global db,_bc_task
    if _stats_dirty:   await save_stats();   logger.info("shutdown: stats saved")
    # پخش نیمه‌تمام: تسک را ببند و شماره‌ی آخرین نفر را ذخیره کن تا اجرای
    # بعدی دقیقاً از نفر بعدی ادامه دهد (نه از اول، نه با پیام تکراری).
    if _bc_task is not None and not _bc_task.done():
        _bc_task.cancel()
        try: await _bc_task
        except Exception: pass
    if _bc_job is not None:
        await bc_save(); logger.info(f"shutdown: پخش در {_bc_job['i']}/{len(_bc_job['queue'])} ذخیره شد")
    if db is not None:
        try:
            await db.close(); db=None
            logger.info("shutdown: دیتابیس بسته شد")
        except Exception as e: logger.error(f"بستن دیتابیس هنگام خاموشی: {e}")
    logger.info("✅ shutdown clean")

def main():
    app=(ApplicationBuilder().token(TOKEN)
         .post_init(post_init).post_shutdown(post_shutdown)
         # پیش‌فرض PTB آپدیت‌ها را «یکی‌یکی» پردازش می‌کند: اگر ارسال عکس یک
         # کاربر یک ثانیه طول بکشد، بقیه‌ی کاربران پشتش صف می‌کشند. با موازی
         # کردن، هر کاربر مستقل از بقیه پاسخ می‌گیرد.
         .concurrent_updates(32)
         # استخر اتصال بزرگ‌تر تا ارسال‌های هم‌زمان پشت هم قفل نشوند
         .connection_pool_size(64).pool_timeout(20.0)
         .connect_timeout(10.0).read_timeout(20.0).write_timeout(20.0)
         .get_updates_read_timeout(35.0)
         .build())
    # گروه ۱- : ریپلای مدیر روی پیام مشتری زودتر از هر هندلر دیگری دیده می‌شود.
    # اگر واقعاً پاسخ بود، ApplicationHandlerStop جلوی پردازش دوباره را می‌گیرد؛
    # وگرنه پیام مسیر عادی خودش را ادامه می‌دهد.
    app.add_handler(MessageHandler(filters.REPLY & ~filters.COMMAND,reply_relay),group=-1)
    app.add_handler(CommandHandler("start",cmd_start))
    app.add_handler(CommandHandler("help",cmd_help))
    app.add_handler(CommandHandler("admin",cmd_admin))
    app.add_handler(CommandHandler("ask",cmd_ask))
    app.add_handler(CommandHandler("test",cmd_test))
    app.add_handler(CommandHandler("badword",cmd_badword))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND,photo_handler))
    app.add_handler(MessageHandler(filters.Document.ZIP & ~filters.COMMAND,document_handler))
    app.add_handler(MessageHandler(filters.LOCATION | filters.VENUE,location_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,text_handler))
    # هر چیز دیگری که مشتری بفرستد — ویس، ویدیو، فایل، مخاطب، استیکر.
    # بدون این، پیام مشتری بی‌صدا دور ریخته می‌شد.
    app.add_handler(MessageHandler(
        (filters.VOICE | filters.VIDEO | filters.VIDEO_NOTE | filters.AUDIO
         | filters.Document.ALL | filters.CONTACT | filters.Sticker.ALL) & ~filters.COMMAND,
        user_media_handler))
    app.add_error_handler(on_error)
    print("🚀 ربات در حال اجراست...")
    app.run_polling(drop_pending_updates=True, poll_interval=0.0, timeout=30)

if __name__=="__main__":
    main()