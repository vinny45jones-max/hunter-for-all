"""Шаг 6 плана: re-registration (/start для существующего юзера)."""
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src import bot, database, browser_pool
from telegram.ext import ConversationHandler


def _make_update(chat_id: int = 123, user_id: int = 999):
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_chat.id = chat_id
    update.effective_user.id = user_id
    # CallbackQuery fields (used by onboard_* callbacks)
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_reply_markup = AsyncMock()
    update.callback_query.message = MagicMock()
    update.callback_query.message.chat_id = chat_id
    update.callback_query.message.reply_text = AsyncMock()
    return update


def _make_context():
    ctx = MagicMock()
    ctx.user_data = {}
    return ctx


@pytest.mark.asyncio
async def test_cmd_start_registered_shows_choice():
    update = _make_update()
    with patch("src.database.is_user_registered", AsyncMock(return_value=True)):
        state = await bot.cmd_start(update, _make_context())
    assert state == bot.ONBOARD_RESTART_CONFIRM
    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.call_args
    assert "reply_markup" in kwargs


@pytest.mark.asyncio
async def test_cmd_start_not_registered_starts_onboarding():
    update = _make_update()
    with patch("src.database.is_user_registered", AsyncMock(return_value=False)):
        state = await bot.cmd_start(update, _make_context())
    assert state == bot.ONBOARD_RESUME


@pytest.mark.asyncio
async def test_onboard_continue_ends():
    state = await bot.onboard_continue(_make_update(), _make_context())
    assert state == ConversationHandler.END


@pytest.mark.asyncio
async def test_onboard_restart_asks_confirm():
    state = await bot.onboard_restart(_make_update(), _make_context())
    assert state == bot.ONBOARD_RESTART_CONFIRM


@pytest.mark.asyncio
async def test_onboard_restart_yes_wipes_and_starts():
    update = _make_update(chat_id=777, user_id=555)
    with patch("src.database.wipe_user", AsyncMock()) as wipe_user, \
         patch("src.browser_pool.wipe_session") as wipe_session:
        state = await bot.onboard_restart_yes(update, _make_context())

    wipe_user.assert_awaited_once_with("777", telegram_id=555)
    wipe_session.assert_called_once_with("777")
    assert state == bot.ONBOARD_RESUME


@pytest.mark.asyncio
async def test_onboard_restart_no_ends():
    state = await bot.onboard_restart_no(_make_update(), _make_context())
    assert state == ConversationHandler.END


# ─── database/browser_pool low-level ─────────────────

@pytest.mark.asyncio
async def test_wipe_user_removes_settings(tmp_path, monkeypatch):
    db_path = str(tmp_path / "wipe.db")
    monkeypatch.setattr(database, "_db_path", db_path)
    await database.init()

    cid = "42"
    await database.set_setting(cid, "candidate_name", "Тест")
    await database.set_setting(cid, "rabota_email", "a@b.c")

    assert await database.is_user_registered(cid) is True

    await database.wipe_user(cid, telegram_id=123)
    assert await database.is_user_registered(cid) is False
    assert await database.get_setting(cid, "candidate_name") is None


def test_wipe_session_removes_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(browser_pool.settings, "sessions_dir", str(tmp_path))
    chat_dir = tmp_path / "99"
    chat_dir.mkdir()
    (chat_dir / "storage_state.json").write_text("{}")

    browser_pool.wipe_session("99")
    assert not chat_dir.exists()


def test_wipe_session_missing_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(browser_pool.settings, "sessions_dir", str(tmp_path))
    browser_pool.wipe_session("does-not-exist")  # не падает
