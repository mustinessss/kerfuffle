from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.permissions import require_event_access
from app.db.models import Event, Score, Station, User
from app.db.session import get_db


router = APIRouter(tags=["Stations"])


class StationCreate(BaseModel):
    name: str
    score_min: int = Field(ge=0)
    score_max: int = Field(ge=0)
    score_step: int = Field(gt=0)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Station name must not be blank")
        return value

    @model_validator(mode="after")
    def validate_score_scale(self):
        if self.score_max < self.score_min:
            raise ValueError("score_max must be greater than or equal to score_min")
        if (self.score_max - self.score_min) % self.score_step:
            raise ValueError("score range must be divisible by score_step")
        return self


class StationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    score_min: int | None = Field(default=None, ge=0)
    score_max: int | None = Field(default=None, ge=0)
    score_step: int | None = Field(default=None, gt=0)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Station name must not be blank")
        return value

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Station fields cannot be null")
        return self


def station_response(station: Station) -> dict[str, int | str]:
    return {
        "id": station.id,
        "event_id": station.event_id,
        "name": station.name,
        "score_min": station.score_min,
        "score_max": station.score_max,
        "score_step": station.score_step,
    }


def _postgres_error_code(error: IntegrityError) -> str | None:
    return getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)


@router.get(
    "/events/{event_id}/stations",
    summary="Список площадок мероприятия",
)
def list_stations(
    event_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    accesses = require_event_access(session, user, event_id)
    statement = select(Station).where(Station.event_id == event_id)
    if not any(access.role in {"organizer", "registrar"} for access in accesses):
        assigned_station_ids = [
            access.station_id
            for access in accesses
            if access.role == "station_operator" and access.station_id is not None
        ]
        statement = statement.where(Station.id.in_(assigned_station_ids))
    stations = session.scalars(statement.order_by(Station.id))
    return [station_response(station) for station in stations]


@router.post(
    "/events/{event_id}/stations",
    status_code=status.HTTP_201_CREATED,
    summary="Создать площадку",
)
def create_station(
    event_id: int,
    payload: StationCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    require_event_access(session, user, event_id, {"organizer"})

    station = Station(event_id=event_id, **payload.model_dump())
    session.add(station)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        if _postgres_error_code(error) == "23505":
            raise HTTPException(
                status_code=409,
                detail="A station with this name already exists in the event",
            ) from error
        raise
    session.refresh(station)
    return station_response(station)


@router.patch("/stations/{station_id}", summary="Изменить площадку")
def update_station(
    station_id: int,
    payload: StationUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    station = session.get(Station, station_id)
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")
    require_event_access(session, user, station.event_id, {"organizer"})

    updates = payload.model_dump(exclude_unset=True)
    scale_fields = {"score_min", "score_max", "score_step"}
    scale_changed = any(
        getattr(station, field) != value
        for field, value in updates.items()
        if field in scale_fields
    )
    prospective_scale = {
        "score_min": updates.get("score_min", station.score_min),
        "score_max": updates.get("score_max", station.score_max),
        "score_step": updates.get("score_step", station.score_step),
    }
    if prospective_scale["score_max"] < prospective_scale["score_min"]:
        raise HTTPException(status_code=422, detail="score_max must be >= score_min")
    if (
        prospective_scale["score_max"] - prospective_scale["score_min"]
    ) % prospective_scale["score_step"]:
        raise HTTPException(
            status_code=422,
            detail="score range must be divisible by score_step",
        )

    if scale_changed and session.scalar(
        select(Score.id).where(Score.station_id == station.id).limit(1)
    ):
        raise HTTPException(
            status_code=409,
            detail="Station scoring scale cannot be changed after scores exist",
        )

    for field, value in updates.items():
        setattr(station, field, value)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        code = _postgres_error_code(error)
        if code == "23505":
            raise HTTPException(
                status_code=409,
                detail="A station with this name already exists in the event",
            ) from error
        if scale_changed and code == "23514":
            raise HTTPException(
                status_code=409,
                detail="Station scoring scale cannot be changed after scores exist",
            ) from error
        raise
    session.refresh(station)
    return station_response(station)
