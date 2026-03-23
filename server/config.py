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
    browser_headless: bool = False
    session_path: Path = Path("auth/storage_state.json")
    timeout: int = Field(default=60, ge=1)
    log_level: str = "INFO"


def load_settings() -> Settings:
    return Settings()
