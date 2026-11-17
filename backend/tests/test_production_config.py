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


def test_production_manual_auth_links_allow_missing_smtp():
    settings = production_settings(
        smtp_host=None,
        smtp_user=None,
        smtp_password=None,
        smtp_from=None,
        manual_auth_links_enabled=True,
    )

    assert settings.manual_auth_links_enabled is True


def test_production_without_smtp_requires_explicit_manual_link_setting():
    with pytest.raises(ValidationError, match="MANUAL_AUTH_LINKS_ENABLED=true"):
        production_settings(
            smtp_host=None,
            smtp_user=None,
            smtp_password=None,
            smtp_from=None,
        )


def test_manual_auth_links_do_not_allow_partial_smtp_configuration():
    with pytest.raises(ValidationError, match="SMTP_HOST, SMTP_USER"):
        production_settings(
            smtp_host=None,
            manual_auth_links_enabled=True,
        )


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
