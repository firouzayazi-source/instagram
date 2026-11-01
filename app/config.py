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
