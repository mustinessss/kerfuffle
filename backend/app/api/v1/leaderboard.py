from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Event, EventParticipant, Person, Score, Station
from app.db.session import get_db


router = APIRouter(tags=["Leaderboard"])


@router.get(
    "/public/events/{event_id}/leaderboard",
    summary="Публичный рейтинг мероприятия",
)
def read_public_leaderboard(
    event_id: int,
    session: Session = Depends(get_db),
):
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

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
    rankings = (
        select(
            EventParticipant.id.label("participant_id"),
            func.rank()
            .over(order_by=func.coalesce(totals.c.total_points, 0).desc())
            .label("place"),
        )
        .outerjoin(totals, totals.c.participant_id == EventParticipant.id)
        .where(EventParticipant.event_id == event_id)
        .subquery()
    )
    rows = list(session.execute(
        select(
            EventParticipant.id,
            EventParticipant.registration_number,
            Person.first_name,
            Person.last_name,
            func.coalesce(totals.c.total_points, 0).label("total_points"),
            totals.c.stations_completed,
            rankings.c.place,
        )
        .join(Person, Person.id == EventParticipant.person_id)
        .outerjoin(totals, totals.c.participant_id == EventParticipant.id)
        .join(rankings, rankings.c.participant_id == EventParticipant.id)
        .where(EventParticipant.event_id == event_id)
        .order_by(
            func.coalesce(totals.c.total_points, 0).desc(),
            EventParticipant.registration_number,
        )
    ))
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
            "first_name": first_name,
            "last_name": last_name,
            "registration_number": registration_number,
            "place": place,
            "total_points": total_points,
            "stations_completed": stations_completed or 0,
            "stations_total": len(stations),
            "stations": [
                {
                    "station_id": station.id,
                    "name": station.name,
                    "points": points_by_participant.get(
                        (participant_id, station.id)
                    ),
                    "score_max": station.score_max,
                }
                for station in stations
            ],
        }
        for (
            participant_id,
            registration_number,
            first_name,
            last_name,
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
