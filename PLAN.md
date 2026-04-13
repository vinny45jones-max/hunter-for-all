# План реализации: Cover Letter Flow (v3)

## 1. Расширение БД — новые поля в таблице vacancies
- [x] `apply_state TEXT DEFAULT 'idle'` — состояние отклика (idle | previewing | editing | sending | sent | failed)
- [x] `cover_letter_version INTEGER DEFAULT 0` — счётчик версий письма
- [x] `employer_requirements TEXT` — JSON: требования работодателя к письму
- [x] `require_cover_letter BOOLEAN DEFAULT 0` — обязательно ли письмо
- [x] `negotiation_id TEXT` — ID отклика на rabota.by
- [x] Миграция в `database.py` (ALTER TABLE или пересоздание)

## 2. extract_cover_letter_requirements() ✅
- [x] Функция в модуле `cover_flow.py`
- [x] Паттерны поиска: 10 regex-паттернов для русскоязычных триггеров
- [x] Возвращает список требований (1-5 штук) или пустой список
- [x] Unit-тесты: `tests/test_cover_flow.py` (14 passed)

## 3. Расширение ai_filter.py — новые промпты ✅
- [x] `generate_cover_letter(vacancy, requirements, version)` — промпт с requirements_block и version_block
- [x] `improve_cover_letter(text, vacancy, requirements)` — доработка текста пользователя с учётом требований

## 4. cover_flow.py — логика состояний ✅
- [x] State machine: _TRANSITIONS, _set_state() с валидацией переходов
- [x] start_cover_letter() — извлечение требований + генерация + previewing
- [x] regenerate_cover_letter() — новый вариант (другой ракурс, version)
- [x] enter_editing(), submit_user_text(), ai_improve_user_text()
- [x] confirm_send(), mark_sent(), mark_failed(), cancel()
- [x] format_preview() — текст превью для Telegram

## 5. bot.py — новые callback handlers для cover letter flow ✅
- [x] `callback_apply` — переделан: генерация письма + превью с кнопками [Отправить] [Изменить] [Новое] [Отмена]
- [x] `callback_cover_send` — отправка отклика с письмом через cover_flow state machine
- [x] `callback_cover_edit` — переход в режим редактирования (ConversationHandler)
- [x] `receive_cover_text` — обработка текста пользователя (письмо)
- [x] `callback_cover_aifix` — AI доработка текста пользователя
- [x] `callback_cover_regen` — генерация нового варианта письма
- [x] Контроль: один контекст за раз (`editing_vacancy` в user_data)

## 6. Обновление карточки вакансии в Telegram ✅
- [x] Показ требований работодателя в превью письма (format_preview в cover flow)
- [x] Счётчик оставшихся откликов — в карточке вакансии и в превью письма
- [x] Индикатор `require_cover_letter` в карточке

## 7. Тестирование ✅
- [x] Unit-тест extract_cover_letter_requirements() (14 тестов — были ранее)
- [x] Unit-тест cover_flow state transitions (24 новых теста)
- [x] format_preview — 3 теста
- [ ] Интеграционный тест: полный cover letter flow в TG (требует live-окружение)
