import os
from typing import Tuple

from playwright.async_api import async_playwright, Browser

from src.config import settings, log
from src.models import Vacancy
from src.scraper import SELECTORS

_browser: Browser = None


async def _get_browser() -> Browser:
    global _browser
    if _browser is None or not _browser.is_connected():
        pw = await async_playwright().start()
        from src.scraper import _detect_chrome_channel
        channel = _detect_chrome_channel()
        launch_kwargs = dict(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        if channel:
            launch_kwargs["channel"] = channel
        _browser = await pw.chromium.launch(**launch_kwargs)
    return _browser


async def _check_auth(page) -> bool:
    try:
        # Проверить наличие элемента авторизованного пользователя
        el = await page.query_selector(
            "[data-qa='mainmenu_myResumes'], "
            ".applicant-sidebar, "
            "a[href*='applicant']"
        )
        return el is not None
    except Exception:
        return False


async def _reauth(page):
    log.info("Session expired, re-authenticating...")
    await page.goto("https://rabota.by/account/login", wait_until="networkidle")

    email_input = await page.wait_for_selector(
        "input[name='login'], input[type='email'], input[name='email']",
        timeout=10000,
    )
    await email_input.fill(settings.rabota_email)

    password_input = await page.wait_for_selector(
        "input[name='password'], input[type='password']",
        timeout=5000,
    )
    await password_input.fill(settings.rabota_password)

    submit = await page.wait_for_selector(
        "button[type='submit'], button[data-qa='account-login-submit']",
        timeout=5000,
    )
    await submit.click()
    await page.wait_for_load_state("networkidle")

    # Сохранить обновлённую сессию
    await page.context.storage_state(path=settings.session_path)
    log.info("Re-authentication complete, session saved")


async def apply_to_vacancy(vacancy: Vacancy) -> Tuple[bool, str]:
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
        await page.goto(vacancy.url, wait_until="networkidle", timeout=30000)

        # Проверить авторизацию
        if not await _check_auth(page):
            await _reauth(page)
            await page.goto(vacancy.url, wait_until="networkidle", timeout=30000)

        # Проверить что вакансия не закрыта
        page_text = await page.inner_text("body")
        if "вакансия в архиве" in page_text.lower() or "вакансия закрыта" in page_text.lower():
            return False, "Вакансия закрыта"

        if "вы уже откликнулись" in page_text.lower() or "отклик уже отправлен" in page_text.lower():
            return False, "Уже откликались"

        # Найти кнопку отклика
        apply_btn = await page.query_selector(SELECTORS["apply_button"])
        if not apply_btn:
            # Fallback: любая кнопка с текстом "Откликнуться"
            apply_btn = await page.query_selector("button:has-text('Откликнуться')")

        if not apply_btn:
            return False, "Кнопка отклика не найдена"

        await apply_btn.click()
        await page.wait_for_timeout(2000)

        # Проверить: появилось ли модальное окно с формой
        cover_textarea = await page.query_selector(
            "textarea[name='letter'], textarea[data-qa='vacancy-response-popup-form-letter-input']"
        )
        if cover_textarea and vacancy.cover_letter:
            await cover_textarea.fill(vacancy.cover_letter)

        # Нажать финальную кнопку отправки (в модалке)
        send_btn = await page.query_selector(
            "button[data-qa='vacancy-response-submit-popup'], "
            "button:has-text('Отправить'), "
            "button:has-text('Откликнуться')"
        )
        if send_btn:
            await send_btn.click()
            await page.wait_for_timeout(3000)

        # Проверить подтверждение
        confirmation = await page.query_selector(
            "[data-qa='vacancy-response-popup-sent'], "
            ":has-text('Отклик отправлен')"
        )

        # Скриншот для лога
        screenshots_dir = "/data/screenshots"
        os.makedirs(screenshots_dir, exist_ok=True)
        await page.screenshot(path=f"{screenshots_dir}/{vacancy.external_id}.png")

        if confirmation:
            log.info(f"Applied to: {vacancy.title}")
            return True, "OK"

        # Проверить капчу
        captcha = await page.query_selector(
            "iframe[src*='captcha'], div[class*='captcha'], .g-recaptcha"
        )
        if captcha:
            return False, f"Капча! Откликнись вручную: {vacancy.url}"

        # Если не уверены — считаем успехом (кнопка была нажата)
        return True, "OK (unconfirmed)"

    except Exception as e:
        log.error(f"Apply error for {vacancy.url}: {e}")

        # Скриншот ошибки
        try:
            screenshots_dir = "/data/screenshots"
            os.makedirs(screenshots_dir, exist_ok=True)
            await page.screenshot(path=f"{screenshots_dir}/{vacancy.external_id}_error.png")
        except Exception:
            pass

        return False, str(e)
    finally:
        await context.close()
