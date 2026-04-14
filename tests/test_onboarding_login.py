"""Онбординг и /settings: тестовый логин rabota.by перед сохранением пароля."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src import bot
from telegram.ext import ConversationHandler


def _make_update(text: str, chat_id: int = 123):
    update = MagicMock()
    update.message = MagicMock()
    update.message.text = text
    update.message.delete = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.effective_chat.id = chat_id
    return update


def _make_context(user_data: dict):
    ctx = MagicMock()
    ctx.user_data = user_data
    return ctx


@pytest.mark.asyncio
async def test_onboard_password_success_advances_to_confirm():
    update = _make_update("correct-password")
    ctx = _make_context({
        "onboard_email": "u@example.com",
        "onboard_profile": {
            "candidate_name": "Иван",
            "search_keywords": ["менеджер"],
        },
    })
    with patch("src.auth.try_login", AsyncMock(return_value=True)):
        state = await bot.onboard_password(update, ctx)

    assert state == bot.ONBOARD_CONFIRM
    assert ctx.user_data["onboard_password"] == "correct-password"
    assert "onboard_pw_attempts" not in ctx.user_data
    update.message.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_onboard_password_failure_retries():
    update = _make_update("wrong")
    ctx = _make_context({
        "onboard_email": "u@example.com",
        "onboard_profile": {"candidate_name": "Иван", "search_keywords": ["x"]},
    })
    with patch("src.auth.try_login", AsyncMock(return_value=False)):
        state = await bot.onboard_password(update, ctx)

    assert state == bot.ONBOARD_PASSWORD
    assert ctx.user_data["onboard_pw_attempts"] == 1
    assert "onboard_password" not in ctx.user_data


@pytest.mark.asyncio
async def test_onboard_password_three_failures_abort():
    update = _make_update("wrong")
    ctx = _make_context({
        "onboard_email": "u@example.com",
        "onboard_profile": {"candidate_name": "Иван", "search_keywords": ["x"]},
        "onboard_pw_attempts": 2,
    })
    with patch("src.auth.try_login", AsyncMock(return_value=False)):
        state = await bot.onboard_password(update, ctx)

    assert state == ConversationHandler.END
    assert "onboard_password" not in ctx.user_data
    assert "onboard_pw_attempts" not in ctx.user_data


@pytest.mark.asyncio
async def test_onboard_password_empty_reasks():
    update = _make_update("")
    ctx = _make_context({
        "onboard_email": "u@example.com",
        "onboard_profile": {"candidate_name": "Иван", "search_keywords": ["x"]},
    })
    state = await bot.onboard_password(update, ctx)
    assert state == bot.ONBOARD_PASSWORD


@pytest.mark.asyncio
async def test_settings_save_password_success():
    update = _make_update("newpass", chat_id=456)
    ctx = _make_context({})
    with patch("src.auth.try_login", AsyncMock(return_value=True)), \
         patch("src.database.get_setting", AsyncMock(return_value="u@example.com")), \
         patch("src.database.set_setting", AsyncMock()) as set_setting:
        state = await bot.settings_save_password(update, ctx)

    assert state == ConversationHandler.END
    set_setting.assert_awaited_once_with("456", "rabota_password", "newpass")


@pytest.mark.asyncio
async def test_settings_save_password_failure_retries():
    update = _make_update("badpass", chat_id=456)
    ctx = _make_context({})
    with patch("src.auth.try_login", AsyncMock(return_value=False)), \
         patch("src.database.get_setting", AsyncMock(return_value="u@example.com")), \
         patch("src.database.set_setting", AsyncMock()) as set_setting:
        state = await bot.settings_save_password(update, ctx)

    assert state == bot.SETTINGS_PASSWORD
    assert ctx.user_data["settings_pw_attempts"] == 1
    set_setting.assert_not_awaited()


@pytest.mark.asyncio
async def test_settings_save_password_no_email_aborts():
    update = _make_update("pw", chat_id=456)
    ctx = _make_context({})
    with patch("src.database.get_setting", AsyncMock(return_value=None)):
        state = await bot.settings_save_password(update, ctx)
    assert state == ConversationHandler.END
