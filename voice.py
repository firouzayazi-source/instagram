"""ویس → متن فارسی، روی همین سرور — بدون هیچ API.

موتور: Whisper (نسخه‌ی faster-whisper، روی CPU با int8). ویس از سرور
بیرون نمی‌رود. این بخش «اختیاری» است: تا وقتی با
    bash deploy/install-voice.sh
نصب نشده، ربات مثل قبل کار می‌کند و ویس فقط برای همکار فرستاده می‌شود.

ملاحظه‌ی سرورِ مشترک:
  • فقط یک ویس در هر لحظه پردازش می‌شود (صف)
  • تعداد هسته‌ی مصرفی محدود است (VOICE_THREADS، پیش‌فرض ۲)
  • مدل بعد از ۳۰ دقیقه بیکاری از حافظه خالی می‌شود
  • هیچ دانلودی هنگام اجرا انجام نمی‌شود؛ مدل فقط از پوشه‌ی models/ همین
    پروژه خوانده می‌شود
"""
import asyncio
import gc
import io
import logging
import os
import re
import threading
import time

log = logging.getLogger("voice")

DIR = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(DIR, "models")
CHOSEN = os.path.join(MODELS, "CHOSEN")

MAX_SEC = int(os.getenv("VOICE_MAX_SEC", "90"))        # ویس بلندتر → مستقیم به همکار
THREADS = int(os.getenv("VOICE_THREADS", "0")) or min(2, os.cpu_count() or 1)
IDLE_UNLOAD = 30 * 60

# واژه‌های همین فروشگاه — Whisper را به سمت املای درست می‌برد
# («آیفون» نه «ای فون»، «اقساط» نه «اغساط»)
PROMPT = ("سلام. قیمت آیفون ۱۳ پرو مکس چنده؟ خرید اقساطی با چک و طلا، گارانتی، "
          "رجیستری، معاوضه، آیپد، مک‌بوک، اپل‌واچ، ایرپاد، استوک لند.")

# جمله‌هایی که Whisper روی سکوت یا نویز «توهم» می‌زند
_HALLUCINATIONS = ("زیرنویس", "subtitle", "ممنون که تماشا", "ترجمه و", "amara",
                   "کانال ما", "سابسکرایب", "لایک کنید")

_model = None
_name = None
_last_used = 0.0
_broken = ""
_load_lock = threading.Lock()
_sem = None


def model_name():
    n = os.getenv("VOICE_MODEL", "").strip()
    if n:
        return n
    try:
        with open(CHOSEN, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def installed():
    try:
        import faster_whisper  # noqa: F401
    except Exception:
        return False
    return bool(model_name())


def available():
    return installed() and not _broken


def status():
    """یک خط برای صفحه‌ی تنظیمات."""
    if not installed():
        return "نصب نشده (bash deploy/install-voice.sh)"
    if _broken:
        if "snapshot" in _broken or "No such file" in _broken:
            return "مدل پیدا نشد — دوباره: bash deploy/install-voice.sh"
        return f"خطا: {_broken[:60]}"
    return f"آماده · مدل {model_name()}" + (" · در حافظه" if _model else "")


def _load():
    global _model, _name, _broken
    with _load_lock:
        if _model is not None:
            return _model
        from faster_whisper import WhisperModel
        t = time.time()
        name = model_name()
        try:
            _model = WhisperModel(name, device="cpu", compute_type="int8",
                                  cpu_threads=THREADS, download_root=MODELS,
                                  local_files_only=True)
        except Exception as e:
            _broken = str(e)
            log.error(f"voice: مدل «{name}» بارگذاری نشد: {e}")
            raise
        _name = name
        log.info(f"voice: مدل {name} در {time.time() - t:.1f} ثانیه بارگذاری شد "
                 f"({THREADS} هسته)")
        return _model


class Result:
    def __init__(self, text="", ok=False, logprob=0.0, seconds=0.0):
        self.text, self.ok, self.logprob, self.seconds = text, ok, logprob, seconds


def _clean(text):
    text = re.sub(r"\s+", " ", text or "").strip(" .،")
    return text


def judge(segments):
    """از قطعه‌های Whisper: (متن, قابل‌اعتماد؟, میانگین log-prob)."""
    segs = [s for s in segments if (s.text or "").strip()]
    if not segs:
        return "", False, 0.0
    text = _clean(" ".join(s.text.strip() for s in segs))
    w = [max(1, len(s.text)) for s in segs]
    lp = sum(s.avg_logprob * x for s, x in zip(segs, w)) / sum(w)
    nsp = max(s.no_speech_prob for s in segs)
    low = text.lower()
    ok = bool(text) and len(text) >= 2 and lp > -1.0 and not (nsp > 0.6 and lp < -0.6)
    if any(h in low for h in _HALLUCINATIONS):
        ok = False
    # مدل تکهٔ بلندی از همان راهنما را تکرار کرده (نه «قیمت آیفون» کوتاهِ واقعی)
    if len(text) > 30 and text in _clean(PROMPT):
        ok = False
    return text, ok, lp


def _run(data):
    global _last_used
    m = _load()
    t = time.time()
    segments, _info = m.transcribe(io.BytesIO(data), language="fa", beam_size=3,
                                   vad_filter=True, condition_on_previous_text=False,
                                   initial_prompt=PROMPT, without_timestamps=True)
    text, ok, lp = judge(list(segments))
    _last_used = time.time()
    return Result(text, ok, lp, time.time() - t)


async def transcribe(data, timeout=None):
    """bytes ویس (ogg/opus، mp4، mp3…) → Result. هرگز استثنا بیرون نمی‌دهد."""
    global _sem
    if not available():
        return None
    if _sem is None:
        _sem = asyncio.Semaphore(1)
    try:
        async with _sem:
            loop = asyncio.get_running_loop()
            return await asyncio.wait_for(loop.run_in_executor(None, _run, data),
                                          timeout or max(60, MAX_SEC * 2))
    except asyncio.TimeoutError:
        log.warning("voice: زمان تبدیل تمام شد")
    except Exception as e:
        log.error(f"voice: {e}")
    return None


async def warmup():
    """بارگذاری مدل پس از روشن شدن ربات، تا اولین ویس معطل نشود."""
    if not available():
        return
    try:
        await asyncio.get_running_loop().run_in_executor(None, _load)
        global _last_used
        _last_used = time.time()
    except Exception:
        pass


async def idle_loop():
    """مدل بیکار را از حافظه خالی می‌کند — سرور مشترک است."""
    global _model
    while True:
        await asyncio.sleep(300)
        if _model is not None and time.time() - _last_used > IDLE_UNLOAD:
            with _load_lock:
                _model = None
            gc.collect()
            log.info("voice: مدل بیکار از حافظه خالی شد")
