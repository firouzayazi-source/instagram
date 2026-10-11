#!/usr/bin/env bash
# نصب «ویس به متن» فارسی — روی همین سرور، بدون هیچ API.
#   bash deploy/install-voice.sh            ← انتخاب خودکار مدل بر اساس رم و دیسک
#   bash deploy/install-voice.sh turbo      ← بهترین کیفیت (حدود ۱٫۶ گیگ دیسک، ۱٫۵ گیگ رم)
#   bash deploy/install-voice.sh small      ← سبک (حدود ۵۰۰ مگ دیسک و رم)، دقت کمتر
#   bash deploy/install-voice.sh remove     ← حذف کامل
# فقط داخل پوشه‌ی همین پروژه کار می‌کند (venv/ و models/) — به بقیه‌ی سرور کاری ندارد.
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"
PY="$DIR/venv/bin/python"; PIP="$DIR/venv/bin/pip"
[ -x "$PY" ] || { echo "❌ محیط پایتون پروژه ($DIR/venv) پیدا نشد."; exit 1; }

if [ "${1:-}" = "remove" ]; then
  rm -rf "$DIR/models"
  "$PIP" uninstall -y faster-whisper ctranslate2 >/dev/null 2>&1 || true
  echo "✅ ویس به متن حذف شد. حالا: bash deploy/restart.sh"
  exit 0
fi

CORES=$(nproc)
MEM_MB=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
DISK_MB=$(df -Pm "$DIR" | awk 'NR==2 {print $4}')
echo "▶ منابع سرور:  هسته: $CORES  ·  رم آزاد: ${MEM_MB}MB  ·  دیسک آزاد: ${DISK_MB}MB"

MODEL="${1:-auto}"
if [ "$MODEL" = "auto" ]; then
  if [ "$MEM_MB" -ge 3000 ] && [ "$DISK_MB" -ge 4000 ]; then MODEL=large-v3-turbo
  elif [ "$MEM_MB" -ge 1200 ] && [ "$DISK_MB" -ge 1500 ]; then MODEL=small
  else echo "❌ رم یا دیسک کافی نیست (دست‌کم ۱٫۲ گیگ رم آزاد و ۱٫۵ گیگ دیسک)."; exit 1; fi
fi
[ "$MODEL" = "turbo" ] && MODEL=large-v3-turbo
echo "▶ مدل انتخاب‌شده: $MODEL"

echo "▶ نصب faster-whisper داخل venv همین پروژه…"
"$PIP" install -q "faster-whisper==1.2.1"

echo "▶ دانلود مدل در $DIR/models (فقط یک‌بار)…"
mkdir -p "$DIR/models"
"$PY" - "$MODEL" <<'PYEOF'
import sys, time, os
from faster_whisper import WhisperModel
name = sys.argv[1]
t = time.time()
m = WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=1, download_root="models")
print(f"   مدل آماده شد ({time.time()-t:.0f} ثانیه)")
# آزمایش: یک ثانیه سکوت — نباید خطا بدهد
import numpy as np
segs, _ = m.transcribe(np.zeros(16000, dtype=np.float32), language="fa", vad_filter=True)
list(segs)
open(os.path.join("models", "CHOSEN"), "w").write(name)
print("   آزمایش موفق")
PYEOF

echo
echo "✅ ویس به متن نصب شد (مدل $MODEL)."
echo "   حالا ربات را ری‌استارت کنید:  bash deploy/restart.sh"
echo "   خاموش/روشن: پنل ← تنظیمات ← «🎤 ویس به متن»"
