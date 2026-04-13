"""
Живой тест полного пайплайна:
  1. Скрапим rabota.by (1 страница, 1 ключевое слово)
  2. Получаем описание первых 3 вакансий
  3. Оцениваем через Claude AI
  4. Сохраняем в SQLite (локальная БД)

Использование:
    python scripts/live_test_pipeline.py
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Локальный путь к БД (не /data/hunter.db)
os.environ.setdefault("DB_PATH", "data/test_pipeline.db")
os.makedirs("data", exist_ok=True)

from dotenv import load_dotenv
load_dotenv()


async def main():
    print("=" * 60)
    print("LIVE PIPELINE TEST: Scrape -> AI -> DB")
    print("=" * 60)

    from src.config import settings
    from src.scraper import parse_search_results, get_full_description, close
    from src.ai_filter import evaluate_relevance
    from src import database as db

    # Перезаписать путь к БД для локального теста
    db._db_path = "data/test_pipeline.db"

    # --- 1. Инициализация БД ---
    print("\n--- [1] Инициализация БД ---")
    await db.init()
    print("  OK: БД инициализирована")

    # --- 2. Скрапинг ---
    keyword = "директор"
    print(f"\n--- [2] Скрапим '{keyword}' (1 страница) ---")
    t0 = time.time()
    vacancies = await parse_search_results(keyword, max_pages=1)
    elapsed = time.time() - t0
    print(f"  OK: {len(vacancies)} вакансий за {elapsed:.1f}s")

    if not vacancies:
        print("  FAIL: нет вакансий для теста!")
        await close()
        return

    # Берём первые 3 вакансии для полного теста
    test_vacancies = vacancies[:3]

    # --- 3. Получение описаний ---
    print(f"\n--- [3] Получаем описания для {len(test_vacancies)} вакансий ---")
    for i, v in enumerate(test_vacancies):
        t0 = time.time()
        desc = await get_full_description(v.url)
        elapsed = time.time() - t0
        v.description = desc
        preview = (desc[:150] + "...") if desc and len(desc) > 150 else desc
        print(f"  [{i+1}] {v.title}")
        print(f"      Описание: {len(desc or '')} символов ({elapsed:.1f}s)")
        print(f"      Превью: {preview}")

    # --- 4. AI-оценка ---
    api_key = settings.anthropic_api_key
    if api_key.startswith("test_") or api_key == "sk-test":
        print("\n--- [4] ПРОПУСК: AI-оценка (тестовый API ключ) ---")
    else:
        print(f"\n--- [4] AI-оценка через Claude (модель: claude-sonnet-4-20250514) ---")
        for i, v in enumerate(test_vacancies):
            t0 = time.time()
            try:
                result = await evaluate_relevance(v)
                elapsed = time.time() - t0
                v.relevance_score = result["score"]
                v.relevance_reason = result["reason"]
                print(f"  [{i+1}] {v.title}")
                print(f"      Score: {v.relevance_score}/100 ({elapsed:.1f}s)")
                print(f"      Reason: {v.relevance_reason}")
            except Exception as e:
                print(f"  [{i+1}] FAIL: {e}")
                v.relevance_score = 0
                v.relevance_reason = f"Error: {e}"

    # --- 5. Сохранение в БД ---
    print(f"\n--- [5] Сохранение в SQLite ---")
    for v in test_vacancies:
        try:
            v.status = "filtered" if v.relevance_score >= settings.min_relevance_score else "skipped"
            row_id = await db.save_vacancy(v)
            print(f"  [{v.external_id}] {v.title} -> id={row_id}, status={v.status}")
        except Exception as e:
            print(f"  FAIL: {e}")

    # --- 6. Проверка из БД ---
    print(f"\n--- [6] Чтение из БД ---")
    last = await db.get_last_vacancies(limit=5)
    for v in last:
        print(f"  [{v.id}] {v.title} | Score: {v.relevance_score} | Status: {v.status}")

    stats = await db.get_stats()
    print(f"\n  Статистика БД: {stats}")

    # --- Итоги ---
    print("\n" + "=" * 60)
    print("ИТОГИ ПАЙПЛАЙНА:")
    print(f"  Спарсено вакансий: {len(vacancies)}")
    print(f"  С описаниями: {sum(1 for v in test_vacancies if v.description)}/{len(test_vacancies)}")
    print(f"  AI-оценено: {sum(1 for v in test_vacancies if v.relevance_score > 0)}/{len(test_vacancies)}")
    print(f"  Сохранено в БД: {len(test_vacancies)}")
    for v in test_vacancies:
        status_icon = "🟢" if v.relevance_score >= settings.min_relevance_score else "🔴"
        print(f"  {status_icon} {v.title} -> {v.relevance_score}/100")
    print("=" * 60)

    await close()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
