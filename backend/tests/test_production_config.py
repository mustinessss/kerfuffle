import pytest
from pydantic import ValidationError

from app.core.config import Settings


def production_settings(**overrides):
    values = {
        "environment": "production",
        "database_url": (
            "postgresql+psycopg://kerfuffle_app:strong-password"
            "@db.example.test:5432/kerfuffle?sslmode=verify-full"
        ),
        "access_code_hash_secret": "x" * 48,
        "app_public_url": "https://kerfuffle.example.test",
        "app_allowed_origins": "https://kerfuffle.example.test",
        "smtp_host": "smtp.example.test",
        "smtp_user": "kerfuffle",
        "smtp_password": "smtp-secret",
        "smtp_from": "noreply@example.test",
    }
    values.update(overrides)
    return Settings(**values)


def test_valid_production_configuration_is_accepted():
    assert production_settings().environment == "production"


@pytest.mark.parametrize(
    "overrides",
    [
        {"access_code_hash_secret": "short"},
        {
            "app_public_url": "http://kerfuffle.example.test",
        },
        {"smtp_password": None},
        {
            "database_url": (
                "postgresql+psycopg://postgres:postgres"
                "@localhost:5432/kerfuffle"
            ),
        },
    ],
)
def test_incomplete_or_insecure_production_configuration_is_rejected(overrides):
    with pytest.raises(ValidationError, match="Invalid production configuration"):
        production_settings(**overrides)


def test_development_settings_remain_permissive():
    assert Settings(environment="development").environment == "development"
