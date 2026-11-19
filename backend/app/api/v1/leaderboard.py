from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Event, EventParticipant, RouteSheet, Score, Station
from app.db.session import get_db


router = APIRouter(tags=["Leaderboard"])


@router.get("/public/events", summary="Список мероприятий для публичного рейтинга")
def list_public_events(session: Session = Depends(get_db)):
    events = list(
        session.scalars(select(Event).order_by(Event.event_date.desc(), Event.name))
    )
    if not events:
        return []

    route_sheets = session.execute(
        select(RouteSheet.event_id, RouteSheet.id, RouteSheet.name)
        .where(RouteSheet.event_id.in_([event.id for event in events]))
        .order_by(RouteSheet.name, RouteSheet.id)
    )
    sheets_by_event: dict[int, list[dict[str, int | str]]] = {
        event.id: [] for event in events
    }
    for event_id, route_sheet_id, name in route_sheets:
        sheets_by_event[event_id].append({"id": route_sheet_id, "name": name})

    return [
        {
            "id": event.id,
            "name": event.name,
            "event_date": event.event_date,
            "route_sheets": sheets_by_event[event.id],
        }
        for event in events
    ]


@router.get(
    "/public/events/{event_id}/leaderboard",
    summary="Публичный рейтинг мероприятия",
)
def read_public_leaderboard(
    event_id: int,
    route_sheet_id: int | None = None,
    session: Session = Depends(get_db),
):
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if route_sheet_id is not None and session.scalar(
        select(RouteSheet.id).where(
            RouteSheet.id == route_sheet_id,
            RouteSheet.event_id == event_id,
        )
    ) is None:
        raise HTTPException(status_code=404, detail="Route sheet not found")

    stations = list(
        session.scalars(
            select(Station)
            .where(Station.event_id == event_id)
            .order_by(Station.id)
        )
    )
    totals = (
        select(
            Score.event_participant_id.label("participant_id"),
            func.sum(Score.points).label("total_points"),
            func.count(Score.id).label("stations_completed"),
        )
        .where(Score.is_annulled.is_(False))
        .group_by(Score.event_participant_id)
        .subquery()
    )
    participant_filter = [EventParticipant.event_id == event_id]
    if route_sheet_id is not None:
        participant_filter.append(EventParticipant.route_sheet_id == route_sheet_id)
    rankings = (
        select(
            EventParticipant.id.label("participant_id"),
            func.rank()
            .over(order_by=func.coalesce(totals.c.total_points, 0).desc())
            .label("place"),
        )
        .outerjoin(totals, totals.c.participant_id == EventParticipant.id)
        .where(*participant_filter)
        .subquery()
    )
    rows = list(
        session.execute(
            select(
                EventParticipant.id,
                EventParticipant.registration_number,
                func.coalesce(totals.c.total_points, 0).label("total_points"),
                totals.c.stations_completed,
                rankings.c.place,
            )
            .outerjoin(totals, totals.c.participant_id == EventParticipant.id)
            .join(rankings, rankings.c.participant_id == EventParticipant.id)
            .where(*participant_filter)
            .order_by(
                func.coalesce(totals.c.total_points, 0).desc(),
                EventParticipant.registration_number,
            )
        )
    )
    score_rows = session.execute(
        select(
            Score.event_participant_id,
            Score.station_id,
            Score.points,
        )
        .join(Station, Station.id == Score.station_id)
        .where(Station.event_id == event_id, Score.is_annulled.is_(False))
    )
    points_by_participant = {
        (participant_id, station_id): points
        for participant_id, station_id, points in score_rows
    }

    participants = [
        {
            "registration_number": registration_number,
            "place": place,
            "total_points": total_points,
            "stations_completed": stations_completed or 0,
            "stations_total": len(stations),
            "stations": [
                {
                    "station_id": station.id,
                    "name": station.name,
                    "points": points_by_participant.get((participant_id, station.id)),
                    "score_max": station.score_max,
                }
                for station in stations
            ],
        }
        for (
            participant_id,
            registration_number,
            total_points,
            stations_completed,
            place,
        ) in rows
    ]
    return {
        "event": {
            "id": event.id,
            "name": event.name,
            "event_date": event.event_date,
        },
        "route_sheet_id": route_sheet_id,
        "stations_total": len(stations),
        "stations": [
            {
                "id": station.id,
                "name": station.name,
                "score_max": station.score_max,
            }
            for station in stations
        ],
        "participants": participants,
    }
