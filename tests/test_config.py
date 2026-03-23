from pathlib import Path

from server.config import Settings, chatgpt_entry_url


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


def test_chatgpt_project_url_overrides_entry(monkeypatch):
    monkeypatch.setenv("CHATGPT_URL", "https://chat.openai.com")
    monkeypatch.setenv("CHATGPT_PROJECT_URL", "https://chatgpt.com/project/mirror-abc")
    s = Settings()
    assert chatgpt_entry_url(s) == "https://chatgpt.com/project/mirror-abc"


def test_chatgpt_project_url_whitespace_ignored(monkeypatch):
    monkeypatch.setenv("CHATGPT_URL", "https://fallback.example")
    monkeypatch.setenv("CHATGPT_PROJECT_URL", "   ")
    s = Settings()
    assert chatgpt_entry_url(s) == "https://fallback.example"
