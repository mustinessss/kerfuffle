from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.permissions import require_event_access
from app.db.models import Event, EventAccess, User
from app.db.session import get_db


router = APIRouter(prefix="/events", tags=["Events"])


class EventCreate(BaseModel):
    name: str
    event_date: date

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Event name must not be blank")
        return value


def event_response(event: Event) -> dict[str, int | str | date]:
    return {
        "id": event.id,
        "name": event.name,
        "event_date": event.event_date,
    }


@router.get("", summary="Мероприятия, доступные текущему пользователю")
def list_events(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    events = session.scalars(
        select(Event)
        .join(EventAccess, EventAccess.event_id == Event.id)
        .where(EventAccess.user_id == user.id)
        .distinct()
        .order_by(Event.event_date, Event.id)
    )
    return [event_response(event) for event in events]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Создать мероприятие")
def create_event(
    payload: EventCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    if not user.is_system_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System administrator role required",
        )

    event = Event(name=payload.name, event_date=payload.event_date)
    session.add(event)
    session.flush()
    session.add(
        EventAccess(
            user_id=user.id,
            event_id=event.id,
            role="organizer",
        )
    )
    session.commit()
    session.refresh(event)
    return event_response(event)


@router.get("/{event_id}", summary="Получить мероприятие")
def read_event(
    event_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    require_event_access(session, user, event_id)
    return event_response(event)
