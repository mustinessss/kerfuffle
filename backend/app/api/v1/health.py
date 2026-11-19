from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import check_database_connection

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Проверка состояния API и PostgreSQL")
def health_check():
    try:
        check_database_connection()
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "api": "ok",
                "database": "unavailable",
            },
        )

    return {
        "status": "ok",
        "api": "ok",
        "database": "connected",
    }
