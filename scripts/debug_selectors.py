"""
Дебаг: открываем поиск rabota.by, делаем скриншот и дампим HTML-структуру.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()


async def main():
    from playwright.async_api import async_playwright
    from src.scraper import _detect_chrome_channel

    channel = _detect_chrome_channel()
    print(f"Chrome channel: {channel}")

    pw = await async_playwright().start()
    launch_kwargs = dict(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
    if channel:
        launch_kwargs["channel"] = channel

    browser = await pw.chromium.launch(**launch_kwargs)
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
    )
    page = await context.new_page()

    os.makedirs("data/debug", exist_ok=True)

    # ─── Тест 1: Главная ───
    print("\n[1] Главная rabota.by...")
    await page.goto("https://rabota.by", wait_until="networkidle", timeout=30000)
    await page.screenshot(path="data/debug/01_main.png", full_page=False)
    print(f"  Title: {await page.title()}")
    print(f"  URL: {page.url}")

    # ─── Тест 2: Поиск 'директор' — пробуем разные URL ───
    search_urls = [
        "https://rabota.by/search/vacancy?text=директор&area=16",
        "https://rabota.by/search/vacancy?text=директор&L_save_area=true&area=1002",
        "https://rabota.by/vakansii?query=директор&area=Минск",
        "https://rabota.by/search/vacancy?text=директор",
    ]

    for i, url in enumerate(search_urls, 2):
        print(f"\n[{i}] Пробуем: {url}")
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            await page.screenshot(path=f"data/debug/0{i}_search.png", full_page=False)
            print(f"  Final URL: {page.url}")
            print(f"  Title: {await page.title()}")

            # Попробовать разные селекторы для карточек вакансий
            selectors_to_try = [
                "div.vacancy-card",
                "div[data-qa='vacancy-serp__vacancy']",
                "div[class*='vacancy']",
                "div[class*='serp-item']",
                "div.serp-item",
                "a[data-qa='serp-item__title']",
                "a[class*='vacancy-name']",
                "[class*='vacancy-card']",
                "[data-qa*='vacancy']",
                "div[class*='HCompany']",
                ".bloko-gap",
            ]

            for sel in selectors_to_try:
                els = await page.query_selector_all(sel)
                if els:
                    print(f"  FOUND: '{sel}' -> {len(els)} elements")

            # Дампим первые 5000 символов body
            body_text = await page.inner_text("body")
            if body_text:
                preview = body_text[:2000].replace('\n', ' | ')
                print(f"  Body preview: {preview[:500]}...")

            # Дампим HTML структуру первого уровня
            html_sample = await page.evaluate("""
                () => {
                    const main = document.querySelector('main') || document.querySelector('[id*="content"]') || document.body;
                    const children = main.children;
                    let result = [];
                    for (let i = 0; i < Math.min(children.length, 20); i++) {
                        const el = children[i];
                        const classes = el.className ? '.' + el.className.split(' ').join('.') : '';
                        const dataQa = el.getAttribute('data-qa') ? `[data-qa="${el.getAttribute('data-qa')}"]` : '';
                        result.push(`<${el.tagName}${classes}${dataQa}> (${el.children.length} children)`);
                    }
                    return result.join('\\n');
                }
            """)
            print(f"  HTML structure:\n    {html_sample.replace(chr(10), chr(10) + '    ')}")

        except Exception as e:
            print(f"  ERROR: {e}")

    # ─── Тест 3: Дампим data-qa атрибуты ───
    print(f"\n[LAST] Все data-qa атрибуты на странице:")
    try:
        qa_attrs = await page.evaluate("""
            () => {
                const els = document.querySelectorAll('[data-qa]');
                const attrs = new Set();
                els.forEach(el => attrs.add(el.getAttribute('data-qa')));
                return [...attrs].sort().slice(0, 50);
            }
        """)
        for attr in qa_attrs:
            print(f"  data-qa='{attr}'")
    except Exception as e:
        print(f"  ERROR: {e}")

    await context.close()
    await browser.close()
    print("\nScreenshots saved to data/debug/")


if __name__ == "__main__":
    asyncio.run(main())
