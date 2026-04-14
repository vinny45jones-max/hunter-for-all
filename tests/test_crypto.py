import pytest

from src import crypto
from src.crypto import ENC_PREFIX, decrypt, encrypt


def test_round_trip():
    plaintext = "SuperSecret123!"
    ciphertext = encrypt(plaintext)
    assert ciphertext != plaintext
    assert ciphertext.startswith(ENC_PREFIX)
    assert decrypt(ciphertext) == plaintext


def test_empty_passes_through():
    assert encrypt("") == ""
    assert decrypt("") == ""


def test_decrypt_non_encrypted_returns_as_is():
    assert decrypt("plain_value") == "plain_value"


def test_generate_key_valid():
    key = crypto.generate_key()
    assert len(key) > 0
    from cryptography.fernet import Fernet
    Fernet(key.encode())


def test_invalid_token_raises():
    with pytest.raises(ValueError):
        decrypt(ENC_PREFIX + "not_a_valid_token")


@pytest.mark.asyncio
async def test_setting_encrypted_in_db(init_db):
    from src import database
    await database.set_setting("42", "rabota_password", "hunter2")

    import aiosqlite
    async with aiosqlite.connect(init_db) as db:
        row = await (await db.execute(
            "SELECT value FROM user_settings WHERE chat_id='42' AND key='rabota_password'"
        )).fetchone()
    assert row[0].startswith(ENC_PREFIX)
    assert "hunter2" not in row[0]

    assert await database.get_setting("42", "rabota_password") == "hunter2"


@pytest.mark.asyncio
async def test_setting_non_encrypted_key_plain(init_db):
    from src import database
    await database.set_setting("42", "search_city", "Минск")
    import aiosqlite
    async with aiosqlite.connect(init_db) as db:
        row = await (await db.execute(
            "SELECT value FROM user_settings WHERE chat_id='42' AND key='search_city'"
        )).fetchone()
    assert row[0] == "Минск"


@pytest.mark.asyncio
async def test_user_password_encrypted(init_db):
    from src import database
    await database.save_user(777, email="a@b.com", password="topsecret")

    import aiosqlite
    async with aiosqlite.connect(init_db) as db:
        row = await (await db.execute(
            "SELECT password FROM users WHERE telegram_id=777"
        )).fetchone()
    assert row[0].startswith(ENC_PREFIX)

    user = await database.get_user(777)
    assert user["password"] == "topsecret"
