from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Locator
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import Page

from server.browser.session import ensure_browser_context, shutdown_reused_browser
from server.config import Settings, chatgpt_entry_url
from server.logger import get_logger

log = get_logger(__name__)

# Serializes automation: one shared browser context, one active page at a time.
_RESEARCH_LOCK = asyncio.Lock()


class ChatGPTAutomationError(Exception):
    __slots__ = ("code", "detail")

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True, slots=True)
class ResearchResult:
    full_response: str


_ASSISTANT_SELECTORS = (
    '[data-message-author-role="assistant"]',
    "[data-testid='conversation-turn-assistant']",
)


async def _first_visible(locator: Locator, timeout_ms: int = 8000) -> Locator | None:
    try:
        target = locator.first
        await target.wait_for(state="visible", timeout=timeout_ms)
        return target
    except PlaywrightTimeoutError:
        return None


async def _locate_composer(page: Page) -> Locator:
    """
    Prefer stable ids and main-landmark scoped controls; avoid unscoped contenteditable
    (matches sidebar or other regions).
    """
    # Strongest: composer id on textarea or ProseMirror host
    for sel in ("#prompt-textarea", "textarea#prompt-textarea", "div#prompt-textarea"):
        got = await _first_visible(page.locator(sel), 8000)
        if got is not None:
            return got

    main = page.locator("main")
    if await main.count() > 0:
        for sel in (
            'textarea[data-id="root"]',
            'textarea[placeholder*="Message"]',
            'textarea[placeholder*="message"]',
            'textarea[placeholder*="Ask"]',
            'textarea[placeholder*="ask"]',
        ):
            got = await _first_visible(main.locator(sel), 6000)
            if got is not None:
                return got

        ce = main.locator('div[contenteditable="true"][data-placeholder]')
        got = await _first_visible(ce, 6000)
        if got is not None:
            return got

        tb = main.get_by_role("textbox")
        if await tb.count() > 0:
            try:
                last = tb.last
                await last.wait_for(state="visible", timeout=6000)
                return last
            except PlaywrightTimeoutError:
                pass

    # Composer often lives in a form at the bottom; avoid picking unrelated editables
    for scope_sel in ("form", "footer", "[data-testid='composer-trailing-actions']"):
        scope = page.locator(scope_sel).last
        if await scope.count() == 0:
            continue
        inner = scope.locator("textarea").or_(scope.locator('div[contenteditable="true"]'))
        got = await _first_visible(inner, 4000)
        if got is not None:
            return got

    raise ChatGPTAutomationError(
        "selector_changed",
        "No visible prompt composer matched known selectors; ChatGPT UI may have changed.",
    )


async def _wait_stable_text(locator: Locator, interval_s: float, stable_rounds: int, max_wait_s: float) -> str:
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


def _looks_like_login(url: str) -> bool:
    u = url.lower()
    return "login" in u or "auth.openai.com" in u or "auth.chatgpt.com" in u


async def _research_on_page(
    page: Page,
    settings: Settings,
    prompt: str,
    timeout_ms: int,
    timeout_s: int,
) -> ResearchResult:
    try:
        entry = chatgpt_entry_url(settings)
        log.debug("Navigating to %s", entry)
        await page.goto(
            entry,
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


async def run_chatgpt_research(settings: Settings, prompt: str, timeout_s: int) -> ResearchResult:
    timeout_ms = max(1000, int(timeout_s * 1000))
    if not prompt.strip():
        raise ChatGPTAutomationError("invalid_prompt", "Prompt is empty.")

    async with _RESEARCH_LOCK:
        try:
            context = await ensure_browser_context(settings)
            page = await context.new_page()
            try:
                return await _research_on_page(page, settings, prompt, timeout_ms, timeout_s)
            finally:
                await page.close()
        except ChatGPTAutomationError:
            raise
        except PlaywrightError as e:
            raise ChatGPTAutomationError("browser_crash", str(e)) from e
        except Exception as e:
            raise ChatGPTAutomationError("unknown", str(e)) from e


async def shutdown_research_browser() -> None:
    """Close the shared Playwright browser and context (e.g. after integration tests)."""
    async with _RESEARCH_LOCK:
        await shutdown_reused_browser()
