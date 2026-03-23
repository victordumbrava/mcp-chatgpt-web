from pathlib import Path

from server.config import Settings


def test_settings_defaults(monkeypatch):
    monkeypatch.delenv("CHATGPT_URL", raising=False)
    monkeypatch.delenv("TIMEOUT", raising=False)
    s = Settings()
    assert "chat.openai.com" in s.chatgpt_url
    assert s.timeout == 60
    assert isinstance(s.session_path, Path)


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("CHATGPT_URL", "https://example.com")
    monkeypatch.setenv("TIMEOUT", "120")
    monkeypatch.setenv("BROWSER_HEADLESS", "true")
    s = Settings()
    assert s.chatgpt_url == "https://example.com"
    assert s.timeout == 120
    assert s.browser_headless is True
