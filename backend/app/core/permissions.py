from collections.abc import Collection

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.models import EventAccess, Station, User


EVENT_ROLES = frozenset({"organizer", "registrar", "station_operator"})


def require_event_access(
    session: Session,
    user: User,
    event_id: int,
    allowed_roles: Collection[str] = EVENT_ROLES,
) -> list[EventAccess]:
    roles = set(allowed_roles)
    if not roles or not roles <= EVENT_ROLES:
        raise ValueError("allowed_roles must contain valid event roles")

    accesses = list(
        session.scalars(
            select(EventAccess).where(
                EventAccess.user_id == user.id,
                EventAccess.event_id == event_id,
                EventAccess.role.in_(roles),
            )
        )
    )
    if not accesses:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this event",
        )
    return accesses


def require_station_access(
    session: Session,
    user: User,
    station_id: int,
    allowed_roles: Collection[str],
) -> EventAccess:
    roles = set(allowed_roles)
    if not roles or not roles <= EVENT_ROLES:
        raise ValueError("allowed_roles must contain valid event roles")

    station = session.get(Station, station_id)
    if station is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Station not found",
        )

    access_conditions = []
    if "station_operator" in roles:
        access_conditions.append(
            and_(
                EventAccess.role == "station_operator",
                EventAccess.station_id == station.id,
            )
        )
    event_wide_roles = roles - {"station_operator"}
    if event_wide_roles:
        access_conditions.append(
            and_(
                EventAccess.role.in_(event_wide_roles),
                EventAccess.station_id.is_(None),
            )
        )

    access = session.scalar(
        select(EventAccess).where(
            EventAccess.user_id == user.id,
            EventAccess.event_id == station.event_id,
            or_(*access_conditions),
        )
    )
    if access is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this station",
        )
    return access
