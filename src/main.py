import asyncio
import signal
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import settings, log
from src import database, pipeline, bot


async def main():
    log.info("Starting Rabota Hunter Bot...")

    # 1. Init DB
    await database.init()

    # 2. Scheduler
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        pipeline.run_pipeline,
        "cron",
        hour=8,
        minute=0,
        id="vacancy_pipeline",
        name="Vacancy Pipeline",
    )

    scheduler.add_job(
        pipeline.check_messages,
        "cron",
        hour=8,
        minute=0,
        id="check_messages",
        name="Check Messages",
    )

    scheduler.start()
    log.info("Scheduler started: vacancies and messages daily at 08:00")

    # 3. Telegram bot
    app = bot.create_app()

    log.info("Starting Telegram polling...")
    await app.initialize()
    # Команды меню не ставим глобально — только per-chat после онбординга
    await app.bot.delete_my_commands()
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
    from src import browser_pool
    await browser_pool.close()
    log.info("Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
