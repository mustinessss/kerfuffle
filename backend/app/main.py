from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1.access_codes import router as access_codes_router
from app.api.v1.auth import router as auth_router
from app.api.v1.account_recovery import public_router as account_recovery_router
from app.api.v1.events import router as events_router
from app.api.v1.health import router as health_router
from app.api.v1.leaderboard import router as leaderboard_router
from app.api.v1.participants import router as participants_router
from app.api.v1.route_sheets import router as route_sheets_router
from app.api.v1.scores import router as scores_router
from app.api.v1.stations import router as stations_router
from app.core.config import get_settings
from app.core.network_access import (
    effective_client_ip,
    is_public_api_request,
    request_peer_ip,
    resolve_network_zone,
)

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Backend сервиса мероприятий Kerfuffle.",
    docs_url=None if settings.environment.lower() == "production" else "/docs",
    redoc_url=None if settings.environment.lower() == "production" else "/redoc",
    openapi_url=None if settings.environment.lower() == "production" else "/openapi.json",
)

app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(access_codes_router, prefix=settings.api_v1_prefix)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(account_recovery_router, prefix=settings.api_v1_prefix)
app.include_router(events_router, prefix=settings.api_v1_prefix)
app.include_router(stations_router, prefix=settings.api_v1_prefix)
app.include_router(participants_router, prefix=settings.api_v1_prefix)
app.include_router(route_sheets_router, prefix=settings.api_v1_prefix)
app.include_router(scores_router, prefix=settings.api_v1_prefix)
app.include_router(leaderboard_router, prefix=settings.api_v1_prefix)


@app.middleware("http")
async def protect_network_zone_and_disable_api_caching(
    request: Request,
    call_next,
):
    if settings.environment.lower() == "production":
        peer_ip = request_peer_ip(request)
        health_check = (
            request.method == "GET"
            and request.url.path == f"{settings.api_v1_prefix}/health"
            and peer_ip in {"127.0.0.1", "::1"}
        )
        zone = resolve_network_zone(request, settings)
        if not health_check and zone is None:
            return JSONResponse(
                status_code=403,
                content={"detail": "Request is not allowed from this network zone."},
            )
        if zone == "public" and not is_public_api_request(
            request.method,
            request.url.path,
            settings.api_v1_prefix,
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": "This endpoint is available only in the private network."},
            )
        request.state.client_ip = effective_client_ip(request, settings)
    else:
        request.state.client_ip = request.client.host if request.client else "unknown"

    response = await call_next(request)
    if request.url.path.startswith(settings.api_v1_prefix):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/", tags=["Root"])
def root():
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "docs": None if settings.environment.lower() == "production" else "/docs",
    }
