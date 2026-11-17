import hmac
import ipaddress
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.passwords import (
    PASSWORD_HASHER,
    hash_password,
    hash_rate_limit_value,
    hash_token,
    is_valid_email,
    new_opaque_token,
    normalize_email,
    verify_password,
)
from app.db.models import AuthAttempt, User, UserSession
from app.db.session import get_db


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_ATTEMPT_LIMIT = 8
LOGIN_IP_ATTEMPT_LIMIT = 40
SESSION_TOUCH_INTERVAL = timedelta(minutes=1)
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash("not-a-real-user-password")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _origin(request: Request) -> str | None:
    value = request.headers.get("origin")
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
        return None
    return f"{parsed.scheme}://{parsed.netloc}".lower()


def _origin_is_allowed(request: Request, settings: Settings) -> bool:
    origin = _origin(request)
    if origin is None:
        return False

    allowed = {
        item.strip().rstrip("/").lower()
        for item in settings.app_allowed_origins.split(",")
        if item.strip()
    }
    public = urlsplit(settings.app_public_url)
    if public.scheme and public.netloc:
        allowed.add(f"{public.scheme}://{public.netloc}".lower())
    if origin in allowed:
        return True

    if settings.environment.strip().lower() != "production":
        request_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        if request_host and origin.endswith(f"://{request_host.lower()}"):
            return True
        hostname = urlsplit(origin).hostname
        if hostname == "localhost":
            return True
        if hostname:
            try:
                address = ipaddress.ip_address(hostname)
            except ValueError:
                return False
            return address.is_loopback or address.is_private or address.is_link_local
    return False


def require_same_origin(request: Request, settings: Settings) -> None:
    if not _origin_is_allowed(request, settings):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Запрос отклонён. Обновите страницу и повторите действие.",
        )


def _cookie_options(settings: Settings) -> dict[str, object]:
    return {
        "secure": settings.environment.strip().lower() == "production",
        "samesite": "lax",
        "path": "/",
    }


def issue_user_session(
    response: Response,
    user: User,
    session: Session,
    settings: Settings,
) -> None:
    now = _utcnow()
    session_token = new_opaque_token()
    csrf_token = new_opaque_token()
    expires_at = now + timedelta(hours=settings.session_absolute_hours)
    row = UserSession(
        user_id=user.id,
        token_hash=hash_token(session_token),
        csrf_token_hash=hash_token(csrf_token),
        last_activity_at=now,
        expires_at=expires_at,
    )
    user.last_login_at = now
    session.add(row)
    session.commit()
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        httponly=True,
        max_age=int(timedelta(hours=settings.session_absolute_hours).total_seconds()),
        **_cookie_options(settings),
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        httponly=False,
        max_age=int(timedelta(hours=settings.session_absolute_hours).total_seconds()),
        **_cookie_options(settings),
    )


def clear_user_session_cookies(response: Response, settings: Settings) -> None:
    for cookie_name in (settings.session_cookie_name, settings.csrf_cookie_name):
        response.delete_cookie(cookie_name, path="/", secure=settings.environment.strip().lower() == "production", samesite="lax")


def get_current_user(
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    if request.method.upper() not in SAFE_METHODS:
        require_same_origin(request, settings)

    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется войти в аккаунт.",
        )

    user_session = session.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_token(raw_token),
            UserSession.revoked_at.is_(None),
        )
    )
    now = _utcnow()
    if user_session is None:
        clear_user_session_cookies(response, settings)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия истекла. Войдите снова.")

    last_activity = user_session.last_activity_at
    expires_at = user_session.expires_at
    if last_activity.tzinfo is None:
        last_activity = last_activity.replace(tzinfo=timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if (
        expires_at <= now
        or last_activity + timedelta(minutes=settings.session_idle_minutes) <= now
    ):
        user_session.revoked_at = now
        session.commit()
        clear_user_session_cookies(response, settings)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия истекла. Войдите снова.")

    if request.method.upper() not in SAFE_METHODS:
        csrf_cookie = request.cookies.get(settings.csrf_cookie_name, "")
        csrf_header = request.headers.get("x-csrf-token", "")
        if (
            not csrf_cookie
            or not csrf_header
            or not hmac.compare_digest(csrf_cookie, csrf_header)
            or not hmac.compare_digest(hash_token(csrf_cookie), user_session.csrf_token_hash)
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Проверка безопасности запроса не пройдена.")

    user = session.get(User, user_session.user_id)
    if user is None or not user.is_active or user.password_hash is None:
        user_session.revoked_at = now
        session.commit()
        clear_user_session_cookies(response, settings)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Учётная запись недоступна.")

    if last_activity + SESSION_TOUCH_INTERVAL <= now:
        user_session.last_activity_at = now
        session.commit()
    return user


def create_initial_admin(session: Session, email: str, password: str, display_name: str | None = None) -> User:
    normalized_email = normalize_email(email)
    if not is_valid_email(normalized_email):
        raise ValueError("Укажите корректный email.")
    if session.scalar(select(User.id).where(User.is_system_admin.is_(True))) is not None:
        raise RuntimeError("Первый системный администратор уже создан.")
    password_hash = hash_password(password)
    existing = session.scalar(select(User).where(func.lower(User.email) == normalized_email))
    if existing is not None and existing.password_hash is not None:
        raise RuntimeError("Учётная запись с этим email уже активирована.")
    user = existing or User(
        email=normalized_email,
        display_name=(display_name or normalized_email).strip(),
        is_active=True,
    )
    user.email = normalized_email
    user.display_name = (display_name or user.display_name or normalized_email).strip()
    user.password_hash = password_hash
    user.is_system_admin = True
    user.is_active = True
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _attempt_hash(value: str, settings: Settings) -> str:
    key = (settings.access_code_hash_secret or "development-auth-rate-limit-key").encode()
    return hash_rate_limit_value(value, key)


def verify_login(
    session: Session,
    email: str,
    password: str,
    remote_ip: str,
    settings: Settings,
) -> User | None:
    normalized_email = normalize_email(email)
    email_hash = _attempt_hash(normalized_email, settings)
    ip_hash = _attempt_hash(remote_ip or "unknown", settings)
    since = _utcnow() - LOGIN_WINDOW
    email_attempts = session.scalar(
        select(func.count(AuthAttempt.id)).where(
            AuthAttempt.created_at >= since,
            AuthAttempt.succeeded.is_(False),
            AuthAttempt.email_hash == email_hash,
        )
    ) or 0
    ip_attempts = session.scalar(
        select(func.count(AuthAttempt.id)).where(
            AuthAttempt.created_at >= since,
            AuthAttempt.succeeded.is_(False),
            AuthAttempt.ip_hash == ip_hash,
        )
    ) or 0
    if email_attempts >= LOGIN_ATTEMPT_LIMIT or ip_attempts >= LOGIN_IP_ATTEMPT_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток входа. Попробуйте позже.",
            headers={"Retry-After": str(int(LOGIN_WINDOW.total_seconds()))},
        )

    user = session.scalar(select(User).where(func.lower(User.email) == normalized_email))
    stored_hash = user.password_hash if user and user.password_hash else DUMMY_PASSWORD_HASH
    password_matches = verify_password(stored_hash, password)
    valid = bool(user and user.is_active and user.password_hash and password_matches)
    if not valid:
        session.query(AuthAttempt).filter(AuthAttempt.created_at < _utcnow() - timedelta(days=1)).delete(
            synchronize_session=False
        )
        session.add(AuthAttempt(ip_hash=ip_hash, email_hash=email_hash, succeeded=False))
        session.commit()
        return None

    session.query(AuthAttempt).filter(
        AuthAttempt.ip_hash == ip_hash,
        AuthAttempt.email_hash == email_hash,
    ).delete(synchronize_session=False)
    return user


def revoke_all_sessions(session: Session, user_id: int) -> None:
    session.query(UserSession).filter(
        UserSession.user_id == user_id,
        UserSession.revoked_at.is_(None),
    ).update({"revoked_at": _utcnow()}, synchronize_session=False)
