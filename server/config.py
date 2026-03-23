from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    chatgpt_url: str = "https://chat.openai.com"
    chatgpt_project_url: str | None = None
    browser_headless: bool = False
    session_path: Path = Path("auth/storage_state.json")
    timeout: int = Field(default=60, ge=1)
    log_level: str = "INFO"


def load_settings() -> Settings:
    return Settings()


def chatgpt_entry_url(settings: Settings) -> str:
    """URL opened before each prompt: mirror project link or default ChatGPT entry."""
    explicit = (settings.chatgpt_project_url or "").strip()
    return explicit if explicit else settings.chatgpt_url
