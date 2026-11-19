import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import require_same_origin
from app.core.config import Settings, get_settings
from app.core.mailer import send_email, smtp_is_configured
from app.core.passwords import (
    hash_password,
    hash_token,
    is_valid_email,
    new_opaque_token,
    normalize_email,
    validate_password,
)
from app.db.models import (
    AuthAttempt,
    PasswordResetToken,
    User,
    UserSession,
)
from app.db.session import get_db


public_router = APIRouter(tags=["Account recovery"])
logger = logging.getLogger(__name__)
RESET_TTL = timedelta(minutes=30)


class ResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = normalize_email(value)
        if not is_valid_email(value):
            raise ValueError("Укажите корректный email.")
        return value


class ResetPassword(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=32, max_length=128)
    password: str = Field(min_length=12, max_length=1024)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_expired(value: datetime, now: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= now


@public_router.post("/public/password-reset/request", status_code=202)
def request_password_reset(
    payload: ResetRequest,
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request, settings)
    ip_hash = _auth_attempt_hash(request.client.host if request.client else "unknown", settings)
    email_hash = _auth_attempt_hash(payload.email, settings)
    since = _now() - timedelta(hours=1)
    email_attempts = session.scalar(
        select(func.count(AuthAttempt.id)).where(
            AuthAttempt.created_at >= since,
            AuthAttempt.email_hash == email_hash,
        )
    ) or 0
    ip_attempts = session.scalar(
        select(func.count(AuthAttempt.id)).where(
            AuthAttempt.created_at >= since,
            AuthAttempt.ip_hash == ip_hash,
        )
    ) or 0
    session.add(AuthAttempt(ip_hash=ip_hash, email_hash=email_hash, succeeded=False))
    session.commit()
    if email_attempts >= 5 or ip_attempts >= 20:
        return {"ok": True}
    if not smtp_is_configured(settings):
        return {"ok": True}
    account = session.scalar(
        select(User).where(
            func.lower(User.email) == payload.email,
            User.is_active.is_(True),
            User.is_system_admin.is_(True),
            User.password_hash.is_not(None),
        )
    )
    if account is not None:
        token = new_opaque_token()
        session.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == account.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.revoked_at.is_(None),
        ).update({"revoked_at": _now()}, synchronize_session=False)
        reset = PasswordResetToken(
            user_id=account.id,
            token_hash=hash_token(token),
            expires_at=_now() + RESET_TTL,
        )
        session.add(reset)
        session.commit()
        reset_url = (
            f"{settings.app_public_url.rstrip('/')}/reset-password"
            f"?token={quote(token, safe='')}"
        )
        try:
            send_email(
                settings,
                account.email or payload.email,
                "Сброс пароля Kerfuffle",
                f"Чтобы задать новый пароль, откройте ссылку:\n\n{reset_url}\n\n"
                "Ссылка действует 30 минут и может быть использована один раз.",
            )
        except (OSError, RuntimeError):
            reset.revoked_at = _now()
            session.commit()
            logger.exception("Could not send password reset email")
    return {"ok": True}


@public_router.post("/public/password-reset/complete")
def complete_password_reset(
    payload: ResetPassword,
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request, settings)
    try:
        validate_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    reset = session.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == hash_token(payload.token))
        .with_for_update()
    )
    now = _now()
    if (
        reset is None
        or reset.used_at is not None
        or reset.revoked_at is not None
        or _is_expired(reset.expires_at, now)
    ):
        raise HTTPException(status_code=400, detail="Ссылка для сброса пароля недействительна или истекла.")
    account = session.scalar(select(User).where(User.id == reset.user_id).with_for_update())
    if account is None or not account.is_active or not account.is_system_admin:
        raise HTTPException(status_code=400, detail="Ссылка для сброса пароля недействительна или истекла.")
    password_hash = hash_password(payload.password)
    account.password_hash = password_hash
    reset.used_at = now
    session.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == account.id,
        PasswordResetToken.id != reset.id,
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.revoked_at.is_(None),
    ).update({"revoked_at": now}, synchronize_session=False)
    session.query(UserSession).filter(
        UserSession.user_id == account.id,
        UserSession.revoked_at.is_(None),
    ).update({"revoked_at": now}, synchronize_session=False)
    session.commit()
    return {"ok": True}


def _auth_attempt_hash(value: str, settings: Settings) -> str:
    from app.core.passwords import hash_rate_limit_value

    return hash_rate_limit_value(
        value,
        (settings.access_code_hash_secret or "development-auth-rate-limit-key").encode(),
    )
