from functools import cached_property
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables (or a local .env file)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Instagram (Instagram API with Instagram Login)
    ig_access_token: str
    ig_user_id: str
    ig_app_secret: str
    ig_verify_token: str
    ig_api_version: str = "v23.0"
    ig_graph_url: str = "https://graph.instagram.com"

    # Telegram
    telegram_bot_token: str
    telegram_admin_chat_id: int = 0
    telegram_webhook_secret: str

    # Claude
    anthropic_api_key: str = ""  # empty = no AI drafts; you write replies yourself
    claude_model: str = "claude-opus-5-5"

    # Deployment
    public_url: str = ""  # e.g. https://my-bot.up.railway.app – used to register the Telegram webhook
    data_dir: Path = Path("data")
    voice_file: Path = Path("voice.md")
    dm_window_hours: int = 24

    @field_validator("telegram_admin_chat_id", mode="before")
    @classmethod
    def _empty_is_zero(cls, v):
        return 0 if v in ("", None) else v

    @cached_property
    def voice(self) -> str:
        try:
            return self.voice_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""
