from fastapi import HTTPException, status
from app.db.models import User


def require_system_admin(user: User) -> None:
    if not user.is_system_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System administrator role required",
        )
