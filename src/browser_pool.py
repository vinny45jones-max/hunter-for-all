"""Единый Playwright-браузер для всех модулей."""
import os
from typing import Optional

from playwright.async_api import async_playwright, Browser, Playwright

from src.config import log

_browser: Optional[Browser] = None
_playwright: Optional[Playwright] = None

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _detect_chrome_channel() -> Optional[str]:
    if os.name == "nt":
        for path in [
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
        ]:
            if os.path.exists(path):
                return "chrome"
    return None


async def get_browser() -> Browser:
    global _browser, _playwright
    if _browser is None or not _browser.is_connected():
        if _playwright is None:
            _playwright = await async_playwright().start()
        channel = _detect_chrome_channel()
        launch_kwargs = dict(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        if channel:
            launch_kwargs["channel"] = channel
            log.info(f"Browser pool: using system Chrome (channel={channel})")
        _browser = await _playwright.chromium.launch(**launch_kwargs)
    return _browser


async def close():
    global _browser, _playwright
    if _browser and _browser.is_connected():
        await _browser.close()
    _browser = None
    if _playwright is not None:
        await _playwright.stop()
        _playwright = None
