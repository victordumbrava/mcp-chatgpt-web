import time

from server.browser.session import browser_context_fingerprint
from server.config import Settings


def test_fingerprint_missing_session_file(tmp_path, monkeypatch):
    missing = tmp_path / "missing.json"
    monkeypatch.setenv("SESSION_PATH", str(missing))
    s = Settings()
    fp = browser_context_fingerprint(s)
    assert fp[2] == -1
    assert fp[1] == str(missing.resolve())


def test_fingerprint_changes_when_storage_file_touched(tmp_path, monkeypatch):
    path = tmp_path / "storage_state.json"
    path.write_text("{}")
    monkeypatch.setenv("SESSION_PATH", str(path))
    s = Settings()
    first = browser_context_fingerprint(s)
    time.sleep(0.05)
    path.write_text('{"cookies":[]}')
    second = browser_context_fingerprint(s)
    assert first != second
