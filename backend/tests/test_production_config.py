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
        "oidc_issuer": "https://identity.example.test/realms/kerfuffle",
        "oidc_audience": "kerfuffle-api",
        "oidc_jwks_url": (
            "https://identity.example.test/realms/kerfuffle/"
            "protocol/openid-connect/certs"
        ),
        "access_code_hash_secret": "x" * 48,
        "keycloak_admin_base_url": "https://identity.example.test",
        "keycloak_admin_realm": "kerfuffle",
        "keycloak_admin_client_id": "kerfuffle-user-provisioner",
        "keycloak_admin_client_secret": "service-secret",
    }
    values.update(overrides)
    return Settings(**values)


def test_valid_production_configuration_is_accepted():
    assert production_settings().environment == "production"


@pytest.mark.parametrize(
    "overrides",
    [
        {"oidc_issuer": None},
        {"access_code_hash_secret": "short"},
        {"oidc_bootstrap_admin_subject": "bootstrap-user"},
        {"keycloak_admin_client_secret": None},
        {
            "oidc_issuer": "http://identity.example.test/realms/kerfuffle",
        },
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
