"""
Тест 5: Telegram bot — создание, хендлеры, escape, карточки.
Не требует реального токена — проверяет структуру, а не HTTP.
"""
import pytest
from src.bot import (
    _escape_md,
    _vacancy_card_text,
    _message_card_text,
    _vacancy_keyboard,
    _message_keyboard,
    create_app,
)
from src.models import Vacancy, Message


class TestEscapeMd:
    def test_basic_escape(self):
        assert _escape_md("hello_world") == r"hello\_world"

    def test_multiple_chars(self):
        result = _escape_md("a*b[c]d(e)f")
        assert r"\*" in result
        assert r"\[" in result
        assert r"\]" in result
        assert r"\(" in result
        assert r"\)" in result

    def test_empty(self):
        assert _escape_md("") == ""
        assert _escape_md(None) == ""

    def test_plain_text(self):
        assert _escape_md("Hello World") == "Hello World"

    def test_numbers(self):
        assert _escape_md("Score: 85/100") == "Score: 85/100"

    def test_all_special_chars(self):
        special = r"_*[]()~`>#+\-=|{}.!"
        result = _escape_md(special)
        # Каждый символ должен быть экранирован
        for ch in special:
            if ch == '\\':
                continue
            assert f"\\{ch}" in result or f"\\\\{ch}" in result


class TestVacancyCard:
    def test_card_text(self):
        v = Vacancy(
            external_id="1",
            url="https://r.by/1",
            title="CEO",
            company="Acme Corp",
            salary="5000 USD",
            city="Minsk",
            relevance_score=85,
            relevance_reason="Great match",
            cover_letter="Dear Sir...",
        )
        text = _vacancy_card_text(v)
        assert "CEO" in text
        assert "Acme Corp" in text
        assert "5000 USD" in text
        assert "85/100" in text
        assert "Great match" in text
        assert "Сопроводительное сгенерировано" in text

    def test_card_text_no_cover(self):
        v = Vacancy(
            external_id="2",
            url="u",
            title="CTO",
            relevance_score=60,
        )
        text = _vacancy_card_text(v)
        assert "Без сопроводительного" in text
        assert "Не указана" in text  # company/salary defaults

    def test_card_text_no_optionals(self):
        v = Vacancy(external_id="3", url="u", title="PM", relevance_score=0)
        text = _vacancy_card_text(v)
        assert "PM" in text
        assert "0/100" in text


class TestVacancyKeyboard:
    def test_keyboard_structure(self):
        kb = _vacancy_keyboard(42, "https://r.by/42")
        rows = kb.inline_keyboard
        assert len(rows) == 2

        # Row 1: Откликнуться + Пропустить
        assert len(rows[0]) == 2
        assert rows[0][0].callback_data == "apply:42"
        assert rows[0][1].callback_data == "skip:42"

        # Row 2: URL button
        assert len(rows[1]) == 1
        assert rows[1][0].url == "https://r.by/42"


class TestMessageCard:
    def test_message_card(self):
        msg = Message(
            message_id="m1",
            text="Приглашаем на собеседование",
            direction="incoming",
            sender="HR Manager",
            company="Acme Corp",
            vacancy_title="CEO",
        )
        text = _message_card_text(msg)
        assert "Новое сообщение" in text
        assert "Acme Corp" in text
        assert "CEO" in text
        assert "HR Manager" in text


class TestMessageKeyboard:
    def test_with_url(self):
        kb = _message_keyboard("conv1", "https://r.by/responses/conv1")
        rows = kb.inline_keyboard
        assert len(rows) == 2
        assert rows[0][0].callback_data == "reply:conv1"
        assert rows[0][1].callback_data == "ai_reply:conv1"
        assert rows[1][0].url == "https://r.by/responses/conv1"

    def test_without_url(self):
        kb = _message_keyboard("conv2")
        rows = kb.inline_keyboard
        assert len(rows) == 1  # No URL row


class TestCreateApp:
    def test_app_created(self):
        app = create_app()
        assert app is not None

    def test_handlers_registered(self):
        app = create_app()
        # ConversationHandler + 6 commands + 6 callbacks = 13 handlers
        handler_count = sum(len(g) for g in app.handlers.values())
        assert handler_count >= 13

    def test_handlers_include_commands(self):
        app = create_app()
        from telegram.ext import CommandHandler
        cmd_handlers = [
            h for group in app.handlers.values()
            for h in group
            if isinstance(h, CommandHandler)
        ]
        commands = set()
        for h in cmd_handlers:
            commands.update(h.commands)
        assert "start" in commands
        assert "stats" in commands
        assert "search" in commands
        assert "last" in commands
        assert "inbox" in commands
        assert "threads" in commands

    def test_handlers_include_callbacks(self):
        app = create_app()
        from telegram.ext import CallbackQueryHandler
        cb_handlers = [
            h for group in app.handlers.values()
            for h in group
            if isinstance(h, CallbackQueryHandler)
        ]
        # apply, skip, ai_reply, send, improve, cancel_reply = 6
        assert len(cb_handlers) >= 6
