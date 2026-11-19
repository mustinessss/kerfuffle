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
        "public_proxy_ip": "172.29.0.2",
        "private_proxy_ip": "172.30.0.2",
    }
    values.update(overrides)
    return Settings(**values)


def test_valid_production_configuration_is_accepted():
    assert production_settings().environment == "production"


def test_production_requires_smtp_for_admin_password_recovery():
    with pytest.raises(ValidationError, match="required for administrator password recovery"):
        production_settings(
            smtp_host=None,
            smtp_user=None,
            smtp_password=None,
            smtp_from=None,
        )


def test_production_rejects_partial_smtp_configuration():
    with pytest.raises(ValidationError, match="SMTP_HOST, SMTP_USER"):
        production_settings(
            smtp_host=None,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"public_proxy_ip": None},
        {"private_proxy_ip": "not-an-ip"},
        {"private_proxy_ip": "172.29.0.2"},
    ],
)
def test_production_requires_distinct_valid_ingress_proxy_ips(overrides):
    with pytest.raises(ValidationError, match="PUBLIC_PROXY_IP|PRIVATE_PROXY_IP"):
        production_settings(**overrides)


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



def test_production_migration_mode_allows_postgres_owner_only_for_migrations():
    settings = production_settings(
        database_url=(
            "postgresql+psycopg://postgres:strong-password"
            "@db.example.test:5432/kerfuffle?sslmode=verify-full"
        ),
        database_migration_mode=True,
    )

    assert settings.database_migration_mode is True


def test_production_migration_mode_does_not_allow_postgres_without_explicit_flag():
    with pytest.raises(ValidationError, match="dedicated non-default database role"):
        production_settings(
            database_url=(
                "postgresql+psycopg://postgres:strong-password"
                "@db.example.test:5432/kerfuffle?sslmode=verify-full"
            ),
        )
