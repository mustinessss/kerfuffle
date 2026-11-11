from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
