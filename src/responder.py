import os
from typing import Tuple

from playwright.async_api import async_playwright, Browser

from src.config import settings, log
from src.inbox import INBOX_SELECTORS

_browser: Browser = None


async def _get_browser() -> Browser:
    global _browser
    if _browser is None or not _browser.is_connected():
        pw = await async_playwright().start()
        from src.scraper import _detect_chrome_channel
        channel = _detect_chrome_channel()
        launch_kwargs = dict(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        if channel:
            launch_kwargs["channel"] = channel
        _browser = await pw.chromium.launch(**launch_kwargs)
    return _browser


async def send_reply(conversation_id: str, text: str) -> Tuple[bool, str]:
    browser = await _get_browser()
    storage_state = settings.session_path if os.path.exists(settings.session_path) else None

    context = await browser.new_context(
        storage_state=storage_state,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    )
    page = await context.new_page()

    try:
        await page.goto(
            f"https://rabota.by/applicant/responses/{conversation_id}",
            wait_until="networkidle",
            timeout=30000,
        )

        # Проверить авторизацию
        auth_el = await page.query_selector(
            "[data-qa='mainmenu_myResumes'], .applicant-sidebar"
        )
        if not auth_el:
            from src.applier import _reauth
            await _reauth(page)
            await page.goto(
                f"https://rabota.by/applicant/responses/{conversation_id}",
                wait_until="networkidle",
            )

        # Найти поле ввода ответа
        textarea = await page.query_selector(
            INBOX_SELECTORS.get("reply_textarea", "")
            + ", textarea[name='text'], textarea[data-qa='message-input']"
            + ", div[contenteditable='true']"
            + ", textarea"
        )

        if not textarea:
            return False, "Поле ввода не найдено"

        tag = await textarea.evaluate("el => el.tagName.toLowerCase()")
        if tag == "div":
            # contenteditable div
            await textarea.click()
            await textarea.type(text, delay=30)
        else:
            await textarea.fill(text)

        await page.wait_for_timeout(500)

        # Нажать «Отправить»
        send_btn = await page.query_selector(
            INBOX_SELECTORS.get("reply_send_button", "")
            + ", button[data-qa='message-submit'], button:has-text('Отправить')"
            + ", button[type='submit']"
        )

        if not send_btn:
            return False, "Кнопка отправки не найдена"

        await send_btn.click()
        await page.wait_for_timeout(3000)

        # Проверить что сообщение появилось
        page_text = await page.inner_text("body")
        if text[:50] in page_text:
            log.info(f"Reply sent to conversation {conversation_id}")
            # Сохранить обновлённую сессию
            await context.storage_state(path=settings.session_path)
            return True, "OK"

        return True, "OK (unconfirmed)"

    except Exception as e:
        log.error(f"Reply error for {conversation_id}: {e}")
        return False, str(e)
    finally:
        await context.close()
