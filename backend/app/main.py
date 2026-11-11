from fastapi import FastAPI

from app.api.v1.access_codes import router as access_codes_router
from app.api.v1.events import router as events_router
from app.api.v1.health import router as health_router
from app.api.v1.leaderboard import router as leaderboard_router
from app.api.v1.me import router as me_router
from app.api.v1.organizer_admin import router as organizer_admin_router
from app.api.v1.participants import router as participants_router
from app.api.v1.scores import router as scores_router
from app.api.v1.stations import router as stations_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Backend сервиса мероприятий Kerfuffle.",
)

app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(access_codes_router, prefix=settings.api_v1_prefix)
app.include_router(me_router, prefix=settings.api_v1_prefix)
app.include_router(organizer_admin_router, prefix=settings.api_v1_prefix)
app.include_router(events_router, prefix=settings.api_v1_prefix)
app.include_router(stations_router, prefix=settings.api_v1_prefix)
app.include_router(participants_router, prefix=settings.api_v1_prefix)
app.include_router(scores_router, prefix=settings.api_v1_prefix)
app.include_router(leaderboard_router, prefix=settings.api_v1_prefix)


@app.get("/", tags=["Root"])
def root():
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "docs": "/docs",
    }
