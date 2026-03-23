from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from server.browser.playwright_client import ChatGPTAutomationError, run_chatgpt_research
from server.config import Settings, load_settings
from server.logger import get_logger

log = get_logger(__name__)

_SUMMARY_MAX = 500


class ChatGPTResearchOutput(BaseModel):
    summary: str = Field(description="Short preview or error summary")
    full_response: str = Field(default="", description="Full assistant reply when successful")
    status: str = Field(description='"ok" or "error"')
    execution_time: float = Field(description="Wall time in seconds for the tool run")


def _make_summary(full: str) -> str:
    text = " ".join(full.split())
    if len(text) <= _SUMMARY_MAX:
        return text
    return text[: _SUMMARY_MAX].rstrip() + "…"


async def chatgpt_web_research(
    prompt: str,
    timeout: int | None = None,
    *,
    _settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Send a prompt to ChatGPT Web via browser automation and return the assistant reply.

    Requires a saved Playwright session at SESSION_PATH (see README). Optional timeout
    overrides the default TIMEOUT (seconds).
    """
    settings = _settings or load_settings()
    deadline_s = timeout if timeout is not None else settings.timeout
    t0 = time.perf_counter()
    log.info("chatgpt_web_research start timeout=%s", deadline_s)

    try:
        result = await run_chatgpt_research(settings, prompt, deadline_s)
        elapsed = time.perf_counter() - t0
        out = ChatGPTResearchOutput(
            summary=_make_summary(result.full_response),
            full_response=result.full_response,
            status="ok",
            execution_time=round(elapsed, 3),
        )
        log.info("chatgpt_web_research ok in %.3fs", elapsed)
        return out.model_dump()
    except ChatGPTAutomationError as e:
        elapsed = time.perf_counter() - t0
        log.warning("chatgpt_web_research error %s: %s", e.code, e.detail)
        return ChatGPTResearchOutput(
            summary=f"[{e.code}] {e.detail}",
            full_response="",
            status="error",
            execution_time=round(elapsed, 3),
        ).model_dump()
    except Exception as e:
        elapsed = time.perf_counter() - t0
        log.exception("chatgpt_web_research unexpected failure")
        return ChatGPTResearchOutput(
            summary=f"[unknown] {e}",
            full_response="",
            status="error",
            execution_time=round(elapsed, 3),
        ).model_dump()
