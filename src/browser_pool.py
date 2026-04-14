"""Единый Playwright-браузер для всех модулей."""
import os
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright

from src.config import settings, log

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


def _session_path(chat_id: str | int) -> str:
    return os.path.join(settings.sessions_dir, str(chat_id), "storage_state.json")


async def get_context(chat_id: str | int) -> BrowserContext:
    """Контекст браузера с per-user storage_state.

    Загружает `sessions_dir/{chat_id}/storage_state.json` если файл есть.
    Сохранение делает `save_context()` или `auth.ensure_logged_in()`.
    """
    browser = await get_browser()
    path = _session_path(chat_id)
    storage_state = path if os.path.exists(path) else None
    context = await browser.new_context(
        storage_state=storage_state,
        user_agent=USER_AGENT,
        viewport={"width": 1920, "height": 1080},
    )
    return context


async def save_context(context: BrowserContext, chat_id: str | int) -> str:
    path = _session_path(chat_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    await context.storage_state(path=path)
    return path


async def close():
    global _browser, _playwright
    if _browser and _browser.is_connected():
        await _browser.close()
    _browser = None
    if _playwright is not None:
        await _playwright.stop()
        _playwright = None
