from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.permissions import require_event_access
from app.db.models import (
    Event,
    EventParticipant,
    RouteSheet,
    RouteSheetStation,
    Station,
    User,
)
from app.db.session import get_db


router = APIRouter(tags=["Route sheets"])


class RouteSheetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    capacity: int | None = Field(default=None, gt=0)
    station_ids: list[int] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Route sheet name must not be blank")
        return value

    @field_validator("station_ids")
    @classmethod
    def station_ids_must_be_unique_and_positive(cls, value: list[int]) -> list[int]:
        if any(station_id <= 0 for station_id in value):
            raise ValueError("Station IDs must be positive")
        if len(set(value)) != len(value):
            raise ValueError("Station IDs must be unique")
        return value

def list_route_sheets_for_event(event_id: int, session: Session) -> list[dict]:
    sheets = list(
        session.scalars(
            select(RouteSheet)
            .where(RouteSheet.event_id == event_id)
            .order_by(RouteSheet.name, RouteSheet.id)
        )
    )
    if not sheets:
        return []

    sheet_ids = [sheet.id for sheet in sheets]
    stations_by_sheet: dict[int, list[dict[str, int | str]]] = {
        sheet_id: [] for sheet_id in sheet_ids
    }
    station_rows = session.execute(
        select(RouteSheetStation.route_sheet_id, Station.id, Station.name)
        .join(Station, Station.id == RouteSheetStation.station_id)
        .where(RouteSheetStation.route_sheet_id.in_(sheet_ids))
        .order_by(Station.name, Station.id)
    )
    for sheet_id, station_id, station_name in station_rows:
        stations_by_sheet[sheet_id].append(
            {"id": station_id, "name": station_name}
        )

    counts = dict(
        session.execute(
            select(EventParticipant.route_sheet_id, func.count())
            .where(EventParticipant.route_sheet_id.in_(sheet_ids))
            .group_by(EventParticipant.route_sheet_id)
        ).all()
    )
    return [
        {
            "id": sheet.id,
            "event_id": sheet.event_id,
            "name": sheet.name,
            "capacity": sheet.capacity,
            "registered_count": counts.get(sheet.id, 0),
            "stations": stations_by_sheet[sheet.id],
        }
        for sheet in sheets
    ]


def _postgres_error_code(error: IntegrityError) -> str | None:
    return getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)


@router.get(
    "/events/{event_id}/route-sheets",
    summary="Список маршрутных листов мероприятия",
)
def list_route_sheets(
    event_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    require_event_access(session, user, event_id, {"organizer", "registrar"})
    return list_route_sheets_for_event(event_id, session)


@router.post(
    "/events/{event_id}/route-sheets",
    status_code=status.HTTP_201_CREATED,
    summary="Создать маршрутный лист мероприятия",
)
def create_route_sheet(
    event_id: int,
    payload: RouteSheetCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    event = session.scalar(
        select(Event).where(Event.id == event_id).with_for_update()
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    require_event_access(session, user, event_id, {"organizer"})

    found_station_ids = set(
        session.scalars(
            select(Station.id).where(
                Station.event_id == event_id,
                Station.id.in_(payload.station_ids),
            )
        )
    )
    if found_station_ids != set(payload.station_ids):
        raise HTTPException(
            status_code=404,
            detail="Every route sheet station must belong to this event",
        )

    sheet = RouteSheet(
        event_id=event_id,
        name=payload.name,
        capacity=payload.capacity,
    )
    session.add(sheet)
    try:
        session.flush()
        session.add_all(
            RouteSheetStation(
                route_sheet_id=sheet.id,
                event_id=event_id,
                station_id=station_id,
            )
            for station_id in payload.station_ids
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        if _postgres_error_code(error) == "23505":
            raise HTTPException(
                status_code=409,
                detail="A route sheet with this name already exists in the event",
            ) from error
        raise
    return next(
        item
        for item in list_route_sheets_for_event(event_id, session)
        if item["id"] == sheet.id
    )


@router.delete(
    "/route-sheets/{route_sheet_id}",
    summary="Удалить маршрутный лист без регистраций",
)
def delete_route_sheet(
    route_sheet_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    existing_sheet = session.get(RouteSheet, route_sheet_id)
    if existing_sheet is None:
        raise HTTPException(status_code=404, detail="Route sheet not found")

    event = session.scalar(
        select(Event)
        .where(Event.id == existing_sheet.event_id)
        .with_for_update()
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    require_event_access(session, user, event.id, {"organizer"})
    sheet = session.scalar(
        select(RouteSheet)
        .where(RouteSheet.id == route_sheet_id)
        .with_for_update()
    )
    if sheet is None:
        raise HTTPException(status_code=404, detail="Route sheet not found")

    if session.scalar(
        select(EventParticipant.id)
        .where(EventParticipant.route_sheet_id == route_sheet_id)
        .limit(1)
    ):
        raise HTTPException(
            status_code=409,
            detail="A route sheet assigned to participants cannot be deleted",
        )

    session.execute(
        delete(RouteSheetStation).where(
            RouteSheetStation.route_sheet_id == sheet.id
        )
    )
    session.delete(sheet)
    session.commit()
    return {"ok": True}
