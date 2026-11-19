from ipaddress import ip_address

from fastapi import Request

from app.core.config import Settings


PUBLIC_ACCESS_ROUTES = {
    ("POST", "/public/access/verify"),
    ("GET", "/public/access/route-sheets"),
    ("POST", "/public/access/participants"),
    ("POST", "/public/access/participant-lookup"),
    ("POST", "/public/access/scores"),
}


def _normalized_ip(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return str(ip_address(value))
    except ValueError:
        return None


def request_peer_ip(request: Request) -> str | None:
    return _normalized_ip(request.client.host if request.client else None)


def resolve_network_zone(request: Request, settings: Settings) -> str | None:
    peer_ip = request_peer_ip(request)
    if peer_ip == _normalized_ip(settings.public_proxy_ip):
        return "public"
    if peer_ip == _normalized_ip(settings.private_proxy_ip):
        return "private"
    return None


def is_public_api_request(method: str, path: str, api_prefix: str) -> bool:
    if not path.startswith(f"{api_prefix}/"):
        return False
    route = path[len(api_prefix):]
    return (method.upper(), route) in PUBLIC_ACCESS_ROUTES


def effective_client_ip(request: Request, settings: Settings) -> str:
    peer_ip = request_peer_ip(request) or "unknown"
    if peer_ip not in {
        _normalized_ip(settings.public_proxy_ip),
        _normalized_ip(settings.private_proxy_ip),
    }:
        return peer_ip

    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if not forwarded_for or "," in forwarded_for:
        return peer_ip
    return _normalized_ip(forwarded_for) or peer_ip
