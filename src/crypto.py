from cryptography.fernet import Fernet, InvalidToken

from .config import settings

_fernet = Fernet(settings.fernet_key.encode() if isinstance(settings.fernet_key, str) else settings.fernet_key)

ENC_PREFIX = "enc:v1:"


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return plaintext
    token = _fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
    return ENC_PREFIX + token


def decrypt(ciphertext: str) -> str:
    if not ciphertext or not ciphertext.startswith(ENC_PREFIX):
        return ciphertext
    token = ciphertext[len(ENC_PREFIX):].encode("ascii")
    try:
        return _fernet.decrypt(token).decode("utf-8")
    except InvalidToken:
        raise ValueError("Не удалось расшифровать: неверный FERNET_KEY или повреждённые данные")


def generate_key() -> str:
    return Fernet.generate_key().decode("ascii")
