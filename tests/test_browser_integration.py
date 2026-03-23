"""
Opt-in live browser tests against ChatGPT Web.

Requires: pip install playwright && playwright install chromium
          valid auth/storage_state.json (or SESSION_PATH)
          RUN_BROWSER_INTEGRATION=1
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from server.browser.playwright_client import run_chatgpt_research, shutdown_research_browser
from server.config import Settings

pytestmark = [pytest.mark.browser, pytest.mark.asyncio]


def _integration_enabled() -> bool:
    return os.environ.get("RUN_BROWSER_INTEGRATION", "").strip().lower() in ("1", "true", "yes")


def _session_path() -> Path:
    raw = os.environ.get("SESSION_PATH", "auth/storage_state.json")
    return Path(raw).expanduser().resolve()


@pytest.mark.skipif(not _integration_enabled(), reason="Set RUN_BROWSER_INTEGRATION=1 to run")
@pytest.mark.skipif(not _session_path().is_file(), reason="Requires existing session storage_state.json")
async def test_chatgpt_web_short_deterministic_reply():
    settings = Settings()
    timeout_s = min(int(os.environ.get("BROWSER_TEST_TIMEOUT", "120")), settings.timeout)
    try:
        result = await run_chatgpt_research(
            settings,
            "Reply with the single word PONG only. No punctuation or other words.",
            timeout_s,
        )
    finally:
        await shutdown_research_browser()

    text = result.full_response.upper()
    assert "PONG" in text, f"Unexpected assistant text: {result.full_response!r}"
