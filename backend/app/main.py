from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Backend сервиса мероприятий Kerfuffle.",
)

app.include_router(health_router, prefix=settings.api_v1_prefix)


@app.get("/", tags=["Root"])
def root():
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "docs": "/docs",
    }
