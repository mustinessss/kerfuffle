import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.api.v1.organizer_admin import OrganizerCreate, create_organizer
from app.core.config import Settings
from app.db.models import User
from app.db.session import Base


@pytest.fixture
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.create_function(
            "btrim", 1, lambda value: None if value is None else value.strip()
        ),
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_non_system_admin_cannot_provision_organizer(db_session):
    regular_user = User(auth_subject="regular-sub", display_name="Regular")
    db_session.add(regular_user)
    db_session.commit()

    with pytest.raises(HTTPException) as error:
        create_organizer(
            OrganizerCreate(username="new.organizer", display_name="New Organizer"),
            regular_user,
            db_session,
            Settings(),
        )

    assert error.value.status_code == 403


def test_provisioned_organizer_receives_one_time_temporary_password(
    db_session, monkeypatch
):
    admin = User(
        auth_subject="admin-sub",
        display_name="Admin",
        is_system_admin=True,
    )
    db_session.add(admin)
    db_session.commit()

    class FakeClient:
        def __init__(self, **_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def post(self, url, **kwargs):
            request = httpx.Request("POST", url)
            if url.endswith("/protocol/openid-connect/token"):
                return httpx.Response(
                    200,
                    json={"access_token": "service-token"},
                    request=request,
                )
            return httpx.Response(
                201,
                headers={"Location": f"{url}/organizer-subject"},
                request=request,
            )

    monkeypatch.setattr("app.api.v1.organizer_admin.httpx.Client", FakeClient)
    result = create_organizer(
        OrganizerCreate(
            username="new.organizer",
            display_name="New Organizer",
            email="new@example.test",
        ),
        admin,
        db_session,
        Settings(
            keycloak_admin_base_url="http://keycloak",
            keycloak_admin_realm="kerfuffle",
            keycloak_admin_client_id="provisioner",
            keycloak_admin_client_secret="service-secret",
        ),
    )

    assert result["username"] == "new.organizer"
    assert result["temporary_password"]
    assert result["must_change_password"] is True
    stored = db_session.query(User).filter_by(auth_subject="organizer-subject").one()
    assert stored.is_organizer is True
    assert stored.is_system_admin is False
