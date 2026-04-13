# Rabota Hunter — Установка

Автоматический поиск вакансий на rabota.by с AI-фильтрацией и Telegram-ботом.

## Что нужно

1. **Telegram-бот** — создайте через [@BotFather](https://t.me/BotFather), получите токен
2. **Ваш Telegram Chat ID** — узнайте через [@userinfobot](https://t.me/userinfobot)
3. **API-ключ Anthropic** — получите на [console.anthropic.com](https://console.anthropic.com)

## Настройка

1. Скопируйте `.env.example` в `.env`:
   ```bash
   cp .env.example .env
   ```

2. Заполните 3 поля в `.env`:
   ```
   TELEGRAM_BOT_TOKEN=ваш_токен_от_BotFather
   TELEGRAM_CHAT_ID=ваш_chat_id
   ANTHROPIC_API_KEY=sk-ant-...
   ```

3. Запустите бота:
   ```bash
   python -m src.main
   ```

4. Откройте бота в Telegram, нажмите `/start` — бот проведёт настройку:
   - Логин и пароль от rabota.by
   - Ключевые слова для поиска
   - Ваш профиль (опыт, навыки, достижения)

После этого бот начнёт автоматически искать и оценивать вакансии.

## Запуск через Docker

```bash
docker compose up -d
```

## Что умеет бот

- Парсит вакансии на rabota.by по вашим ключевым словам
- AI оценивает каждую вакансию под ваш профиль (0–100 баллов)
- Присылает подходящие вакансии в Telegram с сопроводительным письмом
- Автоматически откликается на вакансии (по вашему подтверждению)
- Отслеживает входящие сообщения от работодателей
- Генерирует ответы на сообщения работодателей
