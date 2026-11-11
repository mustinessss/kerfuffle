from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Event, EventParticipant, Score, Station
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

    totals = (
        select(
            Score.event_participant_id.label("participant_id"),
            func.sum(Score.points).label("total_points"),
            func.count(Score.id).label("stations_completed"),
        )
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
    stations_total = session.scalar(
        select(func.count()).select_from(Station).where(Station.event_id == event_id)
    )
    rows = session.execute(
        select(
            EventParticipant.registration_number,
            func.coalesce(totals.c.total_points, 0).label("total_points"),
            totals.c.stations_completed,
            rankings.c.place,
        )
        .outerjoin(totals, totals.c.participant_id == EventParticipant.id)
        .join(rankings, rankings.c.participant_id == EventParticipant.id)
        .where(EventParticipant.event_id == event_id)
        .order_by(
            func.coalesce(totals.c.total_points, 0).desc(),
            EventParticipant.registration_number,
        )
    )

    participants = [
        {
            "registration_number": registration_number,
            "place": place,
            "total_points": total_points,
            "stations_completed": stations_completed or 0,
            "stations_total": stations_total or 0,
        }
        for registration_number, total_points, stations_completed, place in rows
    ]
    return {
        "event": {
            "id": event.id,
            "name": event.name,
            "event_date": event.event_date,
        },
        "stations_total": stations_total or 0,
        "participants": participants,
    }
