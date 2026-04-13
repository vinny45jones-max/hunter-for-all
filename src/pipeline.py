import asyncio
import random

from src.config import settings, log
from src import database, scraper, ai_filter, bot, inbox


async def run_pipeline():
    log.info("Pipeline: starting vacancy scan...")

    try:
        # 1. Скрапинг
        all_vacancies = await scraper.parse_all_keywords()

        # 2. Дедупликация
        new_vacancies = await database.filter_new(all_vacancies)
        if not new_vacancies:
            log.info("Pipeline: no new vacancies")
            return

        log.info(f"Pipeline: {len(new_vacancies)} new vacancies to process")

        # 3. Получить полные описания
        for v in new_vacancies:
            try:
                v.description = await scraper.get_full_description(v.url)
                await asyncio.sleep(random.uniform(2, 4))
            except Exception as e:
                log.warning(f"Pipeline: failed to get description for {v.url}: {e}")

        # 4. AI-оценка
        for v in new_vacancies:
            try:
                result = await ai_filter.evaluate_relevance(v)
                v.relevance_score = result["score"]
                v.relevance_reason = result["reason"]

                if v.relevance_score >= settings.min_relevance_score:
                    v.cover_letter = await ai_filter.generate_cover_letter(v)
                    v.status = "filtered"
            except Exception as e:
                log.warning(f"Pipeline: AI filter error for {v.title}: {e}")

            await database.save_vacancy(v)

        # 5. Отправить в Telegram
        relevant = [v for v in new_vacancies if v.status == "filtered"]
        for v in relevant:
            try:
                await bot.send_vacancy_card(v)
                await database.update_status(v.id, "sent_to_tg")
            except Exception as e:
                log.error(f"Pipeline: TG send error for {v.title}: {e}")

        # 6. Лог
        await database.save_search_log(
            query=",".join(settings.search_keywords),
            total=len(all_vacancies),
            new=len(new_vacancies),
            relevant=len(relevant),
        )

        log.info(
            f"Pipeline: done. "
            f"Total={len(all_vacancies)}, new={len(new_vacancies)}, relevant={len(relevant)}"
        )

    except Exception as e:
        log.error(f"Pipeline error: {e}")
        try:
            await bot.send_text(f"Pipeline error: {e}")
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
