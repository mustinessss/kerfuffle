from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    app_name: str = "Kerfuffle API"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/kerfuffle"
    environment: str = "development"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_signing_algorithm: str = "RS256"
    oidc_bootstrap_admin_subject: str | None = None
    access_code_hash_secret: str | None = None
    keycloak_admin_base_url: str | None = None
    keycloak_admin_realm: str = "kerfuffle"
    keycloak_admin_client_id: str | None = None
    keycloak_admin_client_secret: str | None = None

    @field_validator("oidc_signing_algorithm")
    @classmethod
    def require_asymmetric_oidc_algorithm(cls, value: str) -> str:
        allowed = {
            "RS256",
            "RS384",
            "RS512",
            "PS256",
            "PS384",
            "PS512",
            "ES256",
            "ES384",
            "ES512",
            "EdDSA",
        }
        if value not in allowed:
            raise ValueError("OIDC signing algorithm must be an allowed asymmetric algorithm")
        return value

    @model_validator(mode="after")
    def require_production_configuration(self):
        if self.environment.strip().lower() != "production":
            return self

        missing = []
        if not self.oidc_issuer or not self.oidc_audience or not self.oidc_jwks_url:
            missing.append("OIDC_ISSUER, OIDC_AUDIENCE, OIDC_JWKS_URL")
        if not self.access_code_hash_secret or len(self.access_code_hash_secret) < 32:
            missing.append("ACCESS_CODE_HASH_SECRET (at least 32 characters)")
        if self.oidc_bootstrap_admin_subject:
            missing.append("OIDC_BOOTSTRAP_ADMIN_SUBJECT must be unset")
        if not all(
            (
                self.keycloak_admin_base_url,
                self.keycloak_admin_client_id,
                self.keycloak_admin_client_secret,
            )
        ):
            missing.append(
                "KEYCLOAK_ADMIN_BASE_URL, KEYCLOAK_ADMIN_CLIENT_ID, "
                "KEYCLOAK_ADMIN_CLIENT_SECRET"
            )

        for name, value in (
            ("OIDC_ISSUER", self.oidc_issuer),
            ("OIDC_JWKS_URL", self.oidc_jwks_url),
            ("KEYCLOAK_ADMIN_BASE_URL", self.keycloak_admin_base_url),
        ):
            if value and urlsplit(value).scheme.lower() != "https":
                missing.append(f"{name} must use HTTPS")

        database_url = make_url(self.database_url)
        if database_url.username in (None, "postgres") or not database_url.password:
            missing.append("DATABASE_URL must use a dedicated non-default database role")
        if database_url.host in (None, "localhost", "127.0.0.1", "::1"):
            missing.append("DATABASE_URL must point to a non-local production database")
        if database_url.query.get("sslmode") not in {
            "require",
            "verify-ca",
            "verify-full",
        }:
            missing.append("DATABASE_URL must set sslmode=require, verify-ca, or verify-full")

        if missing:
            raise ValueError("Invalid production configuration: " + "; ".join(missing))
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
