from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.permissions import require_event_access, require_station_access
from app.db.models import (
    Event,
    EventParticipant,
    Person,
    Score,
    ScoreAudit,
    Station,
    User,
)
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
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Reason must not be blank")
        return value


class ScoreAnnulment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Reason must not be blank")
        return value


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


def _score_response(score: Score) -> dict[str, int | bool]:
    return {
        "id": score.id,
        "event_participant_id": score.event_participant_id,
        "station_id": score.station_id,
        "points": score.points,
        "is_annulled": score.is_annulled,
    }


def _score_audit_response(audit: ScoreAudit, display_name: str) -> dict:
    return {
        "id": audit.id,
        "action": audit.action,
        "points_before": audit.points_before,
        "points_after": audit.points_after,
        "reason": audit.reason,
        "changed_by": display_name,
        "created_at": audit.created_at.isoformat(),
    }


def lookup_participant_record(
    station_id: int,
    payload: ParticipantLookup,
    session: Session,
):
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


def create_score_record(
    station_id: int,
    payload: ScoreCreate,
    session: Session,
):
    station = session.get(Station, station_id)
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")
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
    return lookup_participant_record(station_id, payload, session)


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
    return create_score_record(station_id, payload, session)


@router.patch("/scores/{score_id}", summary="Исправить оценку организатором")
def update_score(
    score_id: int,
    payload: ScoreUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    score = session.scalar(
        select(Score).where(Score.id == score_id).with_for_update()
    )
    if score is None:
        raise HTTPException(status_code=404, detail="Score not found")
    station = session.get(Station, score.station_id)
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")
    require_event_access(session, user, station.event_id, {"organizer"})
    _validate_points(payload.points, station)

    if score.is_annulled:
        raise HTTPException(status_code=409, detail="An annulled score cannot be corrected")
    if score.points == payload.points:
        raise HTTPException(status_code=422, detail="Corrected points must differ from the current score")

    previous_points = score.points
    score.points = payload.points
    session.add(
        ScoreAudit(
            score_id=score.id,
            changed_by_user_id=user.id,
            action="correction",
            points_before=previous_points,
            points_after=payload.points,
            reason=payload.reason,
        )
    )
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


@router.post(
    "/scores/{score_id}/annul",
    summary="Аннулировать оценку организатором",
)
def annul_score(
    score_id: int,
    payload: ScoreAnnulment,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    score = session.scalar(
        select(Score).where(Score.id == score_id).with_for_update()
    )
    if score is None:
        raise HTTPException(status_code=404, detail="Score not found")
    station = session.get(Station, score.station_id)
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")
    require_event_access(session, user, station.event_id, {"organizer"})
    if score.is_annulled:
        raise HTTPException(status_code=409, detail="Score is already annulled")

    score.is_annulled = True
    session.add(
        ScoreAudit(
            score_id=score.id,
            changed_by_user_id=user.id,
            action="annulment",
            points_before=score.points,
            points_after=score.points,
            reason=payload.reason,
        )
    )
    session.commit()
    session.refresh(score)
    return _score_response(score)


@router.get(
    "/events/{event_id}/scores",
    summary="История оценок мероприятия",
)
def list_event_scores(
    event_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    require_event_access(session, user, event_id, {"organizer"})
    rows = session.execute(
        select(Score, EventParticipant, Person, Station)
        .join(EventParticipant, EventParticipant.id == Score.event_participant_id)
        .join(Person, Person.id == EventParticipant.person_id)
        .join(Station, Station.id == Score.station_id)
        .where(EventParticipant.event_id == event_id)
        .order_by(Score.created_at.desc(), Score.id.desc())
    ).all()
    score_ids = [score.id for score, _, _, _ in rows]
    audit_by_score: dict[int, list[dict]] = {score_id: [] for score_id in score_ids}
    if score_ids:
        audit_rows = session.execute(
            select(ScoreAudit, User.display_name)
            .join(User, User.id == ScoreAudit.changed_by_user_id)
            .where(ScoreAudit.score_id.in_(score_ids))
            .order_by(ScoreAudit.created_at, ScoreAudit.id)
        )
        for audit, display_name in audit_rows:
            audit_by_score[audit.score_id].append(
                _score_audit_response(audit, display_name)
            )

    return [
        {
            **_score_response(score),
            "registration_number": registration.registration_number,
            "first_name": person.first_name,
            "last_name": person.last_name,
            "station_name": station.name,
            "created_at": score.created_at.isoformat(),
            "history": audit_by_score[score.id],
        }
        for score, registration, person, station in rows
    ]
