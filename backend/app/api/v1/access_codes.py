from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.participants import ParticipantCreate, register_participant_record
from app.api.v1.scores import (
    ParticipantLookup,
    ScoreCreate,
    create_score_record,
    lookup_participant_record,
)
from app.core.auth import get_current_user
from app.core.config import Settings, get_settings
from app.core.permissions import require_event_access
from app.db.models import (
    AccessCode,
    AccessCodeAttempt,
    AccessSession,
    Event,
    Station,
    User,
)
from app.db.session import get_db


router = APIRouter(tags=["Access codes"])
bearer_scheme = HTTPBearer(auto_error=False)
SESSION_LIFETIME = timedelta(hours=12)
ATTEMPT_WINDOW = timedelta(minutes=15)
ATTEMPTS_PER_WINDOW = 30
ACCESS_CODE_REGEX = r"^[A-HJ-NP-Z2-9]{8,16}$"
ACCESS_CODE_PATTERN = re.compile(ACCESS_CODE_REGEX)


def normalize_access_code(value: str) -> str:
    normalized = value.strip().upper()
    if not ACCESS_CODE_PATTERN.fullmatch(normalized):
        raise ValueError(
            "Access code must be 8 to 16 letters or digits, excluding I, O, 0, and 1"
        )
    return normalized


class AccessCodeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(pattern="^(registrar|station_operator)$")
    code: str = Field(min_length=8, max_length=16, pattern=ACCESS_CODE_REGEX)
    station_id: int | None = Field(default=None, gt=0)

    @field_validator("code", mode="before")
    @classmethod
    def validate_code(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return normalize_access_code(value)

    @model_validator(mode="after")
    def require_role_scope(self):
        if (self.role == "station_operator") != (self.station_id is not None):
            raise ValueError("A station code must name exactly one station")
        return self


class AccessCodeVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=8, max_length=128)

    @field_validator("code", mode="before")
    @classmethod
    def validate_code(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if ACCESS_CODE_PATTERN.fullmatch(normalized.upper()):
            return normalized.upper()
        if re.fullmatch(r"[A-Za-z0-9_-]{8,128}", normalized):
            return normalized
        raise ValueError("Access code has an invalid format")


def _secret_hash(value: str, secret: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def _required_secret(settings: Settings) -> str:
    if not settings.access_code_hash_secret or len(settings.access_code_hash_secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Access-code authentication is not configured",
        )
    return settings.access_code_hash_secret


def access_code_response(code: AccessCode, station_name: str | None = None) -> dict:
    return {
        "id": code.id,
        "event_id": code.event_id,
        "station_id": code.station_id,
        "station_name": station_name,
        "role": code.role,
        "label": code.label,
        "is_active": code.is_active,
        "created_at": code.created_at.isoformat(),
        "revoked_at": code.revoked_at.isoformat() if code.revoked_at else None,
    }


def get_access_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> tuple[AccessSession, AccessCode]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access code session required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    secret = _required_secret(settings)
    row = session.execute(
        select(AccessSession, AccessCode)
        .join(AccessCode, AccessCode.id == AccessSession.access_code_id)
        .where(
            AccessSession.token_hash == _secret_hash(credentials.credentials, secret),
            AccessCode.is_active.is_(True),
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access code session is invalid or revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_session, access_code = row
    expires_at = access_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access code session expired; enter the code again",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return access_session, access_code


@router.get(
    "/events/{event_id}/access-codes",
    summary="Список кодов доступа организатора",
)
def list_access_codes(
    event_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    require_event_access(session, user, event_id, {"organizer"})
    rows = session.execute(
        select(AccessCode, Station.name)
        .outerjoin(Station, Station.id == AccessCode.station_id)
        .where(AccessCode.event_id == event_id)
        .order_by(AccessCode.created_at.desc(), AccessCode.id.desc())
    )
    return [access_code_response(code, station_name) for code, station_name in rows]


@router.post(
    "/events/{event_id}/access-codes",
    status_code=status.HTTP_201_CREATED,
    summary="Создать код регистратора или площадки",
)
def create_access_code(
    event_id: int,
    payload: AccessCodeCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    secret = _required_secret(settings)
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    require_event_access(session, user, event_id, {"organizer"})
    station_name = None
    if payload.station_id is not None:
        station = session.get(Station, payload.station_id)
        if station is None or station.event_id != event_id:
            raise HTTPException(status_code=404, detail="Station not found in this event")
        station_name = station.name

    raw_code = payload.code
    secret_hash = _secret_hash(raw_code, secret)
    if session.scalar(select(AccessCode.id).where(AccessCode.secret_hash == secret_hash)):
        raise HTTPException(status_code=409, detail="This access code is already in use")

    access_code = AccessCode(
        event_id=event_id,
        station_id=payload.station_id,
        created_by_user_id=user.id,
        role=payload.role,
        label="Код регистратора" if payload.role == "registrar" else "Код площадки",
        secret_hash=secret_hash,
    )
    session.add(access_code)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if session.scalar(select(AccessCode.id).where(AccessCode.secret_hash == secret_hash)):
            raise HTTPException(
                status_code=409,
                detail="This access code is already in use",
            ) from exc
        raise
    session.refresh(access_code)
    return {**access_code_response(access_code, station_name), "code": raw_code}


@router.delete(
    "/access-codes/{code_id}",
    summary="Отключить код доступа",
)
def revoke_access_code(
    code_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    access_code = session.get(AccessCode, code_id)
    if access_code is None:
        raise HTTPException(status_code=404, detail="Access code not found")
    require_event_access(session, user, access_code.event_id, {"organizer"})
    if not access_code.is_active:
        raise HTTPException(status_code=409, detail="Access code is already disabled")
    access_code.is_active = False
    access_code.revoked_at = datetime.now(UTC)
    session.commit()
    return access_code_response(access_code)


@router.post(
    "/public/access/verify",
    summary="Проверить код регистратора или площадки",
)
def verify_access_code(
    payload: AccessCodeVerification,
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    secret = _required_secret(settings)
    client_ip = request.client.host if request.client else "unknown"
    ip_hash = _secret_hash(client_ip, secret)
    now = datetime.now(UTC)
    session.execute(
        delete(AccessCodeAttempt).where(
            AccessCodeAttempt.created_at < now - timedelta(days=1)
        )
    )
    attempts = session.scalar(
        select(func.count())
        .select_from(AccessCodeAttempt)
        .where(
            AccessCodeAttempt.ip_hash == ip_hash,
            AccessCodeAttempt.created_at >= now - ATTEMPT_WINDOW,
        )
    )
    session.add(AccessCodeAttempt(ip_hash=ip_hash))
    session.commit()
    if attempts >= ATTEMPTS_PER_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many code attempts. Try again later.",
        )

    access_code = session.scalar(
        select(AccessCode)
        .where(
            AccessCode.secret_hash == _secret_hash(payload.code, secret),
            AccessCode.is_active.is_(True),
        )
        .with_for_update()
    )
    if access_code is None:
        raise HTTPException(status_code=400, detail="Access code is invalid or disabled")
    access_token = secrets.token_urlsafe(32)
    expires_at = now + SESSION_LIFETIME
    access_session = AccessSession(
        access_code_id=access_code.id,
        token_hash=_secret_hash(access_token, secret),
        expires_at=expires_at,
    )
    session.add(access_session)
    session.commit()
    station = (
        session.get(Station, access_code.station_id)
        if access_code.station_id is not None
        else None
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_at": expires_at.isoformat(),
        "role": access_code.role,
        "event_id": access_code.event_id,
        "station": (
            {
                "id": station.id,
                "name": station.name,
                "score_min": station.score_min,
                "score_max": station.score_max,
                "score_step": station.score_step,
            }
            if station
            else None
        ),
    }


@router.post(
    "/public/access/register",
    status_code=status.HTTP_201_CREATED,
    summary="Зарегистрировать участника по коду мероприятия",
)
def register_with_access_code(
    payload: ParticipantCreate,
    access: tuple[AccessSession, AccessCode] = Depends(get_access_session),
    session: Session = Depends(get_db),
):
    _, code = access
    if code.role != "registrar":
        raise HTTPException(status_code=403, detail="Registration access required")
    return register_participant_record(code.event_id, payload, session)


@router.post(
    "/public/access/participant-lookup",
    summary="Найти участника по коду площадки",
)
def lookup_with_access_code(
    payload: ParticipantLookup,
    access: tuple[AccessSession, AccessCode] = Depends(get_access_session),
    session: Session = Depends(get_db),
):
    _, code = access
    if code.role != "station_operator" or code.station_id is None:
        raise HTTPException(status_code=403, detail="Station access required")
    return lookup_participant_record(code.station_id, payload, session)


@router.post(
    "/public/access/scores",
    status_code=status.HTTP_201_CREATED,
    summary="Начислить баллы по коду площадки",
)
def submit_score_with_access_code(
    payload: ScoreCreate,
    access: tuple[AccessSession, AccessCode] = Depends(get_access_session),
    session: Session = Depends(get_db),
):
    _, code = access
    if code.role != "station_operator" or code.station_id is None:
        raise HTTPException(status_code=403, detail="Station access required")
    return create_score_record(code.station_id, payload, session)
