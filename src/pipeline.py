import asyncio
import random

from src.config import settings, log
from src import database, scraper, ai_filter, bot, inbox

# Стоп-слова — вакансии с этими словами в названии отсекаются сразу
STOP_WORDS = [
    "магазин", "школ", "детский сад", "аптек", "медсестр", "повар",
    "кассир", "уборщ", "охранник", "водитель", "грузчик", "сторож",
    "воспитатель", "учитель", "преподаватель", "фармацевт", "санитар",
    "медицинск", "стоматолог", "ветеринар", "парикмахер", "маникюр",
    "продавец", "кладовщик", "слесарь", "сварщик", "электрик",
    "сантехник", "плотник", "токар", "фрезеровщик",
]

# Порог быстрой оценки — вакансии выше него идут на полную проверку
BATCH_THRESHOLD = 40


def _passes_stop_words(title: str) -> bool:
    title_lower = title.lower()
    return not any(word in title_lower for word in STOP_WORDS)


async def run_pipeline():
    log.info("Pipeline: starting vacancy scan...")

    try:
        await bot.send_text("🔍 Начинаю поиск вакансий...")

        # 1. Скрапинг
        all_vacancies = await scraper.parse_all_keywords()

        # 2. Дедупликация
        new_vacancies = await database.filter_new(all_vacancies)
        if not new_vacancies:
            log.info("Pipeline: no new vacancies")
            await bot.send_text("Новых вакансий не найдено.")
            return

        log.info(f"Pipeline: {len(new_vacancies)} new vacancies found")

        # 3. Стоп-слова фильтр
        before_stop = len(new_vacancies)
        new_vacancies = [v for v in new_vacancies if _passes_stop_words(v.title)]
        filtered_out = before_stop - len(new_vacancies)
        if filtered_out:
            log.info(f"Pipeline: стоп-слова отсекли {filtered_out} вакансий")

        if not new_vacancies:
            await bot.send_text("Новых подходящих вакансий не найдено (все отсечены стоп-словами).")
            return

        await bot.send_text(
            f"Найдено {len(all_vacancies)} вакансий, {len(new_vacancies)} новых "
            f"(отсечено стоп-словами: {filtered_out}). Быстрая оценка..."
        )

        # 4. Батч-оценка по названиям (быстрая, без описаний)
        try:
            batch_scores = await ai_filter.batch_evaluate_titles(new_vacancies)
        except Exception as e:
            log.error(f"Pipeline: батч-оценка упала: {e}")
            await bot.send_text(f"⚠️ Ошибка AI при быстрой оценке: {e}")
            return
        promising = []
        for i, v in enumerate(new_vacancies):
            score = batch_scores.get(i, 0)
            v.relevance_score = score
            if score >= BATCH_THRESHOLD:
                promising.append(v)
            else:
                # Сохранить отсечённые с низким баллом
                v.relevance_reason = f"Быстрая оценка: {score}"
                await database.save_vacancy(v)

        log.info(f"Pipeline: батч-оценка — {len(promising)} перспективных из {len(new_vacancies)}")

        if not promising:
            await bot.send_text("После быстрой оценки подходящих вакансий не найдено.")
            return

        await bot.send_text(f"Перспективных: {len(promising)}. Загружаю описания...")

        # 5. Загрузить описания только для перспективных
        for v in promising:
            try:
                v.description = await scraper.get_full_description(v.url)
                await asyncio.sleep(random.uniform(1, 2))
            except Exception as e:
                log.warning(f"Pipeline: failed to get description for {v.url}: {e}")

        # 6. Полная AI-оценка с описанием + cover letter (один вызов)
        min_score = await database.get_setting_int("min_relevance_score", settings.min_relevance_score)
        await bot.send_text(f"Оцениваю {len(promising)} вакансий с описаниями...")
        for v in promising:
            try:
                result = await ai_filter.evaluate_and_cover(v, min_score)
                v.relevance_score = result["score"]
                v.relevance_reason = result["reason"]

                if v.relevance_score >= min_score and result.get("cover_letter"):
                    v.cover_letter = result["cover_letter"]
                    v.status = "filtered"
            except Exception as e:
                log.warning(f"Pipeline: AI filter error for {v.title}: {e}")
                await bot.send_text(f"⚠️ Ошибка AI для «{v.title}»: {type(e).__name__}")

            await database.save_vacancy(v)

        # 7. Отправить в Telegram
        relevant = [v for v in promising if v.status == "filtered"]
        for v in relevant:
            try:
                await bot.send_vacancy_card(v)
                await database.update_status(v.id, "sent_to_tg")
            except Exception as e:
                log.error(f"Pipeline: TG send error for {v.title}: {e}")

        # 8. Лог
        await database.save_search_log(
            query=",".join(settings.search_keywords),
            total=len(all_vacancies),
            new=len(new_vacancies),
            relevant=len(relevant),
        )

        log.info(
            f"Pipeline: done. "
            f"Total={len(all_vacancies)}, new={len(new_vacancies)}, "
            f"promising={len(promising)}, relevant={len(relevant)}"
        )
        await bot.send_text(
            f"✅ Поиск завершён.\n"
            f"Всего: {len(all_vacancies)}, новых: {len(new_vacancies)}, "
            f"перспективных: {len(promising)}, подходящих: {len(relevant)}"
        )

    except Exception as e:
        log.error(f"Pipeline error: {e}")
        try:
            await bot.send_text(f"⚠️ Ошибка пайплайна: {e}")
        except Exception:
            pass


async def check_messages():
    log.info("Inbox: checking messages...")

    try:
        new_messages = await inbox.check_inbox()

        for msg in new_messages:
            try:
                # Связать с вакансией
                vacancy = None
                if msg.company and msg.vacancy_title:
                    vacancy = await database.find_vacancy_by_company_title(
                        msg.company, msg.vacancy_title
                    )
                    if vacancy:
                        msg.vacancy_id = vacancy.id

                # Сохранить conversation
                from src.models import Conversation
                conv = Conversation(
                    conversation_id=msg.conversation_id or msg.message_id,
                    vacancy_id=msg.vacancy_id,
                    vacancy_title=msg.vacancy_title,
                    company=msg.company,
                    status="active",
                )
                await database.save_conversation(conv)

                # Сохранить сообщение
                saved = await database.save_incoming_message(msg)
                if saved is None:
                    continue  # Дубликат

                # Отправить в Telegram
                await bot.send_message_card(msg, vacancy)

            except Exception as e:
                log.warning(f"Inbox: error processing message: {e}")
                continue

        if new_messages:
            log.info(f"Inbox: {len(new_messages)} new messages processed")
        else:
            log.info("Inbox: no new messages")

    except Exception as e:
        log.error(f"Inbox check error: {e}")
