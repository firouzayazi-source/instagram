"""مشخصات فنی آیفون‌ها — برای «مشخصات ۱۵ پرو؟» و «۱۳ با ۱۴ چه فرقی داره؟».

فقط مشخصات رسمی و پایدار آمده (سال، تراشه، صفحه، دوربین، درگاه و چند
ویژگی شاخص) — چیزهایی که با کشور و نسخه عوض می‌شوند (قیمت، حافظه، رنگ،
باتری به ساعت) عمداً اینجا نیست؛ قیمت از لیست قیمت روز می‌آید.

هر مدل: (سال، تراشه، اینچ، نوع صفحه، هرتز، دوربین، تله‌فوتو، درگاه، ویژگی‌ها)
"""
import re
import brain

_FA = str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫")


def fa(x):
    return str(x).translate(_FA)


# دوربین: متنِ کوتاه پشت گوشی؛ tele: زوم اپتیکال تله‌فوتو (۰ = ندارد)
IPHONES = {
    "11":         (2019, "A13", 6.1, "LCD", 60, "دو دوربین ۱۲ مگاپیکسل", 0, "Lightning",
                   []),
    "11 pro":     (2019, "A13", 5.8, "OLED", 60, "سه دوربین ۱۲ مگاپیکسل", 2, "Lightning",
                   []),
    "11 pro max": (2019, "A13", 6.5, "OLED", 60, "سه دوربین ۱۲ مگاپیکسل", 2, "Lightning",
                   []),
    "12 mini":    (2020, "A14", 5.4, "OLED", 60, "دو دوربین ۱۲ مگاپیکسل", 0, "Lightning",
                   ["5G", "MagSafe"]),
    "12":         (2020, "A14", 6.1, "OLED", 60, "دو دوربین ۱۲ مگاپیکسل", 0, "Lightning",
                   ["5G", "MagSafe"]),
    "12 pro":     (2020, "A14", 6.1, "OLED", 60, "سه دوربین ۱۲ مگاپیکسل + LiDAR", 2,
                   "Lightning", ["5G", "MagSafe", "LiDAR"]),
    "12 pro max": (2020, "A14", 6.7, "OLED", 60, "سه دوربین ۱۲ مگاپیکسل + LiDAR", 2.5,
                   "Lightning", ["5G", "MagSafe", "LiDAR"]),
    "13 mini":    (2021, "A15", 5.4, "OLED", 60, "دو دوربین ۱۲ مگاپیکسل", 0, "Lightning",
                   ["5G", "MagSafe"]),
    "13":         (2021, "A15", 6.1, "OLED", 60, "دو دوربین ۱۲ مگاپیکسل", 0, "Lightning",
                   ["5G", "MagSafe"]),
    "13 pro":     (2021, "A15 (GPU ۵ هسته)", 6.1, "OLED", 120, "سه دوربین ۱۲ مگاپیکسل + LiDAR", 3,
                   "Lightning", ["5G", "MagSafe", "LiDAR", "ProMotion"]),
    "13 pro max": (2021, "A15 (GPU ۵ هسته)", 6.7, "OLED", 120, "سه دوربین ۱۲ مگاپیکسل + LiDAR", 3,
                   "Lightning", ["5G", "MagSafe", "LiDAR", "ProMotion"]),
    "14":         (2022, "A15 (GPU ۵ هسته)", 6.1, "OLED", 60, "دو دوربین ۱۲ مگاپیکسل", 0, "Lightning",
                   ["5G", "MagSafe"]),
    "14 plus":    (2022, "A15 (GPU ۵ هسته)", 6.7, "OLED", 60, "دو دوربین ۱۲ مگاپیکسل", 0, "Lightning",
                   ["5G", "MagSafe"]),
    "14 pro":     (2022, "A16", 6.1, "OLED", 120, "اصلی ۴۸ + دو دوربین ۱۲ مگاپیکسل", 3,
                   "Lightning", ["5G", "MagSafe", "LiDAR", "ProMotion", "Dynamic Island",
                                 "Always-On"]),
    "14 pro max": (2022, "A16", 6.7, "OLED", 120, "اصلی ۴۸ + دو دوربین ۱۲ مگاپیکسل", 3,
                   "Lightning", ["5G", "MagSafe", "LiDAR", "ProMotion", "Dynamic Island",
                                 "Always-On"]),
    "15":         (2023, "A16", 6.1, "OLED", 60, "اصلی ۴۸ + فوق‌عریض ۱۲ مگاپیکسل", 0, "USB-C",
                   ["5G", "MagSafe", "Dynamic Island"]),
    "15 plus":    (2023, "A16", 6.7, "OLED", 60, "اصلی ۴۸ + فوق‌عریض ۱۲ مگاپیکسل", 0, "USB-C",
                   ["5G", "MagSafe", "Dynamic Island"]),
    "15 pro":     (2023, "A17 Pro", 6.1, "OLED", 120, "اصلی ۴۸ + دو دوربین ۱۲ مگاپیکسل", 3,
                   "USB-C", ["5G", "MagSafe", "LiDAR", "ProMotion", "Dynamic Island",
                             "Always-On", "بدنه‌ی تیتانیوم", "دکمه‌ی Action"]),
    "15 pro max": (2023, "A17 Pro", 6.7, "OLED", 120, "اصلی ۴۸ + دو دوربین ۱۲ مگاپیکسل", 5,
                   "USB-C", ["5G", "MagSafe", "LiDAR", "ProMotion", "Dynamic Island",
                             "Always-On", "بدنه‌ی تیتانیوم", "دکمه‌ی Action"]),
    "16":         (2024, "A18", 6.1, "OLED", 60, "اصلی ۴۸ + فوق‌عریض ۱۲ مگاپیکسل", 0, "USB-C",
                   ["5G", "MagSafe", "Dynamic Island", "دکمه‌ی Action", "Camera Control"]),
    "16 plus":    (2024, "A18", 6.7, "OLED", 60, "اصلی ۴۸ + فوق‌عریض ۱۲ مگاپیکسل", 0, "USB-C",
                   ["5G", "MagSafe", "Dynamic Island", "دکمه‌ی Action", "Camera Control"]),
    "16e":        (2025, "A18", 6.1, "OLED", 60, "یک دوربین ۴۸ مگاپیکسل", 0, "USB-C",
                   ["5G", "دکمه‌ی Action"]),
    "16 pro":     (2024, "A18 Pro", 6.3, "OLED", 120, "اصلی ۴۸ + فوق‌عریض ۴۸ + تله ۱۲ مگاپیکسل",
                   5, "USB-C", ["5G", "MagSafe", "LiDAR", "ProMotion", "Dynamic Island",
                                "Always-On", "بدنه‌ی تیتانیوم", "دکمه‌ی Action",
                                "Camera Control"]),
    "16 pro max": (2024, "A18 Pro", 6.9, "OLED", 120,
                   "اصلی ۴۸ + فوق‌عریض ۴۸ + تله ۱۲ مگاپیکسل", 5, "USB-C",
                   ["5G", "MagSafe", "LiDAR", "ProMotion", "Dynamic Island", "Always-On",
                    "بدنه‌ی تیتانیوم", "دکمه‌ی Action", "Camera Control"]),
    "17":         (2025, "A19", 6.3, "OLED", 120, "اصلی ۴۸ + فوق‌عریض ۴۸ مگاپیکسل", 0, "USB-C",
                   ["5G", "MagSafe", "ProMotion", "Dynamic Island", "Always-On",
                    "دکمه‌ی Action", "Camera Control", "دوربین سلفی ۱۸ مگاپیکسل"]),
    "air":        (2025, "A19 Pro", 6.5, "OLED", 120, "یک دوربین ۴۸ مگاپیکسل", 0, "USB-C",
                   ["5G", "MagSafe", "ProMotion", "Dynamic Island", "Always-On",
                    "دکمه‌ی Action", "Camera Control", "بسیار باریک (۵٫۶ میلی‌متر)"]),
    "17 pro":     (2025, "A19 Pro", 6.3, "OLED", 120, "سه دوربین ۴۸ مگاپیکسل", 4, "USB-C",
                   ["5G", "MagSafe", "LiDAR", "ProMotion", "Dynamic Island", "Always-On",
                    "دکمه‌ی Action", "Camera Control", "دوربین سلفی ۱۸ مگاپیکسل"]),
    "17 pro max": (2025, "A19 Pro", 6.9, "OLED", 120, "سه دوربین ۴۸ مگاپیکسل", 4, "USB-C",
                   ["5G", "MagSafe", "LiDAR", "ProMotion", "Dynamic Island", "Always-On",
                    "دکمه‌ی Action", "Camera Control", "دوربین سلفی ۱۸ مگاپیکسل"]),
}
# ترتیب قدرت تراشه‌ها — برای اینکه «تراشه‌ی قوی‌تر» فقط به نفع مدلِ واقعاً قوی‌تر نوشته شود
CHIP_RANK = ["A13", "A14", "A15", "A15 (GPU ۵ هسته)", "A16", "A17 Pro", "A18", "A18 Pro",
             "A19", "A19 Pro"]
_VAR = {"پرو مکس": "pro max", "پرو": "pro", "پلاس": "plus", "مینی": "mini", "ایر": "air"}
_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def key_of(product):
    """«آیفون ۱۳ پرو مکس» → «13 pro max» (اگر در جدول باشد)، وگرنه None."""
    p = (product or "").strip()
    if not p.startswith("آیفون"):
        return None
    rest = p[len("آیفون"):].strip().translate(_TO_EN)
    for fa_v, en in _VAR.items():
        rest = re.sub(rf"(?<!\S){fa_v}(?!\S)", en, rest)
    rest = " ".join(rest.split())
    if rest in ("air", "17 air"):
        rest = "air"
    return rest if rest in IPHONES else None


def name_of(key):
    if key == "air":
        return "آیفون ایر"
    num, *var = key.split()
    inv = {v: k for k, v in _VAR.items()}
    v = " ".join(var)
    return "آیفون " + fa(num.replace("e", "")) + ("e" if num.endswith("e") else "") + \
        (" " + inv.get(v, v) if v else "")


_16E = re.compile(r"(?:16|۱۶)\s*(?:e|ای)\b", re.I)


def find_models(text):
    """مدل‌های جدولِ مشخصات که در جمله آمده‌اند، به ترتیب."""
    out = []
    t = text or ""
    if _16E.search(t):
        out.append("16e")
        t = _16E.sub(" ", t)        # «۱۶e» دیگر «۱۶» حساب نشود
    for p in brain.products_all(t):
        k = key_of(p)
        if k and k not in out:
            out.append(k)
    return out


def _row(k):
    y, chip, inch, kind, hz, cam, tele, port, feats = IPHONES[k]
    return {"y": y, "chip": chip, "inch": inch, "kind": kind, "hz": hz, "cam": cam,
            "tele": tele, "port": port, "feats": feats}


def _cams(c):
    for w, n in (("یک", 1), ("دو", 2), ("سه", 3)):
        if c.startswith(w):
            return n
    return 1 + c.split("+ LiDAR")[0].count("+") + (1 if "دو دوربین" in c else 0)


def _mp48(c):
    """چند دوربینِ پشتِ ۴۸ مگاپیکسلی."""
    for w, n in (("یک دوربین ۴۸", 1), ("دو دوربین ۴۸", 2), ("سه دوربین ۴۸", 3)):
        if c.startswith(w):
            return n
    return c.count("۴۸")


def _tele(t):
    return f"زوم اپتیکال {fa(t)}x" if t else "ندارد"


def spec_text(k):
    r = _row(k)
    feats = "، ".join(f for f in r["feats"] if f != "5G")
    return (f"📱 <b>{name_of(k)}</b>  ·  مشخصات اصلی\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📅 سال عرضه: {fa(r['y'])}\n"
            f"⚙️ تراشه: {r['chip']}\n"
            f"📐 صفحه: {fa(r['inch'])} اینچ {r['kind']} · {fa(r['hz'])} هرتز\n"
            f"📸 دوربین: {r['cam']}\n"
            f"🔭 تله‌فوتو: {_tele(r['tele'])}\n"
            f"🔌 درگاه: {r['port']}\n"
            + (f"✨ {feats}\n" if feats else ""))


def _newer_points(a, b):
    """چیزهایی که b نسبت به a بیشتر دارد."""
    ra, rb = _row(a), _row(b)
    pts = []
    if CHIP_RANK.index(rb["chip"]) > CHIP_RANK.index(ra["chip"]):
        pts.append(f"تراشه‌ی {rb['chip']} (در برابر {ra['chip']})")
    if rb["hz"] > ra["hz"]:
        pts.append(f"صفحه‌ی {fa(rb['hz'])} هرتز — روان‌تر")
    if rb["inch"] > ra["inch"]:
        pts.append(f"صفحه‌ی بزرگ‌تر ({fa(rb['inch'])} اینچ)")
    if rb["tele"] > ra["tele"]:
        pts.append(f"تله‌فوتو با {_tele(rb['tele'])}")
    if _cams(rb["cam"]) > _cams(ra["cam"]):
        pts.append(f"{fa(_cams(rb['cam']))} دوربین پشت (در برابر {fa(_cams(ra['cam']))})")
    if "۴۸" in rb["cam"] and "۴۸" not in ra["cam"]:
        pts.append("دوربین اصلی ۴۸ مگاپیکسل")
    elif _mp48(rb["cam"]) > _mp48(ra["cam"]) and _cams(rb["cam"]) >= 2:
        pts.append("دوربین‌های ۴۸ مگاپیکسلی بیشتر"
                   + (" (فوق‌عریض ۴۸)" if "فوق‌عریض ۴۸" in rb["cam"] else ""))
    if rb["port"] == "USB-C" and ra["port"] != "USB-C":
        pts.append(f"درگاه {rb['port']}")
    extra = [f for f in rb["feats"] if f not in ra["feats"]]
    if extra:
        pts.append("، ".join(extra))
    return pts


def compare_text(keys):
    keys = keys[:3]
    rows = [_row(k) for k in keys]
    sep = "  ·  "
    head = " در برابر ".join(f"<b>{name_of(k)}</b>" for k in keys)
    out = [f"⚖️ {head}", "━━━━━━━━━━━━━━━",
           "📅 سال: " + sep.join(fa(r["y"]) for r in rows),
           "⚙️ تراشه: " + sep.join(r["chip"] for r in rows),
           "📐 صفحه: " + sep.join(f"{fa(r['inch'])}″ {fa(r['hz'])}Hz" for r in rows),
           "📸 دوربین: " + sep.join(r["cam"] for r in rows),
           "🔭 تله‌فوتو: " + sep.join(_tele(r["tele"]) for r in rows),
           "🔌 درگاه: " + sep.join(r["port"] for r in rows),
           "━━━━━━━━━━━━━━━"]
    if len(keys) == 2:
        a, b = keys
        if (_row(a)["y"], _row(a)["inch"]) > (_row(b)["y"], _row(b)["inch"]):
            a, b = b, a
        pts = _newer_points(a, b)
        back = _newer_points(b, a)
        if pts:
            out.append(f"🧠 <b>{name_of(b)}</b> نسبت به {name_of(a)}:")
            out += [f"  ✔️ {p}" for p in pts]
        if back:
            out.append(f"🧠 <b>{name_of(a)}</b> در عوض:")
            out += [f"  ✔️ {p}" for p in back]
        if not pts and not back:
            out.append("🧠 مشخصات اصلی این دو تقریباً یکی است؛ تفاوت بیشتر در قیمت و وضعیت دستگاه است.")
    return "\n".join(out)
