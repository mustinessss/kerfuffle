import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_same_origin, revoke_all_sessions
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
    AccountInvitation,
    Event,
    EventAccess,
    PasswordResetToken,
    Station,
    User,
    UserSession,
)
from app.db.session import get_db


router = APIRouter(prefix="/system-admin", tags=["System administration"])
public_router = APIRouter(tags=["Account recovery"])
logger = logging.getLogger(__name__)
INVITATION_TTL = timedelta(hours=24)
RESET_TTL = timedelta(minutes=30)


class InvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = normalize_email(value)
        if not is_valid_email(value):
            raise ValueError("Укажите корректный email.")
        return value


class InvitationAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=32, max_length=128)
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=1024)

    @field_validator("display_name")
    @classmethod
    def valid_display_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Укажите имя.")
        return value


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


def _require_system_admin(user: User) -> None:
    if not user.is_system_admin:
        raise HTTPException(status_code=403, detail="Требуются права системного администратора.")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_expired(value: datetime, now: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= now


def _invitation_status(invitation: AccountInvitation, now: datetime) -> str:
    if invitation.used_at:
        return "used"
    if invitation.revoked_at:
        return "revoked"
    if _is_expired(invitation.expires_at, now):
        return "expired"
    return "sent" if invitation.sent_at else "pending"


def _send_or_expose_invitation(
    invitation: AccountInvitation,
    token: str,
    session: Session,
    settings: Settings,
) -> str | None:
    invite_url = (
        f"{settings.app_public_url.rstrip('/')}/accept-invitation"
        f"?token={quote(token, safe='')}"
    )
    if smtp_is_configured(settings):
        try:
            send_email(
                settings,
                invitation.email,
                "Приглашение в Kerfuffle",
                f"Чтобы активировать аккаунт держателя площадки, откройте ссылку:\n\n{invite_url}\n\n"
                "Ссылка действует 24 часа и может быть использована один раз.",
            )
        except (OSError, RuntimeError) as exc:
            invitation.revoked_at = _now()
            session.commit()
            raise HTTPException(
                status_code=503,
                detail="Не удалось отправить приглашение. Проверьте SMTP и создайте новое приглашение.",
            ) from exc
        invitation.sent_at = _now()
        session.commit()
        return None

    if (
        settings.environment.strip().lower() == "production"
        and not settings.manual_auth_links_enabled
    ):
        invitation.revoked_at = _now()
        session.commit()
        raise HTTPException(
            status_code=503,
            detail=(
                "Настройте SMTP или включите ручную выдачу ссылок "
                "системному администратору."
            ),
        )

    invitation.sent_at = _now()
    session.commit()
    return invite_url


@router.get("/users")
def list_users(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    _require_system_admin(user)
    users = session.scalars(select(User).order_by(User.created_at, User.id))
    result = []
    for account in users:
        accesses = session.scalars(
            select(EventAccess).where(EventAccess.user_id == account.id).order_by(EventAccess.event_id)
        )
        result.append(
            {
                "id": account.id,
                "email": account.email,
                "display_name": account.display_name,
                "is_active": account.is_active,
                "is_system_admin": account.is_system_admin,
                "last_login_at": account.last_login_at,
                "events": [
                    {
                        "event_id": access.event_id,
                        "role": access.role,
                        "station_id": access.station_id,
                    }
                    for access in accesses
                    if access.role == "station_operator"
                ],
            }
        )
    return result


@router.post("/invitations", status_code=status.HTTP_201_CREATED)
def create_invitation(
    payload: InvitationCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    _require_system_admin(user)
    normalized_email = payload.email
    existing_user = session.scalar(
        select(User).where(func.lower(User.email) == normalized_email)
    )
    if existing_user and existing_user.is_active and existing_user.password_hash:
        raise HTTPException(status_code=409, detail="Для этого email уже существует активный аккаунт.")

    active_invitation = session.scalar(
        select(AccountInvitation).where(
            AccountInvitation.email == normalized_email,
            AccountInvitation.used_at.is_(None),
            AccountInvitation.revoked_at.is_(None),
            AccountInvitation.expires_at > _now(),
        )
    )
    if active_invitation is not None:
        active_invitation.revoked_at = _now()

    token = new_opaque_token()
    invitation = AccountInvitation(
        email=normalized_email,
        token_hash=hash_token(token),
        created_by_user_id=user.id,
        expires_at=_now() + INVITATION_TTL,
    )
    session.add(invitation)
    session.commit()
    try:
        invitation_url = _send_or_expose_invitation(
            invitation, token, session, settings
        )
    except HTTPException:
        raise
    return {
        "id": invitation.id,
        "email": invitation.email,
        "status": _invitation_status(invitation, _now()),
        "expires_at": invitation.expires_at,
        "invitation_url": invitation_url,
        "delivery_method": "email" if smtp_is_configured(settings) else "manual",
    }


@router.get("/invitations")
def list_invitations(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    _require_system_admin(user)
    now = _now()
    return [
        {
            "id": invitation.id,
            "email": invitation.email,
            "status": _invitation_status(invitation, now),
            "created_at": invitation.created_at,
            "expires_at": invitation.expires_at,
            "sent_at": invitation.sent_at,
        }
        for invitation in session.scalars(
            select(AccountInvitation).order_by(AccountInvitation.created_at.desc())
        )
    ]


@router.post("/invitations/{invitation_id}/revoke")
def revoke_invitation(
    invitation_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    _require_system_admin(user)
    invitation = session.get(AccountInvitation, invitation_id)
    if invitation is None:
        raise HTTPException(status_code=404, detail="Приглашение не найдено.")
    if invitation.used_at is not None:
        raise HTTPException(status_code=409, detail="Приглашение уже использовано.")
    if invitation.revoked_at is None:
        invitation.revoked_at = _now()
        session.commit()
    return {"ok": True}


@router.post("/invitations/{invitation_id}/resend", status_code=status.HTTP_201_CREATED)
def resend_invitation(
    invitation_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    _require_system_admin(user)
    invitation = session.get(AccountInvitation, invitation_id)
    if invitation is None:
        raise HTTPException(status_code=404, detail="Приглашение не найдено.")
    if invitation.used_at is not None:
        raise HTTPException(status_code=409, detail="Приглашение уже использовано.")
    invitation.revoked_at = _now()
    session.commit()
    return create_invitation(
        InvitationCreate(email=invitation.email),
        user,
        session,
        settings,
    )


@public_router.post("/public/invitations/accept")
def accept_invitation(
    payload: InvitationAccept,
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request, settings)
    try:
        validate_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    invitation = session.scalar(
        select(AccountInvitation)
        .where(AccountInvitation.token_hash == hash_token(payload.token))
        .with_for_update()
    )
    now = _now()
    if (
        invitation is None
        or invitation.sent_at is None
        or invitation.used_at is not None
        or invitation.revoked_at is not None
        or _is_expired(invitation.expires_at, now)
    ):
        raise HTTPException(status_code=400, detail="Ссылка приглашения недействительна или истекла.")

    account = session.scalar(
        select(User)
        .where(func.lower(User.email) == invitation.email)
        .with_for_update()
    )
    if account is not None and account.is_system_admin:
        raise HTTPException(status_code=409, detail="Этот адрес уже связан с административной учётной записью.")
    if account is not None and account.password_hash is not None and account.is_active:
        raise HTTPException(status_code=409, detail="Аккаунт по этому приглашению уже активирован.")
    password_hash = hash_password(payload.password)

    if account is None:
        account = User(
            email=invitation.email,
            display_name=payload.display_name,
            is_active=True,
        )
        session.add(account)
    else:
        account.email = invitation.email
        account.display_name = payload.display_name
        account.is_active = True
    account.password_hash = password_hash
    invitation.used_at = now
    session.query(AccountInvitation).filter(
        AccountInvitation.email == invitation.email,
        AccountInvitation.id != invitation.id,
        AccountInvitation.used_at.is_(None),
        AccountInvitation.revoked_at.is_(None),
    ).update({"revoked_at": now}, synchronize_session=False)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Приглашение уже было использовано.") from exc
    return {"ok": True, "email": account.email}


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
    if account is None or not account.is_active:
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


@router.post("/users/{user_id}/block")
def block_user(
    user_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    _require_system_admin(user)
    account = session.get(User, user_id)
    if account is None or account.is_system_admin:
        raise HTTPException(status_code=404, detail="Пользователь не найден.")
    if account.id == user.id:
        raise HTTPException(status_code=409, detail="Нельзя заблокировать собственную учётную запись.")
    account.is_active = False
    revoke_all_sessions(session, account.id)
    session.commit()
    return {"ok": True}


@router.post("/users/{user_id}/unblock")
def unblock_user(
    user_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    _require_system_admin(user)
    account = session.get(User, user_id)
    if account is None or account.is_system_admin:
        raise HTTPException(status_code=404, detail="Пользователь не найден.")
    account.is_active = True
    session.commit()
    return {"ok": True}


@router.post("/users/{user_id}/password-reset-link")
def create_manual_password_reset_link(
    user_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    _require_system_admin(user)
    if (
        settings.environment.strip().lower() == "production"
        and (
            not settings.manual_auth_links_enabled
            or smtp_is_configured(settings)
        )
    ):
        raise HTTPException(status_code=404, detail="Страница не найдена.")
    account = session.get(User, user_id)
    if account is None or not account.is_active or not account.email:
        raise HTTPException(status_code=404, detail="Активный пользователь не найден.")
    token = new_opaque_token()
    session.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == account.id,
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.revoked_at.is_(None),
    ).update({"revoked_at": _now()}, synchronize_session=False)
    session.add(
        PasswordResetToken(
            user_id=account.id,
            token_hash=hash_token(token),
            expires_at=_now() + RESET_TTL,
        )
    )
    session.commit()
    reset_url = (
        f"{settings.app_public_url.rstrip('/')}/reset-password"
        f"?token={quote(token, safe='')}"
    )
    return {"reset_url": reset_url, "expires_in_minutes": int(RESET_TTL.total_seconds() // 60)}


@router.put("/users/{user_id}/events/{event_id}/stations/{station_id}")
def assign_station_operator_to_station(
    user_id: int,
    event_id: int,
    station_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    _require_system_admin(user)
    account = session.get(User, user_id)
    event = session.get(Event, event_id)
    if account is None or account.is_system_admin or not account.is_active:
        raise HTTPException(status_code=404, detail="Активный пользователь не найден.")
    if event is None:
        raise HTTPException(status_code=404, detail="Мероприятие не найдено.")
    station = session.get(Station, station_id)
    if station is None or station.event_id != event.id:
        raise HTTPException(status_code=404, detail="Площадка не найдена.")
    access = session.scalar(
        select(EventAccess).where(
            EventAccess.user_id == account.id,
            EventAccess.event_id == event.id,
            EventAccess.role == "station_operator",
            EventAccess.station_id == station.id,
        )
    )
    if access is None:
        session.add(
            EventAccess(
                user_id=account.id,
                event_id=event.id,
                role="station_operator",
                station_id=station.id,
            )
        )
        session.commit()
    return {"ok": True}


@router.delete("/users/{user_id}/events/{event_id}/stations/{station_id}")
def unassign_station_operator_from_station(
    user_id: int,
    event_id: int,
    station_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    _require_system_admin(user)
    access = session.scalar(
        select(EventAccess).where(
            EventAccess.user_id == user_id,
            EventAccess.event_id == event_id,
            EventAccess.role == "station_operator",
            EventAccess.station_id == station_id,
        )
    )
    if access is not None:
        session.delete(access)
        session.commit()
    return {"ok": True}
