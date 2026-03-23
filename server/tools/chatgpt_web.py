from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from server.browser.playwright_client import ChatGPTAutomationError, run_chatgpt_research
from server.config import Settings, load_settings
from server.logger import get_logger

log = get_logger(__name__)

_SUMMARY_MAX = 500


class ChatGPTResearchOutput(BaseModel):
    summary: str = Field(description="Short preview of the reply, or combined error context for humans")
    full_response: str = Field(default="", description="Full assistant reply when status is ok")
    status: Literal["ok", "error"] = Field(description="Whether automation succeeded")
    execution_time: float = Field(description="Wall time in seconds for the tool run")
    error_code: str | None = Field(
        default=None,
        description="Machine-readable error code when status is error; null when ok",
    )
    error_detail: str | None = Field(
        default=None,
        description="Full error message when status is error; null when ok",
    )


CHATGPT_RESEARCH_OUTPUT_SCHEMA: dict[str, Any] = ChatGPTResearchOutput.model_json_schema()


def _make_summary(full: str) -> str:
    text = " ".join(full.split())
    if len(text) <= _SUMMARY_MAX:
        return text
    return text[: _SUMMARY_MAX].rstrip() + "…"


def _error_payload(code: str, detail: str, elapsed: float) -> dict[str, Any]:
    return ChatGPTResearchOutput(
        summary=f"[{code}] {detail}",
        full_response="",
        status="error",
        execution_time=round(elapsed, 3),
        error_code=code,
        error_detail=detail,
    ).model_dump()


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
            error_code=None,
            error_detail=None,
        )
        log.info("chatgpt_web_research ok in %.3fs", elapsed)
        return out.model_dump()
    except ChatGPTAutomationError as e:
        elapsed = time.perf_counter() - t0
        log.warning("chatgpt_web_research error %s: %s", e.code, e.detail)
        return _error_payload(e.code, e.detail, elapsed)
    except Exception as e:
        elapsed = time.perf_counter() - t0
        log.exception("chatgpt_web_research unexpected failure")
        return _error_payload("unknown", str(e), elapsed)
