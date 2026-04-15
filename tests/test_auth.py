"""Шаг 7 плана: unit-тесты для src.auth (без реального браузера)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src import auth, database


@pytest.mark.asyncio
async def test_is_authorised_true():
    page = MagicMock()
    page.query_selector = AsyncMock(return_value=MagicMock())
    assert await auth._is_authorised(page) is True


@pytest.mark.asyncio
async def test_is_authorised_false():
    page = MagicMock()
    page.query_selector = AsyncMock(return_value=None)
    assert await auth._is_authorised(page) is False


@pytest.mark.asyncio
async def test_is_authorised_swallows_exception():
    page = MagicMock()
    page.query_selector = AsyncMock(side_effect=RuntimeError("boom"))
    assert await auth._is_authorised(page) is False


@pytest.mark.asyncio
async def test_load_credentials_from_db(init_db):
    await database.set_setting("42", "rabota_email", "a@b.c")
    await database.set_setting("42", "rabota_password", "pw")
    email, password = await auth._load_credentials("42")
    assert (email, password) == ("a@b.c", "pw")


@pytest.mark.asyncio
async def test_load_credentials_fallback_to_settings(init_db, monkeypatch):
    monkeypatch.setattr(auth.settings, "rabota_email", "fallback@x.y")
    monkeypatch.setattr(auth.settings, "rabota_password", "fallback_pw")
    email, password = await auth._load_credentials("unknown-chat")
    assert email == "fallback@x.y"
    assert password == "fallback_pw"


@pytest.mark.asyncio
async def test_load_credentials_raises_when_missing(init_db, monkeypatch):
    monkeypatch.setattr(auth.settings, "rabota_email", "")
    monkeypatch.setattr(auth.settings, "rabota_password", "")
    with pytest.raises(auth.LoginError):
        await auth._load_credentials("no-one")


class _FakeAcquireCtx:
    """Async context manager эмулирующий browser_pool.acquire()."""
    def __init__(self, context):
        self._context = context

    async def __aenter__(self):
        return self._context

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _make_context_and_page():
    page = MagicMock()
    page.close = AsyncMock()
    page.query_selector = AsyncMock(return_value=MagicMock())  # authorised
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    return context, page


@pytest.mark.asyncio
async def test_try_login_success():
    context, page = _make_context_and_page()
    with patch("src.auth.browser_pool.acquire", return_value=_FakeAcquireCtx(context)), \
         patch("src.auth._perform_login", AsyncMock()) as perform, \
         patch("src.auth.browser_pool.save_context", AsyncMock()) as save_ctx:
        ok = await auth.try_login("42", "a@b.c", "pw")

    assert ok is True
    perform.assert_awaited_once()
    save_ctx.assert_awaited_once_with(context, "42")
    page.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_try_login_not_authorised_returns_false():
    context, page = _make_context_and_page()
    page.query_selector = AsyncMock(return_value=None)  # NOT authorised
    with patch("src.auth.browser_pool.acquire", return_value=_FakeAcquireCtx(context)), \
         patch("src.auth._perform_login", AsyncMock()), \
         patch("src.auth.browser_pool.save_context", AsyncMock()) as save_ctx:
        ok = await auth.try_login("42", "a@b.c", "pw")

    assert ok is False
    save_ctx.assert_not_awaited()


@pytest.mark.asyncio
async def test_try_login_swallows_exception():
    context, _ = _make_context_and_page()
    with patch("src.auth.browser_pool.acquire", return_value=_FakeAcquireCtx(context)), \
         patch("src.auth._perform_login", AsyncMock(side_effect=RuntimeError("x"))):
        ok = await auth.try_login("42", "a@b.c", "pw")
    assert ok is False


@pytest.mark.asyncio
async def test_ensure_logged_in_already_authorised():
    page = MagicMock()
    page.goto = AsyncMock()
    page.close = AsyncMock()
    page.url = "https://rabota.by/"  # уже не на логине
    page.query_selector = AsyncMock(return_value=MagicMock())  # authorised
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)

    with patch("src.auth._perform_login", AsyncMock()) as perform, \
         patch("src.auth.browser_pool.save_context", AsyncMock()) as save_ctx:
        await auth.ensure_logged_in(context, "42")

    perform.assert_not_awaited()
    save_ctx.assert_not_awaited()
    page.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_logged_in_performs_login(init_db):
    await database.set_setting("42", "rabota_email", "a@b.c")
    await database.set_setting("42", "rabota_password", "pw")

    page = MagicMock()
    page.goto = AsyncMock()
    page.close = AsyncMock()
    page.url = "https://rabota.by/account/login"  # не авторизован до login
    page.query_selector = AsyncMock(return_value=MagicMock())  # marker есть

    async def perform_side_effect(*args, **kwargs):
        page.url = "https://rabota.by/"  # после login ушли с /account/login

    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)

    with patch("src.auth._perform_login", AsyncMock(side_effect=perform_side_effect)) as perform, \
         patch("src.auth.browser_pool.save_context", AsyncMock()) as save_ctx:
        await auth.ensure_logged_in(context, "42")

    perform.assert_awaited_once()
    save_ctx.assert_awaited_once_with(context, "42")


@pytest.mark.asyncio
async def test_ensure_logged_in_raises_on_failure(init_db):
    await database.set_setting("42", "rabota_email", "a@b.c")
    await database.set_setting("42", "rabota_password", "pw")

    page = MagicMock()
    page.goto = AsyncMock()
    page.close = AsyncMock()
    page.url = "https://rabota.by/account/login"  # всегда на странице логина
    page.query_selector = AsyncMock(return_value=None)  # всегда не авторизован
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)

    with patch("src.auth._perform_login", AsyncMock()), \
         patch("src.auth.browser_pool.save_context", AsyncMock()):
        with pytest.raises(auth.LoginError):
            await auth.ensure_logged_in(context, "42")
