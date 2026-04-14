"""Пайплайн при провале auth.ensure_logged_in шлёт TG и выходит, не зовя scraper."""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from src import pipeline
from src.auth import LoginError


@asynccontextmanager
async def _fake_acquire(chat_id, save_on_exit=True):
    yield object()  # фиктивный контекст, ensure_logged_in его всё равно не использует (замокан)


@pytest.mark.asyncio
async def test_run_pipeline_for_user_login_fail(monkeypatch):
    send_text = AsyncMock()
    ensure_logged_in = AsyncMock(side_effect=LoginError("bad creds"))
    parse_all_keywords = AsyncMock()

    monkeypatch.setattr(pipeline.bot, "send_text", send_text)
    monkeypatch.setattr(pipeline.browser_pool, "acquire", _fake_acquire)
    monkeypatch.setattr(pipeline.auth, "ensure_logged_in", ensure_logged_in)
    monkeypatch.setattr(pipeline.scraper, "parse_all_keywords", parse_all_keywords)

    await pipeline.run_pipeline_for_user("42")

    ensure_logged_in.assert_awaited_once()
    parse_all_keywords.assert_not_awaited()
    # Первое — "Начинаю поиск", второе — уведомление об ошибке логина
    assert send_text.await_count == 2
    last_msg = send_text.await_args_list[-1].args[1]
    assert "rabota.by" in last_msg
    assert "/settings" in last_msg


@pytest.mark.asyncio
async def test_check_messages_for_user_login_fail(monkeypatch):
    send_text = AsyncMock()
    ensure_logged_in = AsyncMock(side_effect=LoginError("bad creds"))
    check_inbox = AsyncMock()

    monkeypatch.setattr(pipeline.bot, "send_text", send_text)
    monkeypatch.setattr(pipeline.browser_pool, "acquire", _fake_acquire)
    monkeypatch.setattr(pipeline.auth, "ensure_logged_in", ensure_logged_in)
    monkeypatch.setattr(pipeline.inbox, "check_inbox", check_inbox)

    await pipeline.check_messages_for_user("42")

    ensure_logged_in.assert_awaited_once()
    check_inbox.assert_not_awaited()
    send_text.assert_awaited_once()
    assert "rabota.by" in send_text.await_args.args[1]
