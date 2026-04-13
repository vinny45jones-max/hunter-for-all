# Quick Wins: Prompt Caching, Config Extraction, Monitoring

**Date:** 2026-04-13
**Status:** Approved
**Goal:** Снизить расходы на API, упростить конфигурацию, добавить мониторинг здоровья бота.

---

## 1. Prompt Caching + вынос конфигурации

### 1.1 Профиль кандидата

**Что:** Вынести профиль кандидата из захардкоженных промптов в отдельный файл.

**Файл:** `data/profile.md` — Markdown-текст профиля, подставляется в промпты как есть, без парсинга.

**Конфиг:** В `config.py` добавляется `candidate_profile_path: str = "data/profile.md"`.

**Загрузка:** В `ai_filter.py` профиль загружается один раз при импорте модуля:
```python
_profile_text = Path(settings.candidate_profile_path).read_text(encoding="utf-8")
```

**Промпты:** Все три промпта (EVALUATE_PROMPT, COVER_LETTER_PROMPT, REPLY_PROMPT) используют `{profile}` placeholder вместо захардкоженного текста профиля.

### 1.2 Модель в .env

**Что:** Вынести имя модели из хардкода в конфигурацию.

**Конфиг:** В `config.py` добавляется `ai_model: str = "claude-sonnet-4-20250514"`.

**Использование:** В `ai_filter.py` вместо `MODEL = "..."` используется `settings.ai_model`.

### 1.3 Prompt Caching

**Что:** Использовать Anthropic prompt caching для system prompt + профиля.

**Механизм:** Все вызовы `_client.messages.create()` передают system prompt как structured content с `cache_control`:

```python
system=[
    {
        "type": "text",
        "text": SYSTEM_PROMPT + "\n\n" + _profile_text,
        "cache_control": {"type": "ephemeral"}
    }
]
```

**Эффект:** Кэш живёт 5 минут. При обработке пачки вакансий в pipeline первый вызов пишет в кэш, остальные читают. Экономия ~90% входных токенов на system+профиль.

**Затрагиваемые функции:**
- `evaluate_relevance()` — system prompt + профиль в кэш
- `generate_cover_letter()` — добавить system prompt с профилем (сейчас нет system)
- `generate_reply()` — добавить system prompt с профилем
- `improve_text()` — без изменений (короткий промпт, профиль не нужен)

---

## 2. Мониторинг здоровья скрапера

### 2.1 Детектор сбоев

**Что:** Если парсинг возвращает 0 вакансий N раз подряд — предупредить в Telegram.

**Реализация:**
- Переменная модуля `_empty_cycles: int = 0` в `pipeline.py`
- После `parse_all_keywords()`: если `len(all_vacancies) == 0`, инкрементировать `_empty_cycles`
- Если `_empty_cycles >= threshold` — отправить предупреждение в Telegram
- Если `len(all_vacancies) > 0` — сбросить `_empty_cycles = 0`

**Конфиг:** В `config.py` добавляется `scrape_fail_threshold: int = 3`.

**Сообщение в Telegram:**
```
Скрапер не нашёл вакансий {N} циклов подряд.
Возможно rabota.by изменил верстку.
Проверь вручную: https://rabota.by/search/vacancy?text=директор
```

**Хранение:** В памяти (переменная модуля). При перезапуске сбрасывается — допустимо, т.к. первый цикл запускается сразу при старте.

---

## 3. Daily Heartbeat

### 3.1 Ежедневная сводка

**Что:** Раз в день бот отправляет в Telegram сводку за день.

**Расписание:** `cron`, `hour=settings.daily_summary_hour`, `minute=0`. По умолчанию 20:00.

**Конфиг:** В `config.py` добавляется `daily_summary_hour: int = 20`.

### 3.2 Функция send_daily_summary()

**Расположение:** `pipeline.py`.

**Данные:** Вызывает `database.get_daily_stats()` — новая функция.

**Формат сообщения:**
```
Дневная сводка:
Новых вакансий: {new}
Релевантных: {relevant}
Откликов: {applied}
Сообщений от работодателей: {messages}
Бот работает с {start_time}
```

### 3.3 database.get_daily_stats()

**Новая функция в `database.py`.** SQL-запросы:
- Новых вакансий: `COUNT(*) FROM vacancies WHERE date(created_at) = date('now')`
- Релевантных: `COUNT(*) FROM vacancies WHERE date(created_at) = date('now') AND relevance_score >= ?` (параметр: `settings.min_relevance_score`)
- Откликов: `COUNT(*) FROM vacancies WHERE date(applied_at) = date('now') AND status = 'applied'`
- Сообщений: `COUNT(*) FROM messages WHERE date(created_at) = date('now') AND direction = 'incoming'`

### 3.4 Время старта

Переменная `_bot_start_time` в `pipeline.py`, устанавливается при первом вызове `send_daily_summary()` или при импорте модуля.

---

## Затрагиваемые файлы

| Файл | Изменения |
|---|---|
| `data/profile.md` | **Новый.** Текст профиля кандидата |
| `src/config.py` | +4 поля: `candidate_profile_path`, `ai_model`, `scrape_fail_threshold`, `daily_summary_hour` |
| `src/ai_filter.py` | Prompt caching, загрузка профиля из файла, модель из config |
| `src/pipeline.py` | Счётчик пустых циклов, `send_daily_summary()` |
| `src/database.py` | +1 функция: `get_daily_stats()` |
| `src/main.py` | +1 job в scheduler: `daily_summary` |
| `.env` | +2 строки: `CANDIDATE_PROFILE_PATH`, `AI_MODEL` (опционально) |

## Не затрагивается

- `bot.py`, `scraper.py`, `inbox.py`, `applier.py`, `responder.py`, `models.py` — без изменений
- Тесты — существующие тесты не ломаются (профиль подхватывается из файла, fallback не нужен)
