from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.permissions import require_event_access, require_station_access
from app.db.models import EventParticipant, Person, Score, Station, User
from app.db.session import get_db


router = APIRouter(tags=["Scores"])


class ParticipantLookup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    qr_token: UUID | None = None
    registration_number: str | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def require_exactly_one_lookup_value(self):
        if (self.qr_token is None) == (self.registration_number is None):
            raise ValueError("Provide exactly one of qr_token or registration_number")
        if self.registration_number is not None:
            self.registration_number = self.registration_number.strip()
            if not self.registration_number:
                raise ValueError("Registration number must not be blank")
        return self


class ScoreCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_participant_id: int = Field(gt=0)
    points: int = Field(ge=0)


class ScoreUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    points: int = Field(ge=0)


def _validate_points(points: int, station: Station) -> None:
    if (
        points < station.score_min
        or points > station.score_max
        or (points - station.score_min) % station.score_step
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Points must be between {station.score_min} and {station.score_max} "
                f"in steps of {station.score_step}"
            ),
        )


def _postgres_error_code(error: IntegrityError) -> str | None:
    return getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)


def _is_unique_violation(error: IntegrityError) -> bool:
    return (
        _postgres_error_code(error) == "23505"
        or "UNIQUE constraint failed" in str(error.orig)
    )


def _score_response(score: Score) -> dict[str, int]:
    return {
        "id": score.id,
        "event_participant_id": score.event_participant_id,
        "station_id": score.station_id,
        "points": score.points,
    }


@router.post(
    "/stations/{station_id}/participants/lookup",
    summary="Найти участника на назначенной площадке",
)
def lookup_participant(
    station_id: int,
    payload: ParticipantLookup,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    require_station_access(
        session, user, station_id, {"station_operator", "organizer"}
    )
    station = session.get(Station, station_id)
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")

    lookup = (
        EventParticipant.qr_token == payload.qr_token
        if payload.qr_token is not None
        else EventParticipant.registration_number == payload.registration_number
    )
    row = session.execute(
        select(EventParticipant, Person)
        .join(Person, Person.id == EventParticipant.person_id)
        .where(
            EventParticipant.event_id == station.event_id,
            lookup,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Participant not found")
    registration, person = row
    score = session.scalar(
        select(Score).where(
            Score.event_participant_id == registration.id,
            Score.station_id == station.id,
        )
    )
    return {
        "event_participant_id": registration.id,
        "registration_number": registration.registration_number,
        "first_name": person.first_name,
        "last_name": person.last_name,
        "already_scored": score is not None,
        "score": _score_response(score) if score is not None else None,
    }


@router.post(
    "/stations/{station_id}/scores",
    status_code=status.HTTP_201_CREATED,
    summary="Выставить оценку на площадке",
)
def create_score(
    station_id: int,
    payload: ScoreCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    require_station_access(
        session, user, station_id, {"station_operator", "organizer"}
    )
    station = session.get(Station, station_id)
    registration = session.get(EventParticipant, payload.event_participant_id)
    if registration is None or registration.event_id != station.event_id:
        raise HTTPException(status_code=404, detail="Participant not found")
    _validate_points(payload.points, station)

    score = Score(
        event_participant_id=registration.id,
        station_id=station.id,
        points=payload.points,
    )
    session.add(score)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        if _is_unique_violation(error):
            raise HTTPException(
                status_code=409,
                detail="A score already exists for this participant at this station",
            ) from error
        if _postgres_error_code(error) == "23514":
            raise HTTPException(
                status_code=422,
                detail="Participant, station or points do not match",
            ) from error
        raise
    session.refresh(score)
    return _score_response(score)


@router.patch("/scores/{score_id}", summary="Исправить оценку организатором")
def update_score(
    score_id: int,
    payload: ScoreUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    score = session.get(Score, score_id)
    if score is None:
        raise HTTPException(status_code=404, detail="Score not found")
    station = session.get(Station, score.station_id)
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")
    require_event_access(session, user, station.event_id, {"organizer"})
    _validate_points(payload.points, station)

    score.points = payload.points
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        if _postgres_error_code(error) == "23514":
            raise HTTPException(
                status_code=422,
                detail="Points do not match the station scoring scale",
            ) from error
        raise
    session.refresh(score)
    return _score_response(score)
