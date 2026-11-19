from types import SimpleNamespace

from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core.network_access import (
    effective_client_ip,
    is_public_api_request,
    resolve_network_zone,
)
from app.main import app


PRODUCTION_NETWORK_SETTINGS = SimpleNamespace(
    environment="production",
    api_v1_prefix="/api/v1",
    public_proxy_ip="172.29.0.2",
    private_proxy_ip="172.30.0.2",
)


def request_with_peer(peer_ip: str, headers: list[tuple[bytes, bytes]] | None = None):
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "https",
            "path": "/api/v1/public/access/verify",
            "headers": headers or [],
            "query_string": b"",
            "server": ("kerfuffle.test", 443),
            "client": (peer_ip, 12345),
        }
    )


def test_public_api_allowlist_contains_only_staff_code_endpoints():
    assert is_public_api_request(
        "POST",
        "/api/v1/public/access/verify",
        "/api/v1",
    )
    assert is_public_api_request(
        "GET",
        "/api/v1/public/access/route-sheets",
        "/api/v1",
    )
    assert not is_public_api_request(
        "POST",
        "/api/v1/auth/login",
        "/api/v1",
    )
    assert not is_public_api_request(
        "GET",
        "/api/v1/events/1/leaderboard",
        "/api/v1",
    )
    assert not is_public_api_request(
        "POST",
        "/api/v1/public/access/route-sheets",
        "/api/v1",
    )


def test_proxy_zone_uses_peer_ip_and_trusts_forwarded_ip_only_from_proxy():
    public_request = request_with_peer(
        "172.29.0.2",
        [(b"x-forwarded-for", b"203.0.113.8")],
    )
    spoofed_request = request_with_peer(
        "203.0.113.20",
        [
            (b"x-forwarded-for", b"172.30.0.2"),
            (b"x-kerfuffle-access-zone", b"private"),
        ],
    )

    assert resolve_network_zone(public_request, PRODUCTION_NETWORK_SETTINGS) == "public"
    assert effective_client_ip(public_request, PRODUCTION_NETWORK_SETTINGS) == "203.0.113.8"
    assert resolve_network_zone(spoofed_request, PRODUCTION_NETWORK_SETTINGS) is None
    assert effective_client_ip(spoofed_request, PRODUCTION_NETWORK_SETTINGS) == "203.0.113.20"


def test_production_api_middleware_blocks_public_admin_and_direct_requests(monkeypatch):
    monkeypatch.setattr("app.main.settings", PRODUCTION_NETWORK_SETTINGS)

    public_client = TestClient(app, client=("172.29.0.2", 12345))
    direct_client = TestClient(app, client=("203.0.113.20", 12345))
    private_client = TestClient(app, client=("172.30.0.2", 12345))

    public_admin = public_client.get("/api/v1/auth/me")
    public_leaderboard = public_client.get("/api/v1/events/1/leaderboard")
    direct_request = direct_client.get("/api/v1/health")
    private_request = private_client.get("/not-a-route")

    assert public_admin.status_code == 403
    assert public_leaderboard.status_code == 403
    assert direct_request.status_code == 403
    assert private_request.status_code == 404


def test_production_health_check_is_limited_to_backend_loopback(monkeypatch):
    monkeypatch.setattr("app.main.settings", PRODUCTION_NETWORK_SETTINGS)

    loopback = TestClient(app, client=("127.0.0.1", 12345))
    public = TestClient(app, client=("172.29.0.2", 12345))

    assert loopback.get("/api/v1/health").status_code == 200
    assert public.get("/api/v1/health").status_code == 403
