from functools import lru_cache
from ipaddress import ip_address
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    app_name: str = "Kerfuffle API"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/kerfuffle"
    environment: str = "development"
    access_code_hash_secret: str | None = None
    app_public_url: str = "http://localhost:5173"
    app_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    session_cookie_name: str = "kerfuffle_session"
    csrf_cookie_name: str = "kerfuffle_csrf"
    session_idle_minutes: int = 30
    session_absolute_hours: int = 12
    public_proxy_ip: str | None = None
    private_proxy_ip: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_use_tls: bool = True
    # Set only on the one-shot Alembic migration service, which connects as DB owner.
    database_migration_mode: bool = False

    @model_validator(mode="after")
    def require_production_configuration(self):
        if self.session_idle_minutes < 1 or self.session_absolute_hours < 1:
            raise ValueError("Session expiration settings must be positive")
        if not 1 <= self.smtp_port <= 65535:
            raise ValueError("SMTP_PORT must be between 1 and 65535")
        if self.environment.strip().lower() != "production":
            return self

        missing = []
        if not self.access_code_hash_secret or len(self.access_code_hash_secret) < 32:
            missing.append("ACCESS_CODE_HASH_SECRET (at least 32 characters)")
        if urlsplit(self.app_public_url).scheme.lower() != "https":
            missing.append("APP_PUBLIC_URL must use HTTPS")
        allowed_origins = {
            origin.strip().rstrip("/").lower()
            for origin in self.app_allowed_origins.split(",")
            if origin.strip()
        }
        public = urlsplit(self.app_public_url)
        public_origin = f"{public.scheme}://{public.netloc}".lower()
        if public_origin not in allowed_origins:
            missing.append("APP_ALLOWED_ORIGINS must include APP_PUBLIC_URL origin")
        if any(urlsplit(origin).scheme.lower() != "https" for origin in allowed_origins):
            missing.append("APP_ALLOWED_ORIGINS must use HTTPS in production")
        proxy_ips = (self.public_proxy_ip, self.private_proxy_ip)
        if any(not proxy_ip for proxy_ip in proxy_ips):
            missing.append("PUBLIC_PROXY_IP and PRIVATE_PROXY_IP must be configured")
        else:
            try:
                parsed_proxy_ips = tuple(ip_address(proxy_ip) for proxy_ip in proxy_ips)
            except ValueError:
                missing.append("PUBLIC_PROXY_IP and PRIVATE_PROXY_IP must be valid IP addresses")
            else:
                if parsed_proxy_ips[0] == parsed_proxy_ips[1]:
                    missing.append("PUBLIC_PROXY_IP and PRIVATE_PROXY_IP must be different")
        smtp_values = (
            self.smtp_host,
            self.smtp_user,
            self.smtp_password,
            self.smtp_from,
        )
        smtp_configured = all(smtp_values)
        if any(smtp_values) and not smtp_configured:
            missing.append(
                "SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SMTP_FROM "
                "must be configured together"
            )
        elif not smtp_configured:
            missing.append(
                "SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SMTP_FROM are required "
                "for administrator password recovery"
            )

        database_url = make_url(self.database_url)
        migration_owner_connection = (
            self.database_migration_mode and database_url.username == "postgres"
        )
        if (
            database_url.username in (None, "postgres") and not migration_owner_connection
        ) or not database_url.password:
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
