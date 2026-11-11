from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.models import EventAccess, User
from app.db.session import get_db


router = APIRouter(tags=["Account"])


@router.get("/me", summary="Текущий пользователь и его роли")
def read_current_user(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    accesses = session.scalars(
        select(EventAccess)
        .where(EventAccess.user_id == user.id)
        .order_by(EventAccess.event_id, EventAccess.role, EventAccess.station_id)
    )
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "is_system_admin": user.is_system_admin,
        "access": [
            {
                "event_id": access.event_id,
                "role": access.role,
                "station_id": access.station_id,
            }
            for access in accesses
        ],
    }
