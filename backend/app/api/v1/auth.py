from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.core.auth import (
    clear_user_session_cookies,
    get_current_user,
    issue_user_session,
    require_same_origin,
    revoke_all_sessions,
    verify_login,
)
from app.core.config import Settings, get_settings
from app.core.network_access import effective_client_ip
from app.core.passwords import is_valid_email, normalize_email
from app.db.models import User
from app.db.session import get_db


router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = normalize_email(value)
        if not is_valid_email(value):
            raise ValueError("Укажите корректный email.")
        return value


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


def account_response(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "is_system_admin": user.is_system_admin,
    }


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request, settings)
    user = verify_login(
        session,
        payload.email,
        payload.password,
        effective_client_ip(request, settings),
        settings,
    )
    if user is None:
        raise HTTPException(status_code=401, detail="Неверный email или пароль.")
    issue_user_session(response, user, session, settings)
    return account_response(user)


@router.get("/me")
def current_account(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    return account_response(user)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    raw_token = request.cookies.get(settings.session_cookie_name)
    if raw_token:
        from app.core.passwords import hash_token
        from app.db.models import UserSession

        row = session.query(UserSession).filter_by(token_hash=hash_token(raw_token)).one_or_none()
        if row is not None and row.user_id == user.id:
            row.revoked_at = datetime.now(timezone.utc)
            session.commit()
    clear_user_session_cookies(response, settings)
    return {"ok": True}


@router.post("/logout-all")
def logout_all(
    response: Response,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    revoke_all_sessions(session, user.id)
    session.commit()
    clear_user_session_cookies(response, settings)
    return {"ok": True}


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from app.core.auth import _utcnow
    from app.core.passwords import hash_password, verify_password
    from app.db.models import UserSession

    if not user.password_hash or not verify_password(user.password_hash, payload.current_password):
        raise HTTPException(status_code=400, detail="Текущий пароль указан неверно.")
    try:
        user.password_hash = hash_password(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.query(UserSession).filter(
        UserSession.user_id == user.id,
        UserSession.revoked_at.is_(None),
    ).update({"revoked_at": _utcnow()}, synchronize_session=False)
    session.commit()
    clear_user_session_cookies(response, settings)
    return {"ok": True}
