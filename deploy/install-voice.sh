#!/usr/bin/env bash
# نصب «ویس به متن» فارسی — روی همین سرور، بدون هیچ API.
#   bash deploy/install-voice.sh            ← انتخاب خودکار مدل بر اساس رم و دیسک
#   bash deploy/install-voice.sh turbo      ← بهترین کیفیت (حدود ۱٫۶ گیگ دیسک، ۱٫۵ گیگ رم)
#   bash deploy/install-voice.sh small      ← سبک (حدود ۵۰۰ مگ دیسک و رم)، دقت کمتر
#   bash deploy/install-voice.sh remove     ← حذف کامل
# فقط داخل پوشه‌ی همین پروژه کار می‌کند (venv/ و models/) — به بقیه‌ی سرور کاری ندارد.
# ویس فقط وقتی در ربات روشن می‌شود که آزمایش آخر همین اسکریپت موفق باشد.
set -uo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"
PY="$DIR/venv/bin/python"; PIP="$DIR/venv/bin/pip"
[ -x "$PY" ] || { echo "❌ محیط پایتون پروژه ($DIR/venv) پیدا نشد."; exit 1; }

why() {   # کد خروج → توضیح
  case "$1" in
    132) echo "پردازنده‌ی سرور یکی از دستورهای لازم را ندارد (Illegal instruction)";;
    137) echo "حافظه‌ی سرور کافی نبود (Killed)";;
    124) echo "بیش از حد طول کشید";;
    *)   echo "کد خطا $1";;
  esac
}
fail() { rm -f "$DIR/models/CHOSEN"; echo; echo "❌ $1"; echo "   ربات سالم است و مثل قبل کار می‌کند (ویس فقط برای همکار می‌رود)."; exit 1; }

if [ "${1:-}" = "remove" ]; then
  rm -rf "$DIR/models"
  "$PIP" uninstall -y faster-whisper ctranslate2 onnxruntime >/dev/null 2>&1 || true
  echo "✅ ویس به متن حذف شد. حالا ربات را ری‌استارت کنید."
  exit 0
fi

CORES=$(nproc)
MEM_MB=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
DISK_MB=$(df -Pm "$DIR" | awk 'NR==2 {print $4}')
FLAGS=$(grep -m1 -o -w 'sse4_2\|popcnt\|avx\|avx2\|fma' /proc/cpuinfo | sort -u | tr '\n' ' ')
echo "▶ منابع سرور:  هسته: $CORES  ·  رم آزاد: ${MEM_MB}MB  ·  دیسک آزاد: ${DISK_MB}MB"
echo "▶ پردازنده: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs)"
echo "   قابلیت‌ها: ${FLAGS:-(هیچ‌کدام از sse4_2/avx)}"

MODEL="${1:-auto}"
if [ "$MODEL" = "auto" ]; then
  if [ "$MEM_MB" -ge 3000 ] && [ "$DISK_MB" -ge 4000 ] && [ "$CORES" -ge 4 ]; then MODEL=large-v3-turbo
  elif [ "$MEM_MB" -ge 1200 ] && [ "$DISK_MB" -ge 1500 ]; then MODEL=small
  else fail "رم یا دیسک کافی نیست (دست‌کم ۱٫۲ گیگ رم آزاد و ۱٫۵ گیگ دیسک)."; fi
fi
[ "$MODEL" = "turbo" ] && MODEL=large-v3-turbo
echo "▶ مدل انتخاب‌شده: $MODEL"

echo "▶ نصب کتابخانه‌ها داخل venv همین پروژه…"
# numpy ۲٫۳ به بعد پردازنده‌های قدیمی/مجازیِ بدون x86-64-v2 را پشتیبانی نمی‌کند
# av: faster-whisper با PyAV قدیمی‌تر از ۱۳ کار نمی‌کند (metadata_errors)
"$PIP" install -q --upgrade "faster-whisper==1.2.1" "numpy>=1.24,<2.3" "av>=15,<19" \
  || fail "نصب کتابخانه‌ها ناموفق بود."

echo "▶ آزمایش کتابخانه‌ها روی این پردازنده…"
VERS=$(timeout 120 "$PY" -c "import numpy, av, tokenizers, ctranslate2; print(f'numpy {numpy.__version__} · av {av.__version__} · ctranslate2 {ctranslate2.__version__}')" 2>/tmp/voice_err.txt)
RC=$?
[ $RC -eq 0 ] || { tail -3 /tmp/voice_err.txt; fail "کتابخانه‌ها روی این سرور اجرا نشدند: $(why $RC)"; }
echo "   ✔ $VERS"
command -v ffmpeg >/dev/null && echo "   ✔ ffmpeg سیستم هم هست (پشتیبان)"

echo "▶ دانلود مدل در $DIR/models (فقط یک‌بار)…"
mkdir -p "$DIR/models"
timeout 1800 "$PY" -c "from faster_whisper.utils import download_model; download_model('$MODEL', cache_dir='models')" \
  || fail "دانلود مدل ناموفق بود (اینترنت سرور یا دسترسی به huggingface.co)."

# یک ثانیه سکوت برای آزمایش واقعیِ همان پروسه‌ای که ربات استفاده می‌کند
"$PY" - <<'PYEOF'
import wave
w = wave.open("models/_test.wav", "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
w.writeframes(b"\x00\x00" * 16000); w.close()
PYEOF

trial() {   # $1 = گزینه‌ی اضافه (خالی یا novad)
  printf '%s\n%s\n' "$MODEL" "$1" > "$DIR/models/CHOSEN"
  OUT=$(echo "$DIR/models/_test.wav" | timeout 600 "$PY" voice.py --worker 2>/tmp/voice_err.txt)
  RC=$?
  if [ $RC -eq 0 ] && echo "$OUT" | grep -q '"ok"' && ! echo "$OUT" | grep -q '"error"'; then return 0; fi
  echo "   ✘ $(why $RC) ${OUT:0:200}"; tail -2 /tmp/voice_err.txt
  return 1
}

rm -f "$DIR/models/SPEED"     # سرعت از نو اندازه گرفته می‌شود (مثلاً بعد از ارتقای پردازنده)
echo "▶ آزمایش واقعیِ تبدیل ویس…"
secs() { echo "$OUT" | grep -o '"seconds": [0-9.]*' | grep -o '[0-9.]*$' | cut -c1-5; }
if trial ""; then
  echo "   ✔ با تشخیص سکوت — $(secs) ثانیه برای ۱ ثانیه صدا (با بارگذاری مدل)"
elif trial "novad"; then
  echo "   ✔ بدون تشخیص سکوت — $(secs) ثانیه (این بخش روی پردازنده‌ی سرور اجرا نشد؛ مشکلی نیست)"
else
  rm -f "$DIR/models/_test.wav"
  fail "تبدیل ویس روی این سرور اجرا نشد."
fi
rm -f "$DIR/models/_test.wav"

echo
echo "✅ ویس به متن نصب و آزمایش شد (مدل $MODEL)."
echo "   حالا ربات را ری‌استارت کنید."
echo "   خاموش/روشن: پنل ← تنظیمات ← «🎤 ویس به متن»"
