from datetime import date, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.permissions import require_event_access
from app.db.models import Event, EventParticipant, Person, User
from app.db.session import get_db


router = APIRouter(tags=["Participants"])
REGISTRATION_NUMBER_WIDTH = 4


class PersonCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str
    last_name: str
    birth_date: date | None = None
    workplace_or_study: str | None = None
    phone: str | None = None

    @field_validator("first_name", "last_name")
    @classmethod
    def required_names_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("First and last name must not be blank")
        return value

    @field_validator("workplace_or_study", "phone")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ParticipantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    person_id: int | None = Field(default=None, gt=0)
    person: PersonCreate | None = None

    @model_validator(mode="after")
    def require_exactly_one_person_source(self):
        if (self.person_id is None) == (self.person is None):
            raise ValueError("Provide exactly one of person_id or person")
        return self


def person_response(person: Person) -> dict[str, int | str]:
    return {
        "id": person.id,
        "first_name": person.first_name,
        "last_name": person.last_name,
    }


def participant_response(
    registration: EventParticipant,
    person: Person,
) -> dict[str, int | str | datetime | None]:
    return {
        "id": registration.id,
        "event_id": registration.event_id,
        "person_id": person.id,
        "first_name": person.first_name,
        "last_name": person.last_name,
        "registration_number": registration.registration_number,
        "qr_token": str(registration.qr_token),
        "registered_at": registration.registered_at,
    }


def _postgres_error_code(error: IntegrityError) -> str | None:
    return getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)


@router.get("/people", summary="Найти карточки людей в мероприятии")
def search_people(
    event_id: int = Query(gt=0),
    query: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    require_event_access(session, user, event_id, {"organizer", "registrar"})

    terms = [term for term in query.strip().split() if term]
    if not terms:
        raise HTTPException(status_code=422, detail="Search query must not be blank")
    conditions = [
        or_(
            Person.first_name.ilike(f"%{term}%"),
            Person.last_name.ilike(f"%{term}%"),
        )
        for term in terms
    ]
    people = session.scalars(
        select(Person)
        .where(*conditions)
        .order_by(Person.last_name, Person.first_name, Person.id)
        .limit(limit)
    )
    return [person_response(person) for person in people]


@router.get(
    "/events/{event_id}/participants",
    summary="Список участников мероприятия",
)
def list_participants(
    event_id: int,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    require_event_access(session, user, event_id, {"organizer", "registrar"})
    rows = session.execute(
        select(EventParticipant, Person)
        .join(Person, Person.id == EventParticipant.person_id)
        .where(EventParticipant.event_id == event_id)
        .order_by(EventParticipant.registered_at, EventParticipant.id)
        .limit(limit)
        .offset(offset)
    )
    return [
        participant_response(registration, person)
        for registration, person in rows
    ]


@router.post(
    "/events/{event_id}/participants",
    status_code=status.HTTP_201_CREATED,
    summary="Зарегистрировать участника",
)
def register_participant(
    event_id: int,
    payload: ParticipantCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    event = session.scalar(select(Event).where(Event.id == event_id).with_for_update())
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    require_event_access(session, user, event_id, {"organizer", "registrar"})

    if payload.person_id is not None:
        person = session.get(Person, payload.person_id)
        if person is None:
            raise HTTPException(status_code=404, detail="Person not found")
    else:
        if payload.person is None:
            raise HTTPException(
                status_code=422,
                detail="Provide exactly one of person_id or person",
            )
        person = Person(**payload.person.model_dump())
        session.add(person)
        session.flush()

    existing = session.scalar(
        select(EventParticipant.id).where(
            EventParticipant.event_id == event_id,
            EventParticipant.person_id == person.id,
        )
    )
    if existing is not None:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Person is already registered for this event",
        )

    registration_count = session.scalar(
        select(func.count())
        .select_from(EventParticipant)
        .where(EventParticipant.event_id == event_id)
    )
    registration = EventParticipant(
        event_id=event_id,
        person_id=person.id,
        registration_number=f"{registration_count + 1:0{REGISTRATION_NUMBER_WIDTH}d}",
        qr_token=uuid4(),
    )
    session.add(registration)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        if _postgres_error_code(error) == "23505":
            raise HTTPException(
                status_code=409,
                detail="Registration conflicts with an existing participant",
            ) from error
        raise

    session.refresh(registration)
    return participant_response(registration, person)
