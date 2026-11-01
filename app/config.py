"""تنظیمات از متغیرهای محیطی (.env). هیچ رازی در کد نیست."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

IG_APP_SECRET = os.environ.get("IG_APP_SECRET", "")
IG_VERIFY_TOKEN = os.environ.get("IG_VERIFY_TOKEN", "")
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
IG_USER_ID = os.environ.get("IG_USER_ID", "")
GRAPH_VERSION = os.environ.get("GRAPH_VERSION", "v21.0")
DB_PATH = os.environ.get("DB_PATH", str(ROOT / "data" / "bot.db"))
# تأخیر تصادفی پیش از هر ارسال (ثانیه) برای طبیعی‌تر بودن و رعایت نرخ
SEND_DELAY_MIN = float(os.environ.get("SEND_DELAY_MIN", "2"))
SEND_DELAY_MAX = float(os.environ.get("SEND_DELAY_MAX", "8"))

# پاسخ هوشمند
# سرویس پیش‌فرض؛ از پنل هم عوض می‌شود. کلیدها فقط اینجا خوانده می‌شوند و هرگز به پنل نمی‌روند.
AI_PROVIDER = os.environ.get("AI_PROVIDER", "anthropic")
AI_MODEL = os.environ.get("AI_MODEL", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
# هر سرویس سازگار با OpenAI (مثلاً واسط‌های داخلی با پرداخت ریالی، یا Ollama)
CUSTOM_AI_BASE_URL = os.environ.get("CUSTOM_AI_BASE_URL", "")
CUSTOM_AI_API_KEY = os.environ.get("CUSTOM_AI_API_KEY", "")
CUSTOM_AI_NAME = os.environ.get("CUSTOM_AI_NAME", "")

# همگام‌سازی محصول از ووکامرس: فقط اگر Store API عمومی سایت بسته باشد لازم است (کلید فقط‌خواندنی)
WC_CONSUMER_KEY = os.environ.get("WC_CONSUMER_KEY", "")
WC_CONSUMER_SECRET = os.environ.get("WC_CONSUMER_SECRET", "")

# داده‌ی ربات تلگرام (نیت‌ها، فهرست کالا، متن بخش‌ها) که موتور فهم مشترک از آن می‌خواند
TG_DATA_DIR = os.environ.get("TG_DATA_DIR", str(ROOT / "data" / "telegram"))

# پنل
PANEL_PASSWORD = os.environ.get("PANEL_PASSWORD", "")
SESSION_TTL = int(os.environ.get("SESSION_TTL", str(30 * 86400)))
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1") == "1"
WEB_DIST = os.environ.get("WEB_DIST", str(ROOT / "web" / "dist"))

# اعلان پوش (با `python -m app.push --gen` بسازید)
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:admin@stland.ir")
