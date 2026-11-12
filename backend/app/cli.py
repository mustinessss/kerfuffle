import argparse

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import SessionLocal


def bootstrap_system_admin(
    session: Session,
    auth_subject: str,
    display_name: str,
    email: str | None = None,
) -> User:
    auth_subject = auth_subject.strip()
    display_name = display_name.strip()
    email = email.strip() if email else None
    if not auth_subject or not display_name:
        raise ValueError("OIDC subject and display name are required")

    if session.get_bind().dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": 0x4B4552465546464C},
        )

    existing_admin = session.scalar(
        select(User.id).where(User.is_system_admin.is_(True)).limit(1)
    )
    if existing_admin is not None:
        raise RuntimeError("A system administrator already exists; bootstrap is one-time")

    user = session.scalar(select(User).where(User.auth_subject == auth_subject))
    if user is not None and not user.is_active:
        raise RuntimeError("The selected OIDC account is inactive")
    if user is None:
        user = User(
            auth_subject=auth_subject,
            display_name=display_name,
            email=email,
            is_system_admin=True,
        )
        session.add(user)
    else:
        user.display_name = display_name
        user.email = email or user.email
        user.is_system_admin = True

    session.commit()
    session.refresh(user)
    return user


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Grant the first Kerfuffle system-admin role to an existing Keycloak "
            "identity. This command never handles passwords."
        )
    )
    parser.add_argument("--subject", required=True, help="Keycloak OIDC subject (user ID)")
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--email")
    args = parser.parse_args()

    confirmation = input(
        f"Grant the first system-admin role to OIDC subject {args.subject!r}? [y/N] "
    )
    if confirmation.strip().lower() not in {"y", "yes"}:
        raise SystemExit("Bootstrap cancelled.")

    with SessionLocal() as session:
        user = bootstrap_system_admin(
            session,
            auth_subject=args.subject,
            display_name=args.display_name,
            email=args.email,
        )
    print(f"System administrator configured for OIDC subject {user.auth_subject}.")


if __name__ == "__main__":
    main()
