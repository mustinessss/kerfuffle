from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase
from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)


def check_database_connection() -> None:
    with engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")
