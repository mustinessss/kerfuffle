from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.permissions import require_system_admin
from app.db.models import (
    Event,
    EventParticipant,
    RouteSheet,
    Score,
    Station,
    User,
)
from app.db.session import get_db


router = APIRouter(tags=["Leaderboard"])


@router.get(
    "/events/{event_id}/leaderboard",
    summary="Рейтинг мероприятия для системного администратора",
)
def read_event_leaderboard(
    event_id: int,
    route_sheet_id: int | None = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    require_system_admin(user)
    return build_event_leaderboard(event_id, route_sheet_id, session)


def build_event_leaderboard(
    event_id: int,
    route_sheet_id: int | None,
    session: Session,
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
            .where(Station.event_id == event_id, Station.rating_mode == "main")
            .order_by(Station.id)
        )
    )
    totals = (
        select(
            Score.event_participant_id.label("participant_id"),
            func.sum(Score.points).label("total_points"),
            func.count(Score.id).label("stations_completed"),
        )
        .join(Station, Station.id == Score.station_id)
        .where(Score.is_annulled.is_(False))
        .where(
            Station.event_id == event_id,
            Station.rating_mode == "main",
        )
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
        .where(
            Station.event_id == event_id,
            Station.rating_mode == "main",
            Score.is_annulled.is_(False),
        )
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


@router.get(
    "/events/{event_id}/stations/{station_id}/leaderboard",
    summary="Отдельный рейтинг площадки",
)
def read_station_leaderboard(
    event_id: int,
    station_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    require_system_admin(user)
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    station = session.scalar(
        select(Station).where(
            Station.id == station_id,
            Station.event_id == event_id,
        )
    )
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")
    if station.rating_mode != "separate":
        raise HTTPException(
            status_code=409,
            detail="Station does not have a separate rating",
        )

    scores = (
        select(
            Score.event_participant_id.label("participant_id"),
            Score.points.label("points"),
        )
        .where(
            Score.station_id == station_id,
            Score.is_annulled.is_(False),
        )
        .subquery()
    )
    ranked = (
        select(
            EventParticipant.id.label("participant_id"),
            func.rank()
            .over(order_by=func.coalesce(scores.c.points, 0).desc())
            .label("place"),
        )
        .outerjoin(scores, scores.c.participant_id == EventParticipant.id)
        .where(EventParticipant.event_id == event_id)
        .subquery()
    )
    rows = session.execute(
        select(
            EventParticipant.registration_number,
            func.coalesce(scores.c.points, 0).label("points"),
            scores.c.points.is_not(None).label("has_score"),
            ranked.c.place,
        )
        .outerjoin(scores, scores.c.participant_id == EventParticipant.id)
        .join(ranked, ranked.c.participant_id == EventParticipant.id)
        .where(EventParticipant.event_id == event_id)
        .order_by(
            func.coalesce(scores.c.points, 0).desc(),
            EventParticipant.registration_number,
        )
    )
    return {
        "event": {
            "id": event.id,
            "name": event.name,
            "event_date": event.event_date,
        },
        "station": {
            "id": station.id,
            "name": station.name,
            "score_max": station.score_max,
        },
        "participants": [
            {
                "registration_number": registration_number,
                "place": place,
                "points": points,
                "has_score": has_score,
            }
            for registration_number, points, has_score, place in rows
        ],
    }
