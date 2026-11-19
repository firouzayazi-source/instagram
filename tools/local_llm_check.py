"""آزمایش مدل هوش مصنوعی محلی روی همین سرور (آزمایشی؛ docs/LOCAL_LLM.md).

فقط می‌خواند و می‌سنجد؛ چیزی نصب یا تنظیم نمی‌کند و به .env دست نمی‌زند:
  ۱) منابع سرور (رم آزاد و هسته‌ها) برای مدل‌های کوچک کافی است؟
  ۲) سرویس سازگار با OpenAI (مثلاً Ollama روی 127.0.0.1:11434) جواب می‌دهد و چه مدل‌هایی دارد؟
  ۳) چند سؤال فارسی نمونه: زمان جواب و خود جواب، تا صاحب پیج کیفیت را با چشم خودش ببیند.

اجرا:  .venv/bin/python tools/local_llm_check.py [--url http://127.0.0.1:11434/v1] [--model qwen2.5:3b]
"""
import argparse
import os
import sys
import time

import httpx

SAMPLES = ["سلام، قیمت آیفون ۱۳ پرو چنده؟", "قسطی هم میدید؟", "آدرس مغازه کجاست؟"]
SYSTEM = ("تو دستیار فروشگاه موبایل استوک‌لند هستی. کوتاه و مؤدب فارسی جواب بده. "
          "هیچ قیمت، آدرس یا سیاستی از خودت نساز؛ اگر نمی‌دانی بگو همکار جواب می‌دهد.")


def mem_gb() -> float:
    try:
        with open("/proc/meminfo") as f:
            info = {k: int(v.split()[0]) for k, v in (line.split(":", 1) for line in f)}
        return info.get("MemAvailable", 0) / 1024 / 1024
    except OSError:
        return 0.0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("CUSTOM_AI_BASE_URL") or "http://127.0.0.1:11434/v1")
    ap.add_argument("--model", default="")
    a = ap.parse_args(argv)
    if not a.url.startswith(("http://127.0.0.1", "http://localhost")):
        print("❌ این ابزار فقط سرویس محلی همین سرور را می‌سنجد (127.0.0.1 یا localhost).")
        return 2
    ram, cpus = mem_gb(), os.cpu_count() or 1
    print(f"🖥 رم آزاد: {ram:.1f} گیگ · هسته‌ها: {cpus}")
    if ram < 3:
        print("⚠️ برای مدل‌های ۱.۵ تا ۳ میلیارد پارامتری دست‌کم ۳ گیگ رم آزاد لازم است؛ این سرور کم دارد.")
    url = a.url.rstrip("/")
    try:
        with httpx.Client(timeout=10, trust_env=False) as h:
            models = [m["id"] for m in h.get(url + "/models").json().get("data", [])]
    except Exception as e:  # noqa: BLE001
        print(f"❌ سرویس محلی در {url} جواب نداد ({type(e).__name__}). اول طبق docs/LOCAL_LLM.md راهش بیندازید.")
        return 1
    print("📦 مدل‌ها: " + ("، ".join(models) or "هیچ"))
    model = a.model or (models[0] if models else "")
    if not model:
        print("❌ مدلی نصب نیست.")
        return 1
    slow = 0
    with httpx.Client(timeout=120, trust_env=False) as h:
        for q in SAMPLES:
            t = time.time()
            try:
                r = h.post(url + "/chat/completions", json={"model": model, "max_tokens": 150, "temperature": 0.3,
                                                             "messages": [{"role": "system", "content": SYSTEM},
                                                                          {"role": "user", "content": q}]})
                r.raise_for_status()
                ans = (r.json()["choices"][0]["message"]["content"] or "").strip()
            except Exception as e:  # noqa: BLE001
                ans = f"❌ {type(e).__name__}: {e}"
            dt = time.time() - t
            slow += dt > 15
            print(f"\n❓ {q}\n⏱ {dt:.1f} ثانیه\n💬 {ans[:400]}")
    print("\n" + ("⚠️ جواب‌ها برای چت مشتری کند است (بیش از ۱۵ ثانیه)؛ مدل کوچک‌تر یا سرور قوی‌تر لازم است."
                  if slow else "✅ سرعت قابل قبول است. اگر کیفیت جواب‌ها را هم پسندیدید، از پنل ← هوش مصنوعی ← "
                               "«سرویس دلخواه» را با همین آدرس و مدل انتخاب کنید."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
