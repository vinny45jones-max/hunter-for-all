"""
Живой тест AI-оценки вакансий и генерации сопроводительных.

Прогоняет 5 тестовых вакансий (от идеального match до полного miss)
через реальный Claude API и показывает результаты.

Использование:
    # Указать реальный ANTHROPIC_API_KEY в .env или в env переменной
    python scripts/live_test.py
"""
import asyncio
import os
import sys
import time

# Чтобы импорты src.* работали
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Загрузить .env
from dotenv import load_dotenv
load_dotenv()

from src.models import Vacancy
from src.ai_filter import evaluate_and_cover


# ─── Тестовые вакансии ─────────────────────────────
# От идеального match до полного miss

TEST_VACANCIES = [
    Vacancy(
        external_id="test_1",
        url="https://rabota.by/vakansiya/100001",
        title="Коммерческий директор",
        company="ООО ТрансЛогистик",
        salary="от 5000 BYN",
        city="Минск",
        description="""
        Крупная дистрибуторская компания (оборот $20M) ищет коммерческого директора.
        Обязанности:
        - Управление продажами B2B, 40 менеджеров
        - P&L ответственность за коммерческий блок
        - Выстраивание системы KPI и управленческой отчётности
        - Оптимизация ассортимента (2000+ SKU) и работа с поставщиками
        - Внедрение CRM, автоматизация процессов
        Требования: 10+ лет опыта на руководящих позициях в B2B/дистрибуции,
        опыт работы с крупным ассортиментом, знание управленческого учёта.
        """,
    ),
    Vacancy(
        external_id="test_2",
        url="https://rabota.by/vakansiya/100002",
        title="Директор по развитию бизнеса / AI-трансформация",
        company="Digital Solutions Group",
        salary="от 8000 BYN",
        city="Минск",
        description="""
        Ищем руководителя, который совмещает бизнес-экспертизу с пониманием AI.
        Задачи:
        - Разработка стратегии цифровой трансформации для клиентов (средний бизнес)
        - Внедрение AI-решений в бизнес-процессы компаний
        - Управление командой из 15 человек
        - Развитие клиентской базы, переговоры на уровне C-level
        - Построение и продажа AI-продуктов для автоматизации
        Требования: MBA, 10+ лет C-level опыт, понимание AI/ML,
        опыт трансформации бизнес-процессов, английский B2+.
        """,
    ),
    Vacancy(
        external_id="test_3",
        url="https://rabota.by/vakansiya/100003",
        title="Операционный директор (COO)",
        company="Hauptmann Polska sp. z o.o.",
        salary="15000-20000 PLN",
        city="Варшава",
        description="""
        Производственная компания ищет COO для управления операциями.
        - Стратегическое и оперативное планирование
        - Управление supply chain и производством
        - Контроль бюджетов и KPI
        - Управление командой 50+ человек
        - Оптимизация бизнес-процессов, внедрение ERP
        Требования: опыт COO/операционного директора 5+ лет,
        знание польского языка, опыт работы в Польше.
        """,
    ),
    Vacancy(
        external_id="test_4",
        url="https://rabota.by/vakansiya/100004",
        title="Менеджер по продажам (стройматериалы)",
        company="СтройОпт",
        salary="1500-2500 BYN",
        city="Минск",
        description="""
        Ищем активного менеджера по продажам стройматериалов.
        - Холодные звонки, поиск клиентов
        - Ведение базы в CRM
        - Выполнение плана продаж
        - Работа на складе (приём/отгрузка)
        Требования: опыт продаж от 1 года, водительские права,
        коммуникабельность, стрессоустойчивость.
        """,
    ),
    Vacancy(
        external_id="test_5",
        url="https://rabota.by/vakansiya/100005",
        title="Frontend-разработчик (React/TypeScript)",
        company="IT Solutions",
        salary="3000-5000 BYN",
        city="Минск",
        description="""
        Ищем frontend-разработчика в команду продуктовой разработки.
        - React, TypeScript, Next.js
        - REST API, GraphQL
        - Unit/integration тесты
        - CI/CD, Git
        Требования: 3+ года коммерческого опыта, портфолио проектов.
        """,
    ),
]


async def main():
    print("=" * 60)
    print("LIVE TEST: AI-оценка вакансий (через Claude API)")
    print("=" * 60)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("test_"):
        print("\n[!] ANTHROPIC_API_KEY не задан или тестовый.")
        print("    Укажи реальный ключ в .env или в переменной окружения:")
        print("    set ANTHROPIC_API_KEY=sk-ant-...")
        print("    python scripts/live_test.py")
        sys.exit(1)

    print(f"\nAPI key: {api_key[:12]}...{api_key[-4:]}")
    print(f"Тестовых вакансий: {len(TEST_VACANCIES)}\n")

    results = []

    for i, v in enumerate(TEST_VACANCIES, 1):
        print(f"─── [{i}/{len(TEST_VACANCIES)}] {v.title} @ {v.company} ───")
        t0 = time.time()

        try:
            result = await evaluate_and_cover(v, min_score=60)
            elapsed = time.time() - t0
            score = result["score"]
            reason = result["reason"]
            cover = result.get("cover_letter")

            emoji = "🟢" if score >= 70 else "🟡" if score >= 40 else "🔴"
            print(f"  {emoji} Score: {score}/100  ({elapsed:.1f}s)")
            print(f"  Reason: {reason}")

            if cover:
                print(f"  Cover letter:")
                for line in cover.split("\n"):
                    print(f"    | {line}")

            results.append({"vacancy": v.title, "score": score, "reason": reason})
            print()

        except Exception as e:
            print(f"  [ERROR] {e}\n")
            results.append({"vacancy": v.title, "score": -1, "reason": str(e)})

    # ─── Итоги ───
    print("=" * 60)
    print("ИТОГИ:")
    print("=" * 60)
    for r in results:
        emoji = "🟢" if r["score"] >= 70 else "🟡" if r["score"] >= 40 else "🔴" if r["score"] >= 0 else "❌"
        print(f"  {emoji} {r['score']:>3}/100 | {r['vacancy']}")
    print()

    # Проверка адекватности
    scores = [r["score"] for r in results if r["score"] >= 0]
    if len(scores) >= 4:
        if scores[0] > scores[3] and scores[0] > scores[4]:
            print("[OK] Релевантные вакансии получили выше score чем нерелевантные")
        else:
            print("[!!] Порядок score подозрительный — проверь промпты")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
