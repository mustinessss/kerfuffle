import logging
import secrets
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import Settings, get_settings
from app.db.models import User
from app.db.session import get_db


router = APIRouter(prefix="/system-admin", tags=["System administration"])
logger = logging.getLogger(__name__)


class OrganizerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=254)

    @field_validator("display_name")
    @classmethod
    def display_name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Display name must not be blank")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if "@" not in value:
            raise ValueError("Enter a valid email address")
        return value


def _keycloak_configuration(settings: Settings) -> tuple[str, str, str, str]:
    values = (
        settings.keycloak_admin_base_url,
        settings.keycloak_admin_realm,
        settings.keycloak_admin_client_id,
        settings.keycloak_admin_client_secret,
    )
    if not all(values):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Organizer provisioning is not configured",
        )
    base_url, realm, client_id, client_secret = values
    return (
        base_url.rstrip("/"),
        quote(realm, safe=""),
        client_id,
        client_secret,
    )


def _service_token(client: httpx.Client, base_url: str, realm: str, client_id: str, client_secret: str) -> str:
    try:
        response = client.post(
            f"{base_url}/realms/{realm}/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        response.raise_for_status()
        token = response.json().get("access_token")
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity provider is unavailable for organizer provisioning",
        ) from exc
    if not isinstance(token, str) or not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity provider returned an invalid service session",
        )
    return token


def _remove_keycloak_user(user_url: str, token: str) -> None:
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.delete(user_url, headers={"Authorization": f"Bearer {token}"})
            if response.status_code not in (status.HTTP_204_NO_CONTENT, status.HTTP_404_NOT_FOUND):
                logger.error("Could not remove provisioned Keycloak user; status=%s", response.status_code)
    except httpx.HTTPError:
        logger.exception("Could not contact Keycloak to remove a provisioned user")


@router.post(
    "/organizers",
    status_code=status.HTTP_201_CREATED,
    summary="Создать учётную запись организатора",
)
def create_organizer(
    payload: OrganizerCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not user.is_system_admin:
        raise HTTPException(status_code=403, detail="System administrator role required")
    base_url, realm, client_id, client_secret = _keycloak_configuration(settings)
    temporary_password = secrets.token_urlsafe(18)
    display_name = payload.display_name.strip()
    name_parts = display_name.split(maxsplit=1)
    token = ""
    keycloak_user_url = ""
    created_subject = ""
    try:
        with httpx.Client(timeout=10.0) as client:
            token = _service_token(client, base_url, realm, client_id, client_secret)
            headers = {"Authorization": f"Bearer {token}"}
            users_url = f"{base_url}/admin/realms/{realm}/users"
            response = client.post(
                users_url,
                headers=headers,
                json={
                    "username": payload.username,
                    "enabled": True,
                    "email": payload.email,
                    "firstName": name_parts[0],
                    "lastName": name_parts[1] if len(name_parts) > 1 else "",
                    "emailVerified": False,
                    "credentials": [
                        {
                            "type": "password",
                            "value": temporary_password,
                            "temporary": True,
                        }
                    ],
                },
            )
            if response.status_code == status.HTTP_409_CONFLICT:
                raise HTTPException(status_code=409, detail="This username or email is already in use")
            if response.status_code != status.HTTP_201_CREATED:
                response.raise_for_status()
                raise HTTPException(status_code=502, detail="Identity provider did not create the account")
            location = response.headers.get("Location", "").rstrip("/")
            created_subject = location.rsplit("/", 1)[-1]
            if not created_subject or not location.startswith(users_url):
                raise HTTPException(status_code=502, detail="Identity provider returned an invalid account identifier")
            keycloak_user_url = location

        organizer = User(
            auth_subject=created_subject,
            email=payload.email,
            display_name=display_name,
            is_organizer=True,
        )
        session.add(organizer)
        session.commit()
        session.refresh(organizer)
    except HTTPException:
        if keycloak_user_url and token:
            _remove_keycloak_user(keycloak_user_url, token)
        raise
    except (httpx.HTTPError, SQLAlchemyError) as exc:
        session.rollback()
        if keycloak_user_url and token:
            _remove_keycloak_user(keycloak_user_url, token)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not complete organizer provisioning",
        ) from exc

    return {
        "id": organizer.id,
        "username": payload.username,
        "display_name": organizer.display_name,
        "email": organizer.email,
        "temporary_password": temporary_password,
        "must_change_password": True,
    }
