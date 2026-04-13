import asyncio
import signal
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import BotCommand

from src.config import settings, log
from src import database, pipeline, bot


BOT_COMMANDS = [
    BotCommand("start", "Показать справку"),
    BotCommand("stats", "Статистика"),
    BotCommand("search", "Запустить парсинг сейчас"),
    BotCommand("last", "Последние 5 вакансий"),
    BotCommand("inbox", "Непрочитанные сообщения"),
    BotCommand("threads", "Активные переписки"),
]


async def main():
    log.info("Starting Rabota Hunter Bot...")

    # 1. Init DB
    await database.init()

    # 2. Scheduler
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        pipeline.run_pipeline,
        "interval",
        minutes=settings.scrape_interval_minutes,
        # next_run_time=datetime.now(),  # не запускать при старте
        id="vacancy_pipeline",
        name="Vacancy Pipeline",
    )

    scheduler.add_job(
        pipeline.check_messages,
        "interval",
        minutes=settings.message_check_interval_minutes,
        id="check_messages",
        name="Check Messages",
    )

    scheduler.start()
    log.info(
        f"Scheduler started: vacancies every {settings.scrape_interval_minutes}m, "
        f"messages every {settings.message_check_interval_minutes}m"
    )

    # 3. Telegram bot
    app = bot.create_app()

    log.info("Starting Telegram polling...")
    await app.initialize()
    await app.bot.set_my_commands(BOT_COMMANDS)
    await app.start()
    await app.updater.start_polling()

    log.info("Bot is running. Waiting for updates...")

    # 4. Graceful shutdown via signal
    stop_event = asyncio.Event()

    def _signal_handler():
        log.info("Received shutdown signal...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows — signal handlers not supported in asyncio
            pass

    # Keep running until signal
    try:
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit):
        pass

    # Cleanup
    log.info("Shutting down...")
    scheduler.shutdown(wait=False)
    await app.updater.stop()
    await app.stop()
    await app.shutdown()
    from src import scraper
    await scraper.close()
    log.info("Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
