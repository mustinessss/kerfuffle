import argparse
from getpass import getpass

from sqlalchemy import text

from app.core.auth import create_initial_admin
from app.db.session import SessionLocal


def create_admin_interactively() -> None:
    email = input("Email администратора: ").strip()
    password = getpass("Пароль (не менее 12 символов, строчные/заглавные буквы и цифра): ")
    confirmation = getpass("Повторите пароль: ")
    if password != confirmation:
        raise SystemExit("Пароли не совпадают.")

    with SessionLocal() as session:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": 0x4B4552465546464C},
            )
        try:
            user = create_initial_admin(session, email, password)
        except (ValueError, RuntimeError) as exc:
            session.rollback()
            raise SystemExit(str(exc)) from exc

    print(f"Создан системный администратор {user.email}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Kerfuffle account administration.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create-admin", help="Create the first system administrator.")
    args = parser.parse_args()

    if args.command == "create-admin":
        create_admin_interactively()


if __name__ == "__main__":
    main()
