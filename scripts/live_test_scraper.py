"""
Живой тест скрапера rabota.by

Открывает rabota.by, ищет вакансии по ключевым словам,
парсит карточки, получает описание одной вакансии.
НЕ требует авторизации — парсинг публичных страниц.

Использование:
    python scripts/live_test_scraper.py
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


async def main():
    print("=" * 60)
    print("LIVE TEST: Scraper rabota.by")
    print("=" * 60)

    from src.scraper import get_browser, parse_search_results, get_full_description, close, _detect_chrome_channel

    channel = _detect_chrome_channel()
    print(f"Chrome channel: {channel or 'playwright-chromium (default)'}")

    # ─── Тест 1: Запуск браузера ───
    print("\n--- [1] Запуск браузера ---")
    t0 = time.time()
    try:
        browser = await get_browser()
        print(f"  OK: Browser запущен ({time.time() - t0:.1f}s)")
        print(f"  Connected: {browser.is_connected()}")
    except Exception as e:
        print(f"  FAIL: {e}")
        return

    # ─── Тест 2: Открыть rabota.by ───
    print("\n--- [2] Открываем rabota.by ---")
    t0 = time.time()
    try:
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        await page.goto("https://rabota.by", wait_until="networkidle", timeout=30000)
        title = await page.title()
        print(f"  OK: Страница загружена ({time.time() - t0:.1f}s)")
        print(f"  Title: {title}")
        await context.close()
    except Exception as e:
        print(f"  FAIL: {e}")
        return

    # ─── Тест 3: Парсинг поисковой выдачи ───
    keywords_to_test = ["директор", "CEO"]
    all_vacancies = []

    for keyword in keywords_to_test:
        print(f"\n--- [3] Парсинг '{keyword}' (1 страница) ---")
        t0 = time.time()
        try:
            vacancies = await parse_search_results(keyword, max_pages=1)
            elapsed = time.time() - t0
            print(f"  OK: Найдено {len(vacancies)} вакансий ({elapsed:.1f}s)")

            for i, v in enumerate(vacancies[:3]):
                print(f"  [{i+1}] {v.title}")
                print(f"      Компания: {v.company or 'N/A'}")
                print(f"      Зарплата: {v.salary or 'N/A'}")
                print(f"      Город: {v.city or 'N/A'}")
                print(f"      URL: {v.url}")
                print(f"      ID: {v.external_id}")

            if len(vacancies) > 3:
                print(f"  ... и ещё {len(vacancies) - 3}")

            all_vacancies.extend(vacancies)
        except Exception as e:
            print(f"  FAIL: {e}")
            import traceback
            traceback.print_exc()

    # ─── Тест 4: Получить полное описание ───
    if all_vacancies:
        v = all_vacancies[0]
        print(f"\n--- [4] Полное описание: {v.title} ---")
        t0 = time.time()
        try:
            desc = await get_full_description(v.url)
            elapsed = time.time() - t0
            if desc:
                preview = desc[:500].replace('\n', ' ')
                print(f"  OK: Описание получено ({elapsed:.1f}s, {len(desc)} символов)")
                print(f"  Превью: {preview}...")
            else:
                print(f"  WARN: Описание пустое ({elapsed:.1f}s)")
        except Exception as e:
            print(f"  FAIL: {e}")
    else:
        print("\n--- [4] Пропуск: нет вакансий для тестирования описания ---")

    # ─── Итоги ───
    print("\n" + "=" * 60)
    print("ИТОГИ:")
    print(f"  Браузер: OK (system Chrome)" if channel else "  Браузер: OK (playwright)")
    print(f"  rabota.by: доступен")
    print(f"  Вакансий спарсено: {len(all_vacancies)}")

    unique_ids = set(v.external_id for v in all_vacancies)
    print(f"  Уникальных ID: {len(unique_ids)}")

    if all_vacancies:
        with_company = sum(1 for v in all_vacancies if v.company)
        with_salary = sum(1 for v in all_vacancies if v.salary)
        print(f"  С компанией: {with_company}/{len(all_vacancies)}")
        print(f"  С зарплатой: {with_salary}/{len(all_vacancies)}")
    print("=" * 60)

    await close()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
