import re
import secrets
from hashlib import sha256

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


PASSWORD_HASHER = PasswordHasher()
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def is_valid_email(email: str) -> bool:
    return (
        email.isascii()
        and len(email) <= 254
        and EMAIL_PATTERN.fullmatch(email) is not None
    )


def validate_password(password: str) -> None:
    if len(password) < 12:
        raise ValueError("Пароль должен содержать не менее 12 символов.")
    if not any(char.islower() for char in password):
        raise ValueError("Добавьте в пароль строчную букву.")
    if not any(char.isupper() for char in password):
        raise ValueError("Добавьте в пароль заглавную букву.")
    if not any(char.isdigit() for char in password):
        raise ValueError("Добавьте в пароль цифру.")


def hash_password(password: str) -> str:
    validate_password(password)
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def hash_rate_limit_value(value: str, key: bytes) -> str:
    import hmac

    return hmac.new(key, value.encode("utf-8"), sha256).hexdigest()
