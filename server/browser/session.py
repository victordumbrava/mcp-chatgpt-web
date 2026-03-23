"""Reuse one Playwright browser + browser context across tool calls (serialized by caller)."""

from __future__ import annotations

from playwright.async_api import Browser
from playwright.async_api import BrowserContext
from playwright.async_api import Playwright
from playwright.async_api import async_playwright

from server.config import Settings
from server.logger import get_logger

log = get_logger(__name__)

_playwright: Playwright | None = None
_browser: Browser | None = None
_context: BrowserContext | None = None
_fingerprint: tuple[bool, str, int] | None = None


def browser_context_fingerprint(settings: Settings) -> tuple[bool, str, int]:
    """Stable tuple used to decide whether the shared context must be recreated."""
    path = settings.session_path.resolve()
    if path.is_file():
        return (settings.browser_headless, str(path), int(path.stat().st_mtime_ns))
    return (settings.browser_headless, str(path), -1)


async def _teardown_unlocked() -> None:
    global _playwright, _browser, _context, _fingerprint
    if _context is not None:
        try:
            await _context.close()
        except Exception:
            log.exception("Error closing browser context")
        _context = None
    if _browser is not None:
        try:
            await _browser.close()
        except Exception:
            log.exception("Error closing browser")
        _browser = None
    if _playwright is not None:
        try:
            await _playwright.stop()
        except Exception:
            log.exception("Error stopping Playwright")
        _playwright = None
    _fingerprint = None


async def ensure_browser_context(settings: Settings) -> BrowserContext:
    """
    Return a shared BrowserContext, recreating it if headless, session path, or session file changed.

    Must be called under the same asyncio lock that serializes research runs (see playwright_client).
    """
    global _playwright, _browser, _context, _fingerprint
    fp = browser_context_fingerprint(settings)
    if _context is not None and _fingerprint == fp:
        return _context

    await _teardown_unlocked()
    log.info("Starting Playwright (browser reuse) headless=%s", settings.browser_headless)
    try:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(headless=settings.browser_headless)
        ctx_kwargs: dict = {}
        if settings.session_path.is_file():
            ctx_kwargs["storage_state"] = str(settings.session_path)
            log.info("Loaded session from %s", settings.session_path)
        else:
            log.warning(
                "Session file missing at %s; log in once and save storage_state.json",
                settings.session_path,
            )
        _context = await _browser.new_context(**ctx_kwargs)
        _fingerprint = fp
        return _context
    except Exception:
        await _teardown_unlocked()
        raise


async def shutdown_reused_browser() -> None:
    """Close reused browser and Playwright (for tests or clean exit)."""
    await _teardown_unlocked()
