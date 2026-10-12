"""ویس → متن فارسی، روی همین سرور — بدون هیچ API.

موتور: Whisper (نسخه‌ی faster-whisper، روی CPU با int8). ویس از سرور
بیرون نمی‌رود. این بخش «اختیاری» است: تا وقتی با
    bash deploy/install-voice.sh
نصب و آزمایش نشده، ربات مثل قبل کار می‌کند و ویس فقط برای همکار می‌رود.

ایمنی:
  • تبدیل در یک «پروسه‌ی جدا» انجام می‌شود. اگر کتابخانه‌ها روی پردازنده‌ی
    سرور به هر دلیلی کرش کنند (حتی Illegal instruction که در پایتون قابل
    گرفتن نیست)، فقط همان پروسه می‌میرد و ربات سالم می‌ماند.
  • خودِ ربات هیچ‌وقت faster-whisper را import نمی‌کند.
  • فقط وقتی فعال می‌شود که اسکریپت نصب، آزمایش واقعی را با موفقیت گذرانده
    باشد (فایل models/CHOSEN).

ملاحظه‌ی سرورِ مشترک:
  • یک ویس در هر لحظه (صف) و اولویت پایینِ پردازنده (nice)
  • تعداد هسته‌ی مصرفی محدود است (VOICE_THREADS، پیش‌فرض ۲)
  • پروسه بعد از ۳۰ دقیقه بیکاری بسته می‌شود و حافظه آزاد می‌شود
  • هیچ دانلودی هنگام اجرا انجام نمی‌شود؛ مدل فقط از پوشه‌ی models/
"""
import asyncio
import importlib.util
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

log = logging.getLogger("voice")

DIR = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(DIR, "models")
CHOSEN = os.path.join(MODELS, "CHOSEN")

MAX_SEC = int(os.getenv("VOICE_MAX_SEC", "90"))        # ویس بلندتر → مستقیم به همکار
THREADS = int(os.getenv("VOICE_THREADS", "0")) or min(2, os.cpu_count() or 1)
IDLE_UNLOAD = 30 * 60
MAX_CRASHES = 3          # بعد از این تعداد کرشِ پشت‌سرهم، ویس خاموش می‌ماند

# واژه‌های همین فروشگاه — Whisper را به سمت املای درست می‌برد
# («آیفون» نه «ای فون»، «اقساط» نه «اغساط»)
PROMPT = ("سلام. قیمت آیفون ۱۳ پرو مکس چنده؟ خرید اقساطی با چک و طلا، گارانتی، "
          "رجیستری، معاوضه، آیپد، مک‌بوک، اپل‌واچ، ایرپاد، استوک لند.")

# جمله‌هایی که Whisper روی سکوت یا نویز «توهم» می‌زند
_HALLUCINATIONS = ("زیرنویس", "subtitle", "ممنون که تماشا", "ترجمه و", "amara",
                   "کانال ما", "سابسکرایب", "لایک کنید")


# ════════════════════════════════════════════════
#  تنظیمِ نصب‌شده
# ════════════════════════════════════════════════
def _chosen():
    """(نام مدل, گزینه‌ها) از models/CHOSEN — خط اول مدل، بقیه گزینه‌ها
    مثل «novad» (وقتی تشخیص سکوت روی این پردازنده کار نکرد)."""
    try:
        with open(CHOSEN, encoding="utf-8") as f:
            lines = [x.strip() for x in f.read().splitlines() if x.strip()]
    except OSError:
        return "", set()
    return (lines[0] if lines else ""), set(lines[1:])


def model_name():
    return os.getenv("VOICE_MODEL", "").strip() or _chosen()[0]


def use_vad():
    return "novad" not in _chosen()[1]


def installed():
    """بدون import کردنِ خودِ کتابخانه — فقط وجودش و نتیجه‌ی آزمایش نصب."""
    return bool(model_name()) and importlib.util.find_spec("faster_whisper") is not None


# ════════════════════════════════════════════════
#  قضاوت درباره‌ی خروجی Whisper
# ════════════════════════════════════════════════
class Result:
    def __init__(self, text="", ok=False, logprob=0.0, seconds=0.0):
        self.text, self.ok, self.logprob, self.seconds = text, ok, logprob, seconds


def _clean(text):
    return re.sub(r"\s+", " ", text or "").strip(" .،")


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


# ════════════════════════════════════════════════
#  پروسه‌ی کارگر (python voice.py --worker)
# ════════════════════════════════════════════════
def _decode(data):
    """صدا → آرایه‌ی ۱۶ کیلوهرتز. اول PyAV (همراه faster-whisper)؛ اگر نشد،
    ffmpeg سیستم (اگر نصب باشد) — نسخه‌های مختلف PyAV رفتار یکسانی ندارند."""
    try:
        from faster_whisper.audio import decode_audio
        return decode_audio(io.BytesIO(data), sampling_rate=16000)
    except Exception as e:
        ff = shutil.which("ffmpeg")
        if not ff:
            raise RuntimeError(f"decode: {e}")
        import numpy as np
        r = subprocess.run([ff, "-nostdin", "-loglevel", "error", "-i", "pipe:0", "-f", "s16le",
                            "-ac", "1", "-ar", "16000", "pipe:1"], input=data,
                           capture_output=True, timeout=120)
        if r.returncode != 0 or not r.stdout:
            raise RuntimeError(f"decode: {e} / ffmpeg: {r.stderr[-200:]!r}")
        return np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768.0

def _worker():
    """هر خط ورودی مسیر یک فایل صوتی است؛ هر خط خروجی یک JSON."""
    try:
        os.nice(10)                    # سرور مشترک است — اولویت با بقیه
    except Exception:
        pass
    out = sys.stdout
    sys.stdout = sys.stderr            # هر چاپِ ناخواسته‌ی کتابخانه‌ها خط JSON را خراب نکند
    model = None

    def load():
        nonlocal model
        if model is None:
            if os.getenv("VOICE_FAKE"):            # فقط برای آزمایش خودکار
                model = "fake"
            else:
                from faster_whisper import WhisperModel
                model = WhisperModel(model_name(), device="cpu", compute_type="int8",
                                     cpu_threads=THREADS, download_root=MODELS,
                                     local_files_only=True)
        return model

    def reply(d):
        out.write(json.dumps(d, ensure_ascii=False) + "\n"); out.flush()

    for line in sys.stdin:
        path = line.strip()
        if not path:
            continue
        t = time.time()
        try:
            m = load()
            if path == "__warmup__":
                reply({"ready": True, "seconds": time.time() - t}); continue
            if m == "fake":
                txt = open(path, "rb").read().decode("utf-8", "ignore").strip()
                reply({"text": txt, "ok": bool(txt), "logprob": -0.2,
                       "seconds": time.time() - t}); continue
            with open(path, "rb") as f:
                audio = _decode(f.read())
            segments, _info = m.transcribe(audio, language="fa", beam_size=3,
                                           vad_filter=use_vad(),
                                           condition_on_previous_text=False,
                                           initial_prompt=PROMPT, without_timestamps=True)
            text, ok, lp = judge(list(segments))
            reply({"text": text, "ok": ok, "logprob": lp, "seconds": time.time() - t})
        except Exception as e:
            reply({"error": str(e)[:300]})


# ════════════════════════════════════════════════
#  سمتِ ربات
# ════════════════════════════════════════════════
_proc = None
_last_used = 0.0
_crashes = 0
_broken = ""
_lock = None


def available():
    return installed() and not _broken


def status():
    """یک خط برای صفحه‌ی تنظیمات و لاگ."""
    if not installed():
        return "نصب نشده (bash deploy/install-voice.sh)"
    if _broken:
        return f"خاموش به‌خاطر خطا: {_broken[:80]}"
    return (f"آماده · مدل {model_name()}" + ("" if use_vad() else " · بدون تشخیص سکوت")
            + (" · در حافظه" if _proc and _proc.returncode is None else ""))


async def _ensure_proc():
    global _proc
    if _proc is not None and _proc.returncode is None:
        return _proc
    _proc = await asyncio.create_subprocess_exec(
        sys.executable, os.path.abspath(__file__), "--worker",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, cwd=DIR)
    return _proc


async def _kill():
    global _proc
    p, _proc = _proc, None
    if p is not None and p.returncode is None:
        try:
            p.kill(); await p.wait()
        except Exception:
            pass


async def _ask(line, timeout):
    """یک درخواست به کارگر؛ dict جواب، یا None اگر کارگر مُرد/دیر کرد."""
    global _crashes, _broken, _last_used
    p = await _ensure_proc()
    try:
        p.stdin.write((line + "\n").encode()); await p.stdin.drain()
        raw = await asyncio.wait_for(p.stdout.readline(), timeout)
    except asyncio.TimeoutError:
        log.warning("voice: زمان تبدیل تمام شد — کارگر بسته می‌شود")
        await _kill(); return None
    except Exception as e:
        raw = b""; log.error(f"voice: {e}")
    if not raw:                                     # کارگر کرش کرد
        await _kill()
        _crashes += 1
        log.error(f"voice: پروسه‌ی تبدیل از کار افتاد ({_crashes}/{MAX_CRASHES})")
        if _crashes >= MAX_CRASHES:
            _broken = "پروسه‌ی تبدیل چند بار پشت سر هم از کار افتاد"
        return None
    _crashes = 0
    _last_used = time.time()
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        return None


async def transcribe(data, timeout=None):
    """bytes ویس (ogg/opus، mp4، mp3…) → Result یا None. هرگز استثنا بیرون نمی‌دهد."""
    global _lock, _broken
    if not available():
        return None
    if _lock is None:
        _lock = asyncio.Lock()
    path = None
    try:
        fd, path = tempfile.mkstemp(suffix=".ogg", prefix="tgvoice_")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        async with _lock:
            d = await _ask(path, timeout or max(90, MAX_SEC * 3))
        if not d:
            return None
        if "error" in d:
            log.error(f"voice: {d['error']}")
            if "snapshot" in d["error"] or "No such file" in d["error"]:
                _broken = "مدل پیدا نشد — دوباره: bash deploy/install-voice.sh"
            return None
        return Result(d.get("text", ""), bool(d.get("ok")), float(d.get("logprob", 0)),
                      float(d.get("seconds", 0)))
    except Exception as e:
        log.error(f"voice: {e}")
        return None
    finally:
        if path:
            try: os.unlink(path)
            except OSError: pass


async def warmup():
    """بارگذاری مدل پس از روشن شدن ربات، تا اولین ویس معطل نشود."""
    global _lock
    if not available():
        return
    if _lock is None:
        _lock = asyncio.Lock()
    async with _lock:
        d = await _ask("__warmup__", 300)
    if d and d.get("ready"):
        log.info(f"voice: مدل {model_name()} آماده شد ({d.get('seconds', 0):.1f} ثانیه)")


async def idle_loop():
    """کارگرِ بیکار بسته می‌شود تا حافظه آزاد شود — سرور مشترک است."""
    while True:
        await asyncio.sleep(300)
        if (_proc is not None and _proc.returncode is None
                and time.time() - _last_used > IDLE_UNLOAD
                and not (_lock and _lock.locked())):
            await _kill()
            log.info("voice: کارگرِ بیکار بسته شد و حافظه آزاد شد")


async def shutdown():
    await _kill()


if __name__ == "__main__" and "--worker" in sys.argv:
    _worker()
