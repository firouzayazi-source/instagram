"""مغز دستیار استوک لند — فهم پیام مشتری بدون هیچ API یا مدل بیرونی.

این ماژول هیچ وابستگی به تلگرام ندارد: متن می‌گیرد و می‌گوید مشتری چه
می‌خواهد. تصمیم اینکه بعدش چه پیامی برود با bot.py است.

چرا موتور داخلی و نه مدل زبانی: سؤال‌های یک فروشگاه موبایل محدود است
(قیمت، اقساط، آدرس، ساعت، گارانتی، ...). برای چنین دامنه‌ای، فهمِ دقیقِ
همین چند موضوع + حرف‌زدن طبیعی، از مدلی که «همه‌چیز» را نیمه‌درست
می‌فهمد مطمئن‌تر است. این موتور هیچ‌وقت چیزی از خودش نمی‌سازد: یا یکی از
نیت‌هایی را که ادمین تعریف کرده تشخیص می‌دهد، یا صادقانه می‌گوید نفهمید.

مراحل فهم یک پیام:
  ۱. نرمال‌سازی   — ي/ك عربی، ارقام، نیم‌فاصله، علائم
  ۲. حرف‌های روزمره — سلام، مرسی، خداحافظ، خوبی، آره/نه، «رباتی؟»
  ۳. توکن‌ها       — هر کلمه + ریشه‌اش (بدون پسوند) + هم‌معنی‌اش
  ۴. امتیاز نیت‌ها  — کلیدواژه‌ها (با تحمل غلط تایپی) و جمله‌های نمونه
  ۵. مدل محصول     — «آیفون ۱۳ پرو» برای اینکه جواب شخصی‌تر شود
  ۶. ادامه‌ی بحث    — «قسطیش چی؟»، «واسه ۱۴ چی؟» بعد از سؤال قبلی
"""
import re
import random
import difflib

# ════════════════════════════════════════════════
#  نرمال‌سازی
# ════════════════════════════════════════════════
_AR_FIX = str.maketrans("يكةۀأإؤ", "یکههااو")
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_PUNCT = re.compile(r"[‌‏‎‍?؟!.,،؛;:\-_()\[\]{}\"'«»/\\*+=#@~`|<>^&%$]+")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️]+")
_REPEAT = re.compile(r"(.)\1{2,}")          # «سلاااام» → «سلام»


def norm(text):
    """متنِ قابل مقایسه: حروف یکدست، ارقام لاتین، بدون علائم و ایموجی."""
    t = (text or "").translate(_AR_FIX).translate(_DIGITS).lower()
    t = t.replace("آ", "ا")                  # «آدرس» و «ادرس» یکی‌اند
    t = _EMOJI.sub(" ", t)
    t = _PUNCT.sub(" ", t)
    t = _REPEAT.sub(r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


# ════════════════════════════════════════════════
#  ریشه و هم‌معنی‌ها
# ════════════════════════════════════════════════
# پسوندهای رایج محاوره — بلندترها اول تا «هاشون» قبل از «ها» بیفتد
_SUFFIXES = ("هاشون", "هاشان", "هاتون", "هاتان", "هایی", "های", "ها",
             "تون", "تان", "شون", "شان", "مون", "مان",
             "یید", "اید", "ید", "یم", "ین",
             "یی", "ای", "ی", "ش", "م", "ت", "ه")
_PREFIXES = ("نمی", "می", "ن", "ب")

# هم‌معنی‌ها: هر شکل → یک شکل مرجع. شکل مرجع همانی است که در
# کلیدواژه‌ها می‌آید، پس «اقساطی»، «قسطی» و «چکی» همه به «قسط» می‌رسند.
SYNONYMS = {
    # اقساط
    "اقساط": "قسط", "قسطی": "قسط", "اقساطی": "قسط", "قسط": "قسط",
    "چکی": "چک", "طلایی": "طلا",
    # گارانتی
    "ضمانت": "گارانتی", "وارانتی": "گارانتی", "ضمانتنامه": "گارانتی",
    "گارانتي": "گارانتی", "garanti": "گارانتی", "warranty": "گارانتی",
    # آدرس
    "نشانی": "ادرس", "نشونی": "ادرس", "لوکیشن": "ادرس", "لوکیشین": "ادرس",
    "location": "ادرس", "لوکیشنتون": "ادرس", "ادرستون": "ادرس",
    "کجایید": "کجا", "کجاست": "کجا", "کجاس": "کجا", "کجان": "کجا", "کجایین": "کجا",
    # قیمت
    "قیمتش": "قیمت", "قیمتا": "قیمت", "قیمتها": "قیمت", "نرخ": "قیمت",
    "price": "قیمت", "چقد": "چقدر", "چقدره": "چقدر",
    # موجودی
    "موجوده": "موجودی", "موجود": "موجودی", "موجودیه": "موجودی",
    # ساعت/باز
    "بازید": "باز", "بازه": "باز", "بازین": "باز", "بستید": "بسته", "بستین": "بسته",
    "تعطیلید": "تعطیل", "تعطیلین": "تعطیل", "تعطیله": "تعطیل",
    # محصولات
    "ایفون": "ایفون", "iphone": "ایفون", "ای فون": "ایفون",
    "ایپد": "ایپد", "ipad": "ایپد", "مکبوک": "مکبوک", "macbook": "مکبوک",
    "ایرپاد": "ایرپاد", "airpods": "ایرپاد", "airpod": "ایرپاد",
    "سامسونگ": "سامسونگ", "samsung": "سامسونگ", "شیائومی": "شیائومی", "xiaomi": "شیائومی",
    # سایت / اینستا
    "وبسایت": "سایت", "website": "سایت", "site": "سایت",
    "اینستا": "اینستاگرام", "instagram": "اینستاگرام", "insta": "اینستاگرام", "پیج": "اینستاگرام",
    # ارسال
    "پست": "ارسال", "پیک": "ارسال", "تیپاکس": "ارسال",
    # تعویض / خرید کارکرده
    "معاوضه": "تعویض", "عوض": "تعویض", "کارکرده": "کارکرده", "دسته دوم": "کارکرده",
    # رجیستری
    "رجیستری": "رجیستر", "ریجستر": "رجیستر", "رجستر": "رجیستر", "رجیستره": "رجیستر",
    "رجیسترشده": "رجیستر", "register": "رجیستر",
    # مرجوعی / پرداخت / نرم‌افزار
    "مرجوعی": "مرجوع", "پوز": "کارتخوان", "کارتخون": "کارتخوان",
    "اپلایدی": "اپلایدی", "ایکلاد": "ایکلود", "آیکلود": "ایکلود",
    # برندهای غیر اپل
    "اندرویدی": "اندروید", "گلکسی": "سامسونگ", "galaxy": "سامسونگ", "redmi": "شیائومی",
    "ردمی": "شیائومی",
    # تخفیف
    "اف": "تخفیف", "حراج": "تخفیف", "off": "تخفیف", "تخفیفی": "تخفیف",
    # آدم
    "اپراتور": "همکار", "فروشنده": "همکار", "مشاور": "همکار", "پشتیبان": "همکار",
    "کارشناس": "همکار", "ادمین": "همکار",
}

# کلمه‌هایی که در مقایسه‌ی «جمله‌ی نمونه» معنی‌دار نیستند
STOPWORDS = {
    "سلام", "من", "یه", "یک", "را", "رو", "که", "و", "به", "از", "با", "در", "تو",
    "این", "اون", "ان", "هم", "برای", "واسه", "چی", "چه", "ایا", "میشه", "شه",
    "می", "است", "هست", "ها", "ای", "لطفا", "ممنون", "شما", "خیلی", "یعنی",
    "اگه", "اگر", "باید", "بود", "شد", "کنم", "کنید", "دارم", "داره", "دارید",
    "اقا", "خانم", "جان", "عزیز", "ببخشید", "خسته", "نباشید",
}


def stem(tok):
    """ریشه‌ی ساده‌ی محاوره: پیشوند «می/نمی» و پسوندهای رایج کنده می‌شوند.
    عمداً محافظه‌کار است: پیشوندِ تک‌حرفی («ب»، «ن») فقط از کلمه‌ی بلند
    کنده می‌شود، وگرنه «بسته» و «نقشه» خراب می‌شوند."""
    t = tok
    for p in _PREFIXES:
        if t.startswith(p) and len(t) - len(p) >= (3 if len(p) > 1 else 4):
            t = t[len(p):]
            break
    for s in _SUFFIXES:
        if t.endswith(s) and len(t) - len(s) >= 2:
            return t[:-len(s)]
    return t


def expand(tok):
    """همه‌ی شکل‌های یک کلمه که با کلیدواژه مقایسه می‌شوند.

    ریشه‌ی کوتاه‌تر از ۳ حرف کنار گذاشته می‌شود: «بخرم» و «میخرید» هر دو
    به «خر» می‌رسند و این ریشه آن‌قدر کلی است که دو موضوع بی‌ربط را یکی
    می‌کند. خودِ کلمه‌ی کوتاه («چک») همچنان دقیق تطبیق می‌خورد."""
    out = {tok}
    s = stem(tok)
    if len(s) >= 3:
        out.add(s)
    for f in (tok, s):
        if f in SYNONYMS:
            out.add(SYNONYMS[f])
    return out


def tokens(text):
    return [t for t in norm(text).split() if t]


def token_forms(text):
    """هر توکن پیام → [(شکل, کیفیت)]."""
    return [_msg_forms(t) for t in tokens(text)]


# ════════════════════════════════════════════════
#  حرف‌های روزمره
# ════════════════════════════════════════════════
_GREET = re.compile(
    r"^(سلام(?:م|ت)?(?: علیکم| عرض شد| وقت(?:تون)? بخیر)?|درود|"
    r"(?:وقت|صبح|ظهر|عصر|شب)(?:تون)? ?بخیر|hi|hello|hey|هلو|های)\b ?")
_TIRED = re.compile(r"^(خسته نباشید|خسته نباشی|خدا قوت)\b ?")
_THANKS = re.compile(r"\b(مرسی|ممنون(?:م)?|سپاس(?:گزارم)?|متشکر(?:م)?|تشکر|مچکرم|"
                     r"دمت(?:ون)? گرم|دست(?:تون)? درد نکنه|thanks|thank you|thx|merci)\b")
_BYE = re.compile(r"\b(خداحافظ|خدافظ|خداحافظی|خدانگهدار|خدانگه دار|فعلا|بای|bye|روز خوش|شب خوش)\b")
_HOW = re.compile(r"\b(خوبی|خوبین|خوبید|خوب هستید|چطوری|چطورین|حالت(?:ون)? خوبه|"
                  r"حالتون چطوره|چه خبر)\b")
_WHO = re.compile(r"\b(رباتی|ربات هستی|ربات هستین|ادمی|ادم هستی|انسانی|"
                  r"کی هستی|تو کی هستی|شما کی هستین|هوش مصنوعی|ماشینی)\b")
_YES = re.compile(r"^(اره|ارع|بله|بلی|اوکی|ok|okay|باشه|حتما|لطفا|اری|yes|"
                  r"بفرست(?:ید|ین)?|اره لطفا|بله لطفا|اره بفرست|اوکی بفرست)$")
_NO = re.compile(r"^(نه|نخیر|خیر|نمیخوام|نه ممنون|نه مرسی|no|لازم نیست)$")
_LAUGH = re.compile(r"^(خخ+|هه+|ههه+|lol|😂+)$")


def smalltalk(text):
    """حرف‌های روزمره را جدا می‌کند و باقی پیام را برمی‌گرداند.

    خروجی: (مجموعه‌ی برچسب‌ها, باقیِ متن)
    «سلام خسته نباشید قیمت آیفون؟» → ({"greet","tired"}, "قیمت ایفون")
    """
    t = norm(text)
    tags = set()
    for _ in range(3):                       # «سلام وقت بخیر خسته نباشید»
        m = _GREET.match(t)
        if m:
            tags.add("greet"); t = t[m.end():].strip(); continue
        m = _TIRED.match(t)
        if m:
            tags.add("tired"); t = t[m.end():].strip(); continue
        break
    if _YES.match(t):
        return tags | {"yes"}, ""
    if _NO.match(t):
        return tags | {"no"}, ""
    if _LAUGH.match(t):
        return tags | {"laugh"}, ""
    for rx, tag in ((_THANKS, "thanks"), (_BYE, "bye"), (_HOW, "how"), (_WHO, "who")):
        if rx.search(t):
            tags.add(tag)
            t = rx.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # اگر از پیام فقط پرکننده مانده («ممنون از شما»)، چیزی برای فهمیدن نیست
    if t and all(w in STOPWORDS for w in t.split()):
        t = ""
    return tags, t


# ════════════════════════════════════════════════
#  مدل محصول
# ════════════════════════════════════════════════
_BRANDS = {
    "ایفون": "آیفون", "iphone": "آیفون", "ایپد": "آیپد", "ipad": "آیپد",
    "مکبوک": "مک‌بوک", "مک بوک": "مک‌بوک", "macbook": "مک‌بوک",
    "اپل واچ": "اپل‌واچ", "apple watch": "اپل‌واچ", "واچ": "اپل‌واچ",
    "ایرپاد": "ایرپاد", "airpods": "ایرپاد", "airpod": "ایرپاد",
    "سامسونگ": "سامسونگ", "samsung": "سامسونگ", "گلکسی": "گلکسی", "galaxy": "گلکسی",
    "شیائومی": "شیائومی", "xiaomi": "شیائومی", "پوکو": "پوکو", "poco": "پوکو",
}
_VARIANTS = {"پرو مکس": "پرو مکس", "pro max": "پرو مکس", "پرومکس": "پرو مکس",
             "پرو مکسش": "پرو مکس", "پرومکسش": "پرو مکس", "پروش": "پرو",
             "پرو": "پرو", "pro": "پرو", "پلاس": "پلاس", "plus": "پلاس",
             "مینی": "مینی", "mini": "مینی", "اولترا": "اولترا", "ultra": "اولترا",
             "ایر": "ایر", "air": "ایر"}
_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

_brand_rx = "|".join(sorted(map(re.escape, _BRANDS), key=len, reverse=True))
_var_rx = "|".join(sorted(map(re.escape, _VARIANTS), key=len, reverse=True))
_PRODUCT = re.compile(rf"(?:\b({_brand_rx}))?\s*\b(\d{{1,2}})?\s*(?:\b({_var_rx})\b)?")


def product(text):
    """«قیمت ایفون ۱۳ پرو مکس؟» → «آیفون ۱۳ پرو مکس». اگر چیزی نبود: "".

    فقط برند، یا برند+عدد، یا عدد+مدل («۱۴ پرو») قبول است — عدد تنها
    («۲ تا»، «۱۸ ماه») محصول حساب نمی‌شود."""
    t = norm(text)
    best = ""
    for m in _PRODUCT.finditer(t):
        brand, num, var = m.group(1), m.group(2), m.group(3)
        if not brand and not (num and var):
            continue
        parts = []
        if brand: parts.append(_BRANDS[brand])
        if num: parts.append(num.translate(_FA))
        if var: parts.append(_VARIANTS[var])
        cand = " ".join(parts)
        if len(cand) > len(best):
            best = cand
    return best


def carry_product(text, prev=""):
    """محصولِ پیام، با تکیه بر محصولِ قبلیِ گفت‌وگو.

    بعد از «آیفون ۱۳ چنده؟»، «واسه ۱۴ چی؟» یعنی «آیفون ۱۴» و «پرو مکسش؟»
    یعنی همان مدل با نوع دیگر — آدم‌ها هم همین‌طور حرف می‌زنند."""
    cur = product(text)
    brands = set(_BRANDS.values())
    pw = (prev or "").split()
    brand = pw[0] if pw and pw[0] in brands else ""
    if not brand:
        return cur
    if cur:
        return cur if cur.split()[0] in brands else f"{brand} {cur}"
    # عددِ تنها فقط وقتی مدل است که جمله کوتاه و پرسشِ ادامه باشد و بعدش
    # واحد نیاید («۲ تا»، «۱۸ ماه»، «۳ میلیون» مدل نیستند)
    toks = tokens(text)
    if len(toks) > 5 or not any(t in _FOLLOW or stem(t) in _FOLLOW for t in toks):
        return ""
    m = re.search(r"\b(\d{1,2})\b(?!\s*(?:تا|ماه|روز|سال|میلیون|میلیونی|تومن|تومان|هزار|قسط))",
                  norm(text))
    if m:
        return f"{brand} {m.group(1).translate(_FA)}"
    return ""


# ════════════════════════════════════════════════
#  تشخیص نیت
# ════════════════════════════════════════════════
FUZZY_MIN = 0.82      # شباهت لازم برای «گارانتئ» ≈ «گارانتی»
MATCH_MIN = 0.5       # کمترین امتیاز برای اینکه بگوییم «فهمیدم»

# کلمه‌های کلی: تنها که بیایند معنی دارند («کجایید؟» یعنی آدرس،
# «آیفون ۱۳ چقدره؟» یعنی قیمت)، ولی کنار هر کلمه‌ی معنی‌دار — حتی با
# غلط تایپی — می‌بازند: «معاوضه هم دارید» درباره‌ی معاوضه است، و
# «ضمانتش چقدره» درباره‌ی گارانتی. کلمه‌ی کلی فقط به شکل دقیق قبول است،
# وگرنه «بازی فوتبال» از ریشه‌ی «باز» سؤال ساعت کاری فهمیده می‌شد.
WEAK = {"دارید", "داری", "دارین", "هست", "کجا", "باز", "کی", "میفرستید", "میفرستین",
        "چقدر", "چنده", "چقد"}
WEAK_SCORE = 0.5
# کلمه‌هایی که «توضیح» نمی‌خواهند: اگر پیام فقط با یک کلمه‌ی ضعیف («دارید»)
# جور شده و کلمه‌ی معنادارِ بی‌جوابی دارد («تعمیرات دارید؟»)، آن تطبیق
# پذیرفته نمی‌شود — وگرنه «تعمیرات دارید» جوابِ موجودی می‌گرفت.
GENERIC = {"مدل", "مدلش", "مدلا", "گوشی", "گوشیا", "گوشیاتون", "گوشیتون", "گوشیم", "دستگاه",
           "الان", "امروز", "فعلا", "الان", "ایفون", "اپل", "محصول", "جنس", "رنگ", "نو",
           "اصل", "اوکی", "اینجا", "اونجا", "مغازتون", "مغازه", "فروشگاه", "شما", "شمام",
           "میخواستم", "میخوام", "بپرسم", "سوال", "داشتم", "یعنی", "بازم", "دوباره",
           "شده", "شد", "کرده", "کردم", "کنه", "کنم", "داره", "دارم", "بود", "باشه", "هستن",
           "هستید", "هستین", "هستی",
           "صفحه", "صفحش", "صفحهش", "گوشیمو", "گوشیم", "خیلی", "چیزی", "یکی", "همه"}
# کلمه‌های مدل — در «جمله‌ی نمونه» شمرده نمی‌شوند، وگرنه نمونه‌ی «۱۶ پرو مکس
# چند اینچه» هر «… پرو مکس چند»ی را سؤال مشخصات می‌فهمید
_MODEL_WORDS = {"پرو", "مکس", "پلاس", "مینی", "ایر", "اولترا", "pro", "max", "plus", "mini"}


def _ex_words(text):
    return {stem(t) for t in tokens(text)
            if t not in STOPWORDS and t not in _MODEL_WORDS and not t.isdigit()}
EXAMPLE_MIN = 0.6     # چه سهمی از کلمه‌های یک جمله‌ی نمونه باید در پیام باشد


# کیفیت یک تطبیق: کلمه‌ی دقیق یا مترادفِ تعریف‌شده قطعی است؛ ریشه‌یابی
# و غلط‌گیری حدس‌اند و کمی کمتر وزن می‌گیرند، تا در تساوی ببازند.
Q_EXACT, Q_STEM, Q_FUZZY = 1.0, 0.96, 0.93


def _key_forms(key):
    """کلیدواژه → شکل‌های هر کلمه‌اش. عمداً ریشه‌یابی نمی‌شود: کلیدواژه
    همان است که مدیر نوشته. اگر «چنده» ریشه‌یابی شود به «چند» می‌رسد و
    «چند سال گارانتی» را سؤال قیمت می‌فهمد؛ «بفروشم» به «فروش» می‌رسد
    و «قسطی می‌فروشید؟» را سؤال معاوضه."""
    out = []
    for t in norm(key).split():
        f = {t}
        if t in SYNONYMS: f.add(SYNONYMS[t])
        out.append(f)
    return out


def _msg_forms(tok):
    """یک کلمه‌ی پیام → [(شکل, کیفیت)]."""
    out = [(tok, Q_EXACT)]
    if tok in SYNONYMS: out.append((SYNONYMS[tok], Q_EXACT))
    s = stem(tok)
    if len(s) >= 3 and s != tok:
        out.append((s, Q_STEM))
        if s in SYNONYMS: out.append((SYNONYMS[s], Q_STEM))
    return out


def _tok_hit(kforms, msg):
    """بهترین کیفیتِ تطبیقِ یک کلمه‌ی کلیدواژه در پیام (۰ یعنی نیست)."""
    best = 0.0
    for forms in msg:
        for w, q in forms:
            if w in kforms and q > best:
                best = q
    if best:
        return best
    for kf in kforms:
        if len(kf) < 4:
            continue
        for forms in msg:
            for w, _ in forms:
                if len(w) >= 4 and difflib.SequenceMatcher(None, kf, w).ratio() >= FUZZY_MIN:
                    return Q_FUZZY
    return 0.0


def score_intent(item, msg_forms, msg_content):
    """امتیاز یک نیت برای یک پیام، و طولِ بلندترین کلیدواژه‌ای که خورد."""
    score = 0.0
    longest = 0
    for key in item.get("keys") or []:
        kf = _key_forms(key)
        if not kf:
            continue
        hits = [_tok_hit(f, msg_forms) for f in kf]
        if all(hits):
            words = norm(key).split()
            if all(w in WEAK for w in words):
                if min(hits) < Q_EXACT:
                    continue
                s = WEAK_SCORE
            else:
                # کلیدواژه‌ی چندکلمه‌ای دقیق‌تر است و وزن بیشتری می‌گیرد
                s = (1.0 + 0.5 * (len(kf) - 1)) * min(hits)
            if s > score or (s == score and len(norm(key)) > longest):
                score, longest = s, len(norm(key))
    for ex in item.get("examples") or []:
        ex_content = _ex_words(ex)
        if len(ex_content) < 2:
            continue
        cover = len(ex_content & msg_content) / len(ex_content)
        if cover >= EXAMPLE_MIN:
            score = max(score, 1.0 + cover)
            longest = max(longest, len(norm(ex)))
    return score, longest


def match(text, intents):
    """بهترین نیت برای این متن، یا None اگر مطمئن نیستیم.

    خروجی: (نیت, امتیاز). در تساوی، نیتی که کلیدواژه‌ی بلندتری خورده
    برنده است — «گارانتی طلایی» بر «گارانتی» می‌چربد."""
    msg_forms = token_forms(text)
    if not msg_forms:
        return None, 0.0
    msg_content = set()
    for t in tokens(text):
        if t not in STOPWORDS:
            msg_content |= {stem(t), t}
            if t in SYNONYMS: msg_content.add(SYNONYMS[t])
    best, best_score, best_len = None, 0.0, 0
    for it in intents:
        if not it.get("enabled", True):
            continue
        s, ln = score_intent(it, msg_forms, msg_content)
        if s >= MATCH_MIN and (s > best_score or (s == best_score and ln > best_len)):
            best, best_score, best_len = it, s, ln
    if best is not None and best_score <= WEAK_SCORE and _only_have(text) and _unexplained(text):
        return None, 0.0
    return best, best_score


_HAVE = {"دارید", "داری", "دارین", "هست"}


def _only_have(text):
    """تنها کلمه‌ی ضعیفِ پیام از جنس «دارید/هست» است — نه «کجا»، «باز»،
    «چقدر» که خودشان جهت سؤال را روشن می‌کنند."""
    ws = set()
    for t in tokens(text):
        for f in (t, SYNONYMS.get(t, ""), stem(t)):
            if f in WEAK: ws.add(f)
    return bool(ws) and ws <= _HAVE


def _unexplained(text):
    """کلمه‌های معنادارِ پیام که نه ضعیف‌اند، نه عمومی، نه اسم محصول."""
    prod = set(norm(product(text)).split()) if product(text) else set()
    out = []
    for t in tokens(text):
        if (t in STOPWORDS or t in WEAK or t in GENERIC or t.isdigit() or t in _BRANDS
                or t in _VARIANTS or t in prod or len(t) < 3):
            continue
        if any(w in WEAK for w in (stem(t), SYNONYMS.get(t, ""))):
            continue
        out.append(t)
    return out


# ════════════════════════════════════════════════
#  ادامه‌ی بحث
# ════════════════════════════════════════════════
_FOLLOW = {"چی", "چطور", "چطوره", "چطوریه", "اون", "این", "همین", "همون", "پس",
           "اونم", "اینم", "اینو", "اونو", "چند", "چنده", "ش", "شو"}


def is_followup(text):
    """«واسه ۱۴ چی؟»، «اونم داره؟» — پیام کوتاهی که به سؤال قبلی تکیه دارد."""
    toks = tokens(text)
    if not toks or len(toks) > 6:
        return False
    if product(text):
        return True
    return any(t in _FOLLOW or stem(t) in _FOLLOW for t in toks)


# ════════════════════════════════════════════════
#  جواب‌های چندشکلی و جای‌گذاری
# ════════════════════════════════════════════════
VARIANT_SEP = re.compile(r"\n\s*-{3,}\s*\n")


def pick_variant(answer, rnd=random, product=None):
    """پاسخ می‌تواند چند شکل داشته باشد که با خط «---» جدا شده‌اند؛
    هر بار یکی انتخاب می‌شود تا ربات تکراری و ماشینی به نظر نیاید.

    اگر product داده شود: وقتی مشتری اسم مدل را گفته، شکلی که {product}
    دارد ترجیح دارد («قیمت روز آیفون ۱۳»)، و وقتی نگفته، شکلی که ندارد —
    تا جای خالی در جمله نماند."""
    parts = [p.strip() for p in VARIANT_SEP.split(answer or "") if p.strip()]
    if product is not None:
        want = [p for p in parts if ("{product}" in p) == bool(product)]
        parts = want or parts
    return rnd.choice(parts) if parts else ""


_PLACEHOLDER = re.compile(r"\{(name|product|shop|status|hours)\}")


def fill(text, **values):
    """{name} {product} {shop} {status} {hours} → مقدارشان.
    جای‌نگهدارِ بی‌مقدار پاک می‌شود، نه اینکه خام به مشتری برسد."""
    def rep(m):
        return values.get(m.group(1)) or ""
    out = _PLACEHOLDER.sub(rep, text or "")
    out = re.sub(r"[ \t]{2,}", " ", out)
    return re.sub(r" ([،.!؟])", r"\1", out).strip()


# ════════════════════════════════════════════════
#  جمله‌های روزمره
# ════════════════════════════════════════════════
def daypart(hour):
    if 5 <= hour < 12: return "صبحتون بخیر ☀️"
    if 12 <= hour < 17: return "روزتون بخیر 🌤"
    if 17 <= hour < 21: return "عصرتون بخیر 🌇"
    return "شبتون بخیر 🌙"


_SAID_PART = (("صبح", "صبحتون بخیر ☀️"), ("ظهر", "ظهرتون بخیر 🌤"), ("عصر", "عصرتون بخیر 🌇"),
              ("شب", "شبتون بخیر 🌙"), ("روز", "روزتون بخیر 🌤"))


def greet_line(name, hour, rnd=random, text=""):
    """سلامِ جواب. اگر مشتری خودش گفته «عصر بخیر»، همان را جواب می‌دهیم —
    ساعت سرور یا اختلاف ساعت نباید «صبح بخیر» در جواب «شب بخیر» بگذارد."""
    who = f" {name} جان" if name else ""
    t = norm(text)
    part = next((p for w, p in _SAID_PART if re.search(rf"\b{w}(?:تون)? ?بخیر", t)), None)
    part = part or daypart(hour)
    return rnd.choice([f"سلام{who} 👋 {part}",
                       f"سلام{who}، {part}",
                       f"درود{who} 🌸 {part}"])


SMALLTALK_REPLIES = {
    "greet_only": ["چطور می‌تونم کمکتون کنم؟ سؤالتون رو بنویسید یا از منو انتخاب کنید 👇",
                   "در خدمتم 🙂 هر سؤالی دارید بپرسید، یا از منو انتخاب کنید 👇",
                   "خوش اومدید 🙂 بفرمایید، چه کمکی از دستم برمیاد؟"],
    "tired": ["سلامت باشید 🙏", "ممنون، شما هم خسته نباشید 🌸"],
    "how": ["ممنون، خوبم 🙂 شما خوبید؟ بفرمایید، در خدمتم.",
            "مرسی که پرسیدید 🌸 بفرمایید، چه کمکی می‌تونم بکنم؟"],
    "thanks": ["خواهش می‌کنم 🌸 هر سؤال دیگه‌ای داشتید در خدمتم.",
               "قربان شما 🙏 اگه سؤال دیگه‌ای بود بپرسید.",
               "خواهش می‌کنم، خوشحال شدم کمک کنم 🙂"],
    "bye": ["خدانگهدار 👋 هر وقت سؤالی داشتید همین‌جا هستم.",
            "به امید دیدار 🌸 منتظرتون هستیم."],
    "laugh": ["😄", "🙂"],
    "no": ["باشه 🙂 هر سؤال دیگه‌ای داشتید بپرسید."],
    "yes_nothing": ["بفرمایید 🙂 چه کمکی از دستم برمیاد؟"],
}


def who_reply(shop):
    """صادقانه: دستیار است، نه آدم. و آدم هم در دسترس است."""
    return (f"من دستیار {shop} هستم 🤖\n"
            "سؤال‌های رایج رو همین‌جا جواب می‌دم، و هر وقت لازم باشه همکارهای "
            "ما خودشون جوابتون رو می‌دن. اگه بخواید همین الان با همکار صحبت کنید، "
            "بنویسید «همکار» یا دکمه‌ی زیر رو بزنید.")


def say(kind, rnd=random):
    return rnd.choice(SMALLTALK_REPLIES[kind])


UNKNOWN_LEADS = ["این یکی رو باید از همکارم بپرسم 🙏",
                 "سؤال خوبیه؛ بذارید از همکارم بپرسم 🙏",
                 "برای اینکه جواب دقیق بگیرید، پیامتون رو به همکارم دادم 🙏"]


# «آیفون ۱۲ چند؟» — اسم محصول + کلمه‌ی پرسش از مبلغ = سؤال قیمت، حتی
# اگر کلمه‌ی «قیمت» در جمله نباشد. در فروشگاه موبایل این تقریباً همیشه
# درست است و جواب (لیست قیمت روز) هیچ ادعای نادرستی نمی‌کند.
PRICE_HINTS = {"چند", "چنده", "چقدر", "چقد", "چقدره", "میدید", "میدین", "میفروشید"}
PRICE_KEY = "قیمت"


def price_intent(intents):
    for it in intents:
        if it.get("enabled", True) and any(norm(k) == PRICE_KEY for k in it.get("keys") or []):
            return it
    return None


def analyze(text, intents):
    """یک‌جا: حرف روزمره، نیت، محصول، و اینکه پیام ادامه‌ی بحث است یا نه."""
    tags, rest = smalltalk(text)
    intent, sc = (match(rest, intents) if rest else (None, 0.0))
    prod = product(text)
    if intent is None and prod and any(t in PRICE_HINTS for t in tokens(rest)):
        intent, sc = price_intent(intents), MATCH_MIN
    return {
        "tags": tags,
        "rest": rest,
        "intent": intent,
        "score": sc,
        "product": prod,
        "followup": bool(rest) and intent is None and is_followup(rest),
    }


# ════════════════════════════════════════════════
#  چند سؤال در یک پیام
# ════════════════════════════════════════════════
# «قیمت ۱۳ پرو چنده؟ قسطی هم میدید؟ کجایید؟» — پیام به بندها شکسته می‌شود و
# هر بند جدا فهمیده می‌شود. شکستن روی متنِ خام است (علامت‌ها هنوز هستند).
_CLAUSE_SPLIT = re.compile(
    r"[?؟!\n.،,؛;]+|\s+(?:و|ضمنا|ضمناً|همچنین|بعدشم|بعدم|راستی|یه سوال دیگه|یک سوال دیگه)\s+")
MULTI_MAX = 3


def clauses(text):
    return [c.strip() for c in _CLAUSE_SPLIT.split(text or "") if c and c.strip()]


def match_all(text, intents):
    """نیت‌های جدا در بندهای پیام، به ترتیب آمدن (حداکثر سه‌تا).
    [(نیت, امتیاز, بند)] — اگر کمتر از دو نیتِ متفاوت باشد، خالی."""
    prod = product(text)
    found, seen = [], set()
    for c in clauses(text):
        _, rest = smalltalk(c)
        if not rest:
            continue
        it, sc = match(rest, intents)
        if it is None and (prod or product(c)) and any(t in PRICE_HINTS for t in tokens(rest)):
            it, sc = price_intent(intents), MATCH_MIN
        if it is not None and it.get("id") not in seen:
            seen.add(it.get("id"))
            found.append((it, sc, c))
    return found[:MULTI_MAX] if len(found) >= 2 else []


# ════════════════════════════════════════════════
#  «منظورتون این بود؟» — نامزدهای نزدیک
# ════════════════════════════════════════════════
NEAR_MIN = 0.6
NEAR_FUZZY = 0.72      # کمتر از FUZZY_MIN ولی هنوز شبیه


def _content(text):
    out = set()
    for t in tokens(text):
        if t not in STOPWORDS:
            out |= {stem(t), t}
            if t in SYNONYMS: out.add(SYNONYMS[t])
    return out


def near(text, intents, limit=2):
    """وقتی هیچ نیتی قطعی نیست: نیت‌هایی که «نزدیک» بودند، تا از مشتری
    بپرسیم منظورش کدام است. [(نیت, امتیاز)] — بهترین‌ها اول."""
    _, rest = smalltalk(text)
    if not rest:
        return []
    msg_forms = token_forms(rest)
    content = _content(rest)
    strong_words = [t for t in tokens(rest) if t not in STOPWORDS and t not in WEAK]
    if not strong_words:
        return []
    cands = []
    for it in intents:
        if not it.get("enabled", True):
            continue
        best = 0.0
        for key in it.get("keys") or []:
            words = norm(key).split()
            kf = _key_forms(key)
            if not kf:
                continue
            hits = [_tok_hit(f, msg_forms) for f in kf]
            # فعل‌ها («میفروشید»، «میدید») در جمله‌های بی‌ربط هم هستند؛ نیمه‌تطبیق
            # فقط با اسم‌های معنادار شمرده می‌شود
            strong = [h for h, w in zip(hits, words)
                      if h and w not in WEAK and w not in STOPWORDS and w not in GENERIC
                      and not w.startswith(("می", "نمی"))]
            if len(kf) >= 2 and strong and not all(hits):
                best = max(best, 0.45 + 0.35 * len(strong) / len(kf))
            if (len(kf) == 1 and len(words[0]) >= 4 and words[0] not in WEAK
                    and not words[0].startswith(("می", "نمی"))):
                for t in strong_words:
                    if len(t) >= 4 and not t.startswith(("می", "نمی")) and t not in GENERIC:
                        r = difflib.SequenceMatcher(None, words[0], t).ratio()
                        if NEAR_FUZZY <= r < FUZZY_MIN:
                            best = max(best, 0.62)
        for ex in it.get("examples") or []:
            exc = _ex_words(ex)
            if len(exc) < 3:
                continue
            cover = len(exc & content) / len(exc)
            if 0.34 <= cover < EXAMPLE_MIN:
                best = max(best, 0.4 + cover * 0.5)
        if best >= NEAR_MIN:
            cands.append((it, best))
    cands.sort(key=lambda x: -x[1])
    return cands[:limit]


# ════════════════════════════════════════════════
#  ناراحتی و شکایت
# ════════════════════════════════════════════════
# wait      — «چرا جواب نمیدید؟» منتظر مانده
# complaint — از خودِ فروشگاه/خرید ناراضی است → فوری
# issue     — دستگاهش مشکل دارد (شاید فقط سؤال تعمیر) → همدلی، نه آژیر
_WAIT = ("جواب نمیدید", "جواب نمیدین", "جواب نمیده", "جواب نمیدن", "چرا جواب", "کسی جواب",
         "هیچکس جواب", "هیچ کس جواب", "کسی نیست", "هیچکس نیست", "منتظرم", "منتظر موندم",
         "خیلی وقته منتظر", "چقدر باید صبر", "هیچ خبری", "خبری نشد", "جوابمو بدید",
         "جواب منو بدید", "پس چی شد")
_COMPLAINT = ("شکایت", "ناراضی", "نارضایتی", "بدقول", "بد قول", "کلاهبردار", "کلاه برداری",
              "کلاهبرداری", "سرم کلاه", "پولمو پس", "پول منو پس", "پولم رو پس", "پولمو بدید",
              "پول منو بدید", "پس نمیدید",
              "پس نمیگیرید", "پس نمی گیرید", "دروغ گفتید", "دروغ میگید", "گول زدید",
              "تقلبی بود", "فیک بود", "بی مسئولیت", "بیمسئولیت", "مسخره کردید", "اعتراض",
              "افتضاح بود", "افتضاحید", "پشیمونم", "پشیمان شدم", "هنوز نرسیده",
              "نرسیده دستم", "دیر کردید", "پیگیری نکردید", "دیگه ازتون خرید نمیکنم",
              "دیگه خرید نمیکنم")
_ISSUE = ("خراب شد", "خراب شده", "خرابه", "کار نمیکنه", "کار نمی کنه", "روشن نمیشه",
          "شارژ نمیشه", "ایراد داره", "ایراد پیدا", "مشکل داره", "مشکل پیدا", "عیب داره",
          "سوخت", "هنگ میکنه", "ریستارت میشه", "ضربه خورد", "افتاد تو آب", "افتاد تو اب",
          "شکسته", "شکست")
_BOUGHT = ("خریدم", "خریدیم", "گرفتم ازتون", "ازتون گرفتم", "ازتون خریدم", "از شما خریدم",
           "از شما گرفتم", "خرید کردم", "تحویل گرفتم")


def mood(text):
    """'wait' | 'complaint' | 'issue' | None"""
    t = f" {norm(text)} "
    has = lambda xs: any(f" {norm(x)} " in t or f" {norm(x)}" in t for x in xs)
    if has(_COMPLAINT):
        return "complaint"
    issue = has(_ISSUE)
    if issue and has(_BOUGHT):
        return "complaint"        # مشکلِ بعد از خرید از خودِ ما
    if has(_WAIT):
        return "wait"
    if issue:
        return "issue"
    return None


MOOD_LEADS = {
    "wait": ["ببخشید که منتظر موندید 🙏 همین الان دوباره به همکارم خبر دادم که فوری پیگیری کنه.",
             "عذر می‌خوام بابت انتظار 🙏 پیامتون رو با اولویت فوری به همکارم رسوندم."],
    "complaint": ["واقعاً متأسفم که این اتفاق افتاده 🙏 پیامتون رو با اولویت فوری به مسئول "
                  "پیگیری دادم؛ همین‌جا جوابتون رو می‌ده.",
                  "خیلی متأسفم 🙏 حق دارید ناراحت باشید. همین الان موضوع رو با اولویت فوری "
                  "به مسئولش سپردم."],
    "issue": ["متأسفم که دستگاهتون مشکل پیدا کرده 🙏",
              "ای بابا، متأسفم 🙏"],
}


# ════════════════════════════════════════════════
#  چند محصول در یک جمله (برای مقایسه)
# ════════════════════════════════════════════════
def products_all(text, default_brand="آیفون"):
    """«۱۳ پرو یا ۱۴ پرو مکس کدوم بهتره؟» → ["آیفون ۱۳ پرو", "آیفون ۱۴ پرو مکس"].
    عدد بی‌برند اینجا مدل آیفون حساب می‌شود (فروشگاه تخصصی اپل است)،
    به شرط اینکه عددی در محدوده‌ی مدل‌ها باشد."""
    t = norm(text)
    out, brand_now = [], None
    for m in _PRODUCT.finditer(t):
        brand, num, var = m.group(1), m.group(2), m.group(3)
        if brand:
            brand_now = _BRANDS[brand]
        if not (brand or num or var):
            continue
        if not brand and not num:
            continue                      # «پرو» تنها
        if not brand and num and not (6 <= int(num) <= 20):
            continue
        b = _BRANDS[brand] if brand else (brand_now or default_brand)
        parts = [b]
        if num: parts.append(num.translate(_FA))
        if var: parts.append(_VARIANTS[var])
        if len(parts) == 1:
            continue
        p = " ".join(parts)
        if p not in out:
            out.append(p)
    return out


def content_words(text, limit=3):
    """کلمه‌های معنادار یک جمله — برای پیشنهاد کلیدواژه هنگام یادگیری."""
    seen, out = set(), []
    for t in tokens(text):
        if (t in STOPWORDS or t in WEAK or t in GENERIC or len(t) < 3 or t.isdigit()
                or t.startswith(("می", "نمی"))):
            continue
        if t not in seen:
            seen.add(t); out.append(t)
    return out[:limit]
