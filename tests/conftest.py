"""
Фикстуры для тестов.
Устанавливает env-переменные ДО импорта модулей проекта,
чтобы pydantic-settings не падал на отсутствующих переменных.
"""
import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

# Выставить env до любых импортов src.*
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token_123")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456789")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key_123")
os.environ.setdefault("RABOTA_EMAIL", "test@test.com")
os.environ.setdefault("RABOTA_PASSWORD", "testpass")
os.environ.setdefault("FERNET_KEY", "zmWtnB2u3i4kqUgrFKBYJBo8RDDhBnxGfvDr_jx0Pn4=")
os.environ.setdefault("SEARCH_QUERIES", "director,CEO,AI")
os.environ.setdefault("SEARCH_CITY", "Minsk")
os.environ.setdefault("MIN_RELEVANCE_SCORE", "60")
os.environ.setdefault("DB_PATH", "data/test_hunter.db")
os.environ.setdefault("SESSION_PATH", "data/test_session.json")


def _is_real_anthropic_api_key(value: str) -> bool:
    value = (value or "").strip()
    return bool(value) and not value.startswith("test_") and value != "sk-test"


def _resolve_anthropic_api_key() -> str:
    env_value = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if _is_real_anthropic_api_key(env_value):
        return env_value

    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return env_value

    file_value = (dotenv_values(env_path).get("ANTHROPIC_API_KEY") or "").strip()
    if _is_real_anthropic_api_key(file_value):
        return file_value

    return env_value


def pytest_addoption(parser):
    parser.addoption(
        "--live-api",
        action="store_true",
        default=False,
        help="run tests that call the real Anthropic API",
    )
    parser.addoption(
        "--live-web",
        action="store_true",
        default=False,
        help="run tests that call real external websites via Playwright/browser",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live_api: tests that call the real Anthropic API",
    )
    config.addinivalue_line(
        "markers",
        "live_web: tests that call real external websites via Playwright/browser",
    )


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "live_api" in item.keywords and not config.getoption("--live-api"):
            item.add_marker(pytest.mark.skip(
                reason="need --live-api to run tests that call the real Anthropic API",
            ))
        if "live_web" in item.keywords and not config.getoption("--live-web"):
            item.add_marker(pytest.mark.skip(
                reason="need --live-web to run tests that call real external websites",
            ))


@pytest.fixture
def tmp_db(tmp_path):
    """Return a path to a temporary database file."""
    return str(tmp_path / "test.db")


@pytest.fixture
async def init_db(tmp_db, monkeypatch):
    """Initialize a fresh test database."""
    monkeypatch.setattr("src.database._db_path", tmp_db)
    from src import database
    await database.init()
    return tmp_db


@pytest.fixture(scope="session")
def live_anthropic_api_key(pytestconfig):
    if not pytestconfig.getoption("--live-api"):
        pytest.skip("need --live-api to run tests that call the real Anthropic API")

    api_key = _resolve_anthropic_api_key()
    if not _is_real_anthropic_api_key(api_key):
        pytest.skip("real ANTHROPIC_API_KEY is not configured")

    return api_key


@pytest.fixture(scope="session")
def live_web_enabled(pytestconfig):
    if not pytestconfig.getoption("--live-web"):
        pytest.skip("need --live-web to run tests that call real external websites")

    return True
