from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from server.config import Settings
from server.logger import get_logger

log = get_logger(__name__)


class ChatGPTAutomationError(Exception):
    __slots__ = ("code", "detail")

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True, slots=True)
class ResearchResult:
    full_response: str


_COMPOSER_SELECTORS = (
    "#prompt-textarea",
    "textarea[data-id='root']",
    "textarea[placeholder*='Message']",
    "textarea[placeholder*='message']",
    "div[contenteditable='true'][data-placeholder]",
    "div#prompt-textarea",
    "div[contenteditable='true']",
)

_ASSISTANT_SELECTORS = (
    '[data-message-author-role="assistant"]',
    "[data-testid='conversation-turn-assistant']",
)


async def _wait_stable_text(locator, interval_s: float, stable_rounds: int, max_wait_s: float) -> str:
    prev = ""
    stable = 0
    deadline = time.monotonic() + max_wait_s
    while time.monotonic() < deadline:
        try:
            txt = (await locator.inner_text()).strip()
        except PlaywrightError:
            txt = ""
        if txt and txt == prev:
            stable += 1
            if stable >= stable_rounds:
                return txt
        else:
            stable = 0
        prev = txt
        await asyncio.sleep(interval_s)
    return prev


async def _locate_composer(page):
    for sel in _COMPOSER_SELECTORS:
        loc = page.locator(sel).first
        try:
            await loc.wait_for(state="visible", timeout=8000)
            return loc
        except PlaywrightTimeoutError:
            continue
    raise ChatGPTAutomationError(
        "selector_changed",
        "No visible prompt composer matched known selectors; ChatGPT UI may have changed.",
    )


def _looks_like_login(url: str) -> bool:
    u = url.lower()
    return "login" in u or "auth.openai.com" in u or "auth.chatgpt.com" in u


async def run_chatgpt_research(settings: Settings, prompt: str, timeout_s: int) -> ResearchResult:
    timeout_ms = max(1000, int(timeout_s * 1000))
    if not prompt.strip():
        raise ChatGPTAutomationError("invalid_prompt", "Prompt is empty.")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=settings.browser_headless)
            try:
                ctx_kwargs: dict = {}
                if settings.session_path.is_file():
                    ctx_kwargs["storage_state"] = str(settings.session_path)
                    log.info("Using session storage at %s", settings.session_path)
                else:
                    log.warning(
                        "Session file missing at %s; log in once and save storage_state.json",
                        settings.session_path,
                    )

                context = await browser.new_context(**ctx_kwargs)
                page = await context.new_page()
                try:
                    await page.goto(
                        settings.chatgpt_url,
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    )
                except PlaywrightTimeoutError as e:
                    raise ChatGPTAutomationError("network_failure", f"Navigation timed out: {e}") from e
                except PlaywrightError as e:
                    raise ChatGPTAutomationError("network_failure", str(e)) from e

                if _looks_like_login(page.url):
                    raise ChatGPTAutomationError(
                        "session_expired",
                        "Redirected to login; refresh auth/storage_state.json after signing in.",
                    )

                composer = await _locate_composer(page)

                assistant_loc = None
                for sel in _ASSISTANT_SELECTORS:
                    al = page.locator(sel)
                    if await al.count() > 0:
                        assistant_loc = al
                        break
                if assistant_loc is None:
                    raise ChatGPTAutomationError(
                        "chatgpt_not_loaded",
                        "Assistant message container not found; page may not have loaded.",
                    )

                n_before = await assistant_loc.count()

                try:
                    await composer.click(timeout=5000)
                    await composer.fill("")
                    await composer.fill(prompt)
                except PlaywrightError as e:
                    raise ChatGPTAutomationError("selector_changed", f"Could not fill composer: {e}") from e

                await page.keyboard.press("Enter")

                try:
                    await page.wait_for_function(
                        """(before) => {
                            const sels = [
                                '[data-message-author-role="assistant"]',
                                "[data-testid='conversation-turn-assistant']"
                            ];
                            let n = 0;
                            for (const s of sels) {
                                n = Math.max(n, document.querySelectorAll(s).length);
                            }
                            return n > before;
                        }""",
                        arg=n_before,
                        timeout=timeout_ms,
                    )
                except PlaywrightTimeoutError as e:
                    raise ChatGPTAutomationError(
                        "timeout",
                        "Timed out waiting for a new assistant message after submit.",
                    ) from e

                last = assistant_loc.nth(await assistant_loc.count() - 1)

                stop = page.get_by_role("button", name=re.compile(r"stop", re.I))
                try:
                    if await stop.count() > 0:
                        await stop.first.wait_for(state="visible", timeout=5000)
                        await stop.first.wait_for(state="hidden", timeout=timeout_ms)
                except PlaywrightTimeoutError:
                    log.debug("Stop button did not appear or hide; using text stability wait")

                text = await _wait_stable_text(last, interval_s=0.5, stable_rounds=3, max_wait_s=float(timeout_s))
                if not text.strip():
                    raise ChatGPTAutomationError(
                        "selector_changed",
                        "Assistant message was empty after generation; selectors or timing may need adjustment.",
                    )

                return ResearchResult(full_response=text.strip())
            finally:
                await browser.close()
    except ChatGPTAutomationError:
        raise
    except PlaywrightError as e:
        raise ChatGPTAutomationError("browser_crash", str(e)) from e
    except Exception as e:
        raise ChatGPTAutomationError("unknown", str(e)) from e
