"""
Скрипт для одноразового сохранения сессии rabota.by.
Запускать ЛОКАЛЬНО — откроется реальный браузер.

Использование:
    python scripts/save_cookies.py

После логина файл data/rabota_session.json загрузить в Railway Volume:
    railway volume add -m /data
    railway up  (сессия загрузится при первом деплое если лежит в data/)

Или через Railway CLI:
    railway run cp data/rabota_session.json /data/rabota_session.json
"""
import asyncio
import os

from playwright.async_api import async_playwright


async def main():
    os.makedirs("data", exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="chrome")
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://rabota.by")

        print("=" * 50)
        print("Log in to rabota.by in the opened browser.")
        print("Then press Enter here.")
        print("=" * 50)

        input("Press Enter when logged in... ")

        await context.storage_state(path="data/rabota_session.json")
        print("Session saved to data/rabota_session.json")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
