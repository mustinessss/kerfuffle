from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.permissions import require_event_access, require_system_admin
from app.db.models import Event, EventAccess, User
from app.db.session import get_db


router = APIRouter(prefix="/events", tags=["Events"])


class EventCreate(BaseModel):
    name: str = Field(max_length=200)
    event_date: date

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Event name must not be blank")
        return value


class EventUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    event_date: date | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Event name must not be blank")
        return value

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set:
            raise ValueError("At least one event field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Event fields cannot be null")
        return self


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
    statement = select(Event).order_by(Event.event_date, Event.id)
    if not user.is_system_admin:
        statement = (
            statement.join(EventAccess, EventAccess.event_id == Event.id)
            .where(EventAccess.user_id == user.id)
            .distinct()
        )
    events = session.scalars(statement)
    return [event_response(event) for event in events]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Создать мероприятие")
def create_event(
    payload: EventCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    require_system_admin(user)

    event = Event(name=payload.name, event_date=payload.event_date)
    session.add(event)
    session.commit()
    session.refresh(event)
    return event_response(event)


@router.patch("/{event_id}", summary="Изменить мероприятие")
def update_event(
    event_id: int,
    payload: EventUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    require_system_admin(user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
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
    if not user.is_system_admin:
        require_event_access(session, user, event_id)
    return event_response(event)
