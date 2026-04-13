import asyncio
import os
import random
import re
from typing import List, Optional
from urllib.parse import urljoin

from playwright.async_api import async_playwright, Browser, Page, Playwright

from src.config import settings, log
from src.models import Vacancy

# CSS-селекторы rabota.by — проверены debug_selectors.py на live-сайте
SELECTORS = {
    "vacancy_card": "div[data-qa='vacancy-serp__vacancy'], div.vacancy-card, div[class*='serp-item']",
    "vacancy_title": "a[data-qa='serp-item__title'], a.vacancy-card__title, h3 a",
    "vacancy_company": "a[data-qa='vacancy-serp__vacancy-employer'], span.vacancy-card__company",
    "vacancy_salary": "[data-qa='vacancy-serp__vacancy-compensation'], div[class*='compensation'], span[class*='compensation']",
    "vacancy_city": "[data-qa='vacancy-serp__vacancy-address'], span.vacancy-card__city",
    "next_page": "a[data-qa='pager-next'], a.pagination__next",
    "full_description": "div[data-qa='vacancy-description'], div.vacancy-description",
    "apply_button": "button[data-qa='vacancy-response-link-top'], button.vacancy-apply-button",
}

BASE_URL = "https://rabota.by"

_browser: Optional[Browser] = None
_playwright: Optional[Playwright] = None


def _detect_chrome_channel() -> Optional[str]:
    """На Windows/macOS используем системный Chrome, на Linux (Docker) — Playwright Chromium."""
    if os.name == "nt":
        # Windows: проверить наличие Chrome
        for path in [
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
        ]:
            if os.path.exists(path):
                return "chrome"
    return None  # Linux/Docker — используем Playwright Chromium


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
            log.info(f"Using system Chrome (channel={channel})")
        _browser = await _playwright.chromium.launch(**launch_kwargs)
    return _browser


async def _random_delay(min_sec: float = 2.0, max_sec: float = 5.0):
    await asyncio.sleep(random.uniform(min_sec, max_sec))


def _extract_external_id(url: str) -> Optional[str]:
    match = re.search(r"/vakansiya/(\d+)", url)
    if match:
        return match.group(1)
    match = re.search(r"/vacancy/(\d+)", url)
    if match:
        return match.group(1)
    match = re.search(r"(\d{6,})", url)
    if match:
        return match.group(1)
    return None


async def parse_search_results(keyword: str, max_pages: int = None) -> List[Vacancy]:
    if max_pages is None:
        max_pages = settings.max_pages

    browser = await get_browser()
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1920, "height": 1080},
    )
    page = await context.new_page()
    vacancies: List[Vacancy] = []

    try:
        search_url = f"{BASE_URL}/search/vacancy?text={keyword}&area={settings.search_area_id}"
        log.info(f"Scraping: {keyword} -> {search_url}")

        for page_num in range(max_pages):
            url = f"{search_url}&page={page_num}"
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await _random_delay(1.5, 3.0)

            cards = await page.query_selector_all(SELECTORS["vacancy_card"])
            if not cards:
                log.info(f"No cards found on page {page_num} for '{keyword}'")
                break

            for card in cards:
                try:
                    title_el = await card.query_selector(SELECTORS["vacancy_title"])
                    if not title_el:
                        continue

                    title = (await title_el.inner_text()).strip()
                    href = await title_el.get_attribute("href")
                    if not href:
                        continue
                    url_full = urljoin(BASE_URL, href)

                    external_id = _extract_external_id(url_full)
                    if not external_id:
                        continue

                    company_el = await card.query_selector(SELECTORS["vacancy_company"])
                    company = (await company_el.inner_text()).strip() if company_el else None

                    salary_el = await card.query_selector(SELECTORS["vacancy_salary"])
                    salary = None
                    if salary_el:
                        raw_salary = (await salary_el.inner_text()).strip()
                        # div[class*='compensation'] захватывает и "Опыт ..." — берём первую строку
                        first_line = raw_salary.split("\n")[0].strip() if raw_salary else ""
                        # Отсечь фейковую зарплату: если текст только "Опыт ..." — это не зарплата
                        if first_line and not first_line.startswith("Опыт"):
                            salary = first_line

                    city_el = await card.query_selector(SELECTORS["vacancy_city"])
                    city = (await city_el.inner_text()).strip() if city_el else None

                    vacancies.append(Vacancy(
                        external_id=external_id,
                        url=url_full,
                        title=title,
                        company=company,
                        salary=salary,
                        city=city,
                    ))
                except Exception as e:
                    log.warning(f"Error parsing card: {e}")
                    continue

            # Пагинация: проверяем есть ли следующая страница
            if page_num < max_pages - 1:
                next_btn = await page.query_selector(SELECTORS["next_page"])
                if not next_btn:
                    log.info(f"No next page after page {page_num + 1}")
                    break
                await _random_delay()

        log.info(f"Found {len(vacancies)} vacancies for '{keyword}'")
    except Exception as e:
        log.error(f"Scraper error for '{keyword}': {e}")
    finally:
        await context.close()

    return vacancies


async def get_full_description(url: str) -> Optional[str]:
    browser = await get_browser()
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    )
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await _random_delay(1.0, 2.5)

        desc_el = await page.query_selector(SELECTORS["full_description"])
        if desc_el:
            text = await desc_el.inner_text()
            return text.strip()

        # Fallback: собрать весь текст из body
        body = await page.query_selector("body")
        if body:
            text = await body.inner_text()
            # Обрезать до разумного размера
            return text[:5000].strip()
        return None
    except Exception as e:
        log.error(f"Error getting description for {url}: {e}")
        return None
    finally:
        await context.close()


async def parse_all_keywords() -> List[Vacancy]:
    all_vacancies: List[Vacancy] = []
    seen_ids = set()

    for keyword in settings.search_keywords:
        vacancies = await parse_search_results(keyword)
        for v in vacancies:
            if v.external_id not in seen_ids:
                seen_ids.add(v.external_id)
                all_vacancies.append(v)
        await _random_delay(3.0, 6.0)

    log.info(f"Total unique vacancies: {len(all_vacancies)}")
    return all_vacancies


async def close():
    global _browser, _playwright
    if _browser and _browser.is_connected():
        await _browser.close()
    _browser = None
    if _playwright is not None:
        await _playwright.stop()
        _playwright = None
