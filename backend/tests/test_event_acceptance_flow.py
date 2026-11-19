from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.auth import create_initial_admin
from app.core.config import Settings, get_settings
from app.db.session import Base, get_db
from app.main import app


PRIVATE_FIELDS = {"first_name", "last_name", "phone", "workplace_or_study"}


@pytest.fixture
def acceptance_client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.create_function(
            "btrim", 1, lambda value: None if value is None else value.strip()
        ),
    )
    Base.metadata.create_all(engine)

    def override_get_db():
        with Session(engine) as session:
            yield session

    settings = Settings(
        environment="development",
        access_code_hash_secret="a" * 48,
    )
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: settings
    with Session(engine) as session:
        create_initial_admin(session, "admin@example.test", "SecurePassword123")

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    engine.dispose()


def admin_headers(client: TestClient) -> dict[str, str]:
    csrf_token = client.cookies.get("kerfuffle_csrf")
    assert csrf_token
    return {
        "Origin": "http://testserver",
        "X-CSRF-Token": csrf_token,
    }


def assert_no_private_fields(value: object) -> None:
    if isinstance(value, dict):
        assert not PRIVATE_FIELDS.intersection(value)
        for nested in value.values():
            assert_no_private_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            assert_no_private_fields(nested)


def test_complete_event_flow_and_public_api_privacy(acceptance_client):
    client = acceptance_client
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "ADMIN@example.test", "password": "SecurePassword123"},
        headers={"Origin": "http://testserver"},
    )
    assert login.status_code == 200
    assert login.json()["is_system_admin"] is True
    headers = admin_headers(client)

    event_response = client.post(
        "/api/v1/events",
        json={"name": "Acceptance event", "event_date": date.today().isoformat()},
        headers=headers,
    )
    assert event_response.status_code == 201
    event_id = event_response.json()["id"]

    stations = {}
    for name, rating_mode, score_max, score_step in (
        ("North", "main", 10, 2),
        ("South", "main", 8, 2),
        ("Special", "separate", 10, 1),
    ):
        response = client.post(
            f"/api/v1/events/{event_id}/stations",
            json={
                "name": name,
                "score_min": 0,
                "score_max": score_max,
                "score_step": score_step,
                "rating_mode": rating_mode,
            },
            headers=headers,
        )
        assert response.status_code == 201
        stations[name] = response.json()

    route_sheets = {}
    for name, station_name in (("North route", "North"), ("South route", "South")):
        response = client.post(
            f"/api/v1/events/{event_id}/route-sheets",
            json={"name": name, "station_ids": [stations[station_name]["id"]]},
            headers=headers,
        )
        assert response.status_code == 201
        route_sheets[name] = response.json()

    for role, station_name, code in (
        ("registrar", None, "REGSTR8X"),
        ("station_operator", "North", "STAGE2X8"),
        ("station_operator", "South", "STAGE3X8"),
        ("station_operator", "Special", "STAGE4X8"),
    ):
        response = client.post(
            f"/api/v1/events/{event_id}/access-codes",
            json={
                "role": role,
                "station_id": stations[station_name]["id"] if station_name else None,
                "code": code,
            },
            headers=headers,
        )
        assert response.status_code == 201
        assert response.json()["code"] == code

    def verify_code(code: str) -> str:
        response = client.post("/api/v1/public/access/verify", json={"code": code})
        assert response.status_code == 200
        return response.json()["access_token"]

    registrar_headers = {"Authorization": f"Bearer {verify_code('REGSTR8X')}"}
    route_list = client.get(
        "/api/v1/public/access/route-sheets",
        headers=registrar_headers,
    )
    assert route_list.status_code == 200
    assert {item["name"] for item in route_list.json()} == {
        "North route",
        "South route",
    }

    for number, sheet_name, first_name in (
        ("000117", "North route", "Private"),
        ("000118", "South route", "Zero"),
    ):
        response = client.post(
            "/api/v1/public/access/participants",
            headers=registrar_headers,
            json={
                "registration_number": number,
                "route_sheet_id": route_sheets[sheet_name]["id"],
                "person": {
                    "first_name": first_name,
                    "last_name": "Participant",
                    "phone": "+70000000000",
                    "workplace_or_study": "Example school",
                },
            },
        )
        assert response.status_code == 201
        assert response.json() == {"registration_number": number}
        assert_no_private_fields(response.json())

    invalid_number = client.post(
        "/api/v1/public/access/participants",
        headers=registrar_headers,
        json={
            "registration_number": "00A117",
            "route_sheet_id": route_sheets["North route"]["id"],
            "person": {"first_name": "Invalid", "last_name": "Number"},
        },
    )
    assert invalid_number.status_code == 422

    duplicate_number = client.post(
        "/api/v1/public/access/participants",
        headers=registrar_headers,
        json={
            "registration_number": "000117",
            "route_sheet_id": route_sheets["North route"]["id"],
            "person": {"first_name": "Duplicate", "last_name": "Number"},
        },
    )
    assert duplicate_number.status_code == 409

    score_ids = {}
    for station_name, code in (
        ("North", "STAGE2X8"),
        ("South", "STAGE3X8"),
        ("Special", "STAGE4X8"),
    ):
        holder_headers = {"Authorization": f"Bearer {verify_code(code)}"}
        lookup = client.post(
            "/api/v1/public/access/participant-lookup",
            headers=holder_headers,
            json={"registration_number": "000117"},
        )
        assert lookup.status_code == 200
        assert lookup.json()["registration_number"] == "000117"
        assert_no_private_fields(lookup.json())
        assert "Private" not in lookup.text

        points = {"North": 6, "South": 8, "Special": 5}[station_name]
        score = client.post(
            "/api/v1/public/access/scores",
            headers=holder_headers,
            json={
                "event_participant_id": lookup.json()["event_participant_id"],
                "points": points,
            },
        )
        assert score.status_code == 201
        score_ids[station_name] = score.json()["id"]

        if station_name == "North":
            duplicate_score = client.post(
                "/api/v1/public/access/scores",
                headers=holder_headers,
                json={
                    "event_participant_id": lookup.json()["event_participant_id"],
                    "points": points,
                },
            )
            assert duplicate_score.status_code == 409

            invalid_step = client.post(
                "/api/v1/public/access/scores",
                headers=holder_headers,
                json={
                    "event_participant_id": lookup.json()["event_participant_id"],
                    "points": 7,
                },
            )
            assert invalid_step.status_code == 422

    corrected = client.patch(
        f"/api/v1/scores/{score_ids['North']}",
        json={"points": 4, "reason": "Corrected transcription"},
        headers=headers,
    )
    assert corrected.status_code == 200
    assert corrected.json()["points"] == 4
    history = client.get(f"/api/v1/events/{event_id}/scores", headers=headers)
    assert history.status_code == 200
    corrected_history = next(
        item for item in history.json() if item["id"] == score_ids["North"]
    )
    assert any(
        item["reason"] == "Corrected transcription"
        for item in corrected_history["history"]
    )

    registrations = client.get(
        f"/api/v1/events/{event_id}/participants",
        headers=headers,
    )
    assert registrations.status_code == 200
    registrations_by_number = {
        item["registration_number"]: item for item in registrations.json()
    }
    assert (
        registrations_by_number["000117"]["route_sheet_id"]
        == route_sheets["North route"]["id"]
    )

    overall = client.get(f"/api/v1/events/{event_id}/leaderboard", headers=headers)
    assert overall.status_code == 200
    assert [
        (item["registration_number"], item["total_points"], item["place"])
        for item in overall.json()["participants"]
    ] == [("000117", 12, 1), ("000118", 0, 2)]
    assert_no_private_fields(overall.json())

    route_rating = client.get(
        f"/api/v1/events/{event_id}/leaderboard",
        params={"route_sheet_id": route_sheets["North route"]["id"]},
        headers=headers,
    )
    assert route_rating.status_code == 200
    assert [
        item["registration_number"] for item in route_rating.json()["participants"]
    ] == ["000117"]

    separate_rating = client.get(
        f"/api/v1/events/{event_id}/stations/{stations['Special']['id']}/leaderboard",
        headers=headers,
    )
    assert separate_rating.status_code == 200
    assert [
        (item["registration_number"], item["points"], item["place"])
        for item in separate_rating.json()["participants"]
    ] == [("000117", 5, 1), ("000118", 0, 2)]
    assert_no_private_fields(separate_rating.json())

    with TestClient(app) as anonymous_client:
        private_rating = anonymous_client.get(
            f"/api/v1/events/{event_id}/leaderboard"
        )
    assert private_rating.status_code == 401
