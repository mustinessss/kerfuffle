from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


class Person(Base):
    __tablename__ = "people"
    __table_args__ = (
        CheckConstraint("btrim(first_name) <> ''", name="people_first_name_not_empty"),
        CheckConstraint("btrim(last_name) <> ''", name="people_last_name_not_empty"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, Identity(always=True), primary_key=True)
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    birth_date: Mapped[date | None] = mapped_column(Date)
    workplace_or_study: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="events_name_not_empty"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("btrim(display_name) <> ''", name="users_display_name_not_empty"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, Identity(always=True), primary_key=True)
    auth_subject: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    is_system_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_organizer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Station(Base):
    __tablename__ = "stations"
    __table_args__ = (
        UniqueConstraint("id", "event_id", name="stations_id_event_unique"),
        UniqueConstraint("event_id", "name", name="stations_name_per_event_unique"),
        CheckConstraint(
            "score_min >= 0 AND score_max >= score_min AND score_step > 0 "
            "AND (score_max - score_min) % score_step = 0",
            name="stations_valid_score_scale",
        ),
        CheckConstraint("btrim(name) <> ''", name="stations_name_not_empty"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, Identity(always=True), primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("events.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    score_min: Mapped[int] = mapped_column(Integer, nullable=False)
    score_max: Mapped[int] = mapped_column(Integer, nullable=False)
    score_step: Mapped[int] = mapped_column(Integer, nullable=False)


class EventParticipant(Base):
    __tablename__ = "event_participants"
    __table_args__ = (
        UniqueConstraint("person_id", "event_id", name="one_registration_per_person_event"),
        UniqueConstraint(
            "event_id", "registration_number", name="registration_number_per_event_unique"
        ),
        CheckConstraint(
            "btrim(registration_number) <> ''",
            name="event_participants_registration_number_not_empty",
        ),
        Index("event_participants_event_idx", "event_id", "registered_at"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, Identity(always=True), primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("events.id", ondelete="RESTRICT"), nullable=False
    )
    person_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("people.id", ondelete="RESTRICT"), nullable=False
    )
    registration_number: Mapped[str] = mapped_column(Text, nullable=False)
    qr_token: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, unique=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EventAccess(Base):
    __tablename__ = "event_access"
    __table_args__ = (
        CheckConstraint(
            "(role = 'station_operator' AND station_id IS NOT NULL) OR "
            "(role IN ('organizer', 'registrar') AND station_id IS NULL)",
            name="access_station_required_for_operator",
        ),
        CheckConstraint(
            "role IN ('organizer', 'registrar', 'station_operator')",
            name="event_access_valid_role",
        ),
        ForeignKeyConstraint(
            ["station_id", "event_id"],
            ["stations.id", "stations.event_id"],
            name="access_station_must_belong_to_event",
            ondelete="RESTRICT",
        ),
        Index("event_access_user_idx", "user_id", "event_id"),
        Index(
            "event_access_event_role_unique",
            "event_id",
            "user_id",
            "role",
            unique=True,
            postgresql_where=text("station_id IS NULL"),
            sqlite_where=text("station_id IS NULL"),
        ),
        Index(
            "event_access_operator_station_unique",
            "event_id",
            "user_id",
            "station_id",
            unique=True,
            postgresql_where=text("role = 'station_operator'"),
            sqlite_where=text("role = 'station_operator'"),
        ),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    event_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("events.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    station_id: Mapped[int | None] = mapped_column(ID_TYPE)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (
        CheckConstraint("points >= 0", name="scores_points_non_negative"),
        UniqueConstraint(
            "event_participant_id", "station_id", name="one_score_per_participant_station"
        ),
        Index("scores_station_idx", "station_id"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, Identity(always=True), primary_key=True)
    event_participant_id: Mapped[int] = mapped_column(
        ID_TYPE,
        ForeignKey("event_participants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    station_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False
    )
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    is_annulled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ScoreAudit(Base):
    __tablename__ = "score_audit"
    __table_args__ = (
        CheckConstraint(
            "action IN ('correction', 'annulment')",
            name="score_audit_valid_action",
        ),
        CheckConstraint(
            "btrim(reason) <> ''",
            name="score_audit_reason_not_empty",
        ),
        Index("score_audit_score_created_idx", "score_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, Identity(always=True), primary_key=True)
    score_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("scores.id", ondelete="RESTRICT"), nullable=False
    )
    changed_by_user_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    points_before: Mapped[int] = mapped_column(Integer, nullable=False)
    points_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AccessCode(Base):
    __tablename__ = "access_codes"
    __table_args__ = (
        CheckConstraint(
            "(role = 'registrar' AND station_id IS NULL) OR "
            "(role = 'station_operator' AND station_id IS NOT NULL)",
            name="access_codes_valid_scope",
        ),
        ForeignKeyConstraint(
            ["station_id", "event_id"],
            ["stations.id", "stations.event_id"],
            name="access_codes_station_must_belong_to_event",
            ondelete="RESTRICT",
        ),
        Index("access_codes_event_idx", "event_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, Identity(always=True), primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("events.id", ondelete="RESTRICT"), nullable=False
    )
    station_id: Mapped[int | None] = mapped_column(ID_TYPE)
    created_by_user_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    secret_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccessSession(Base):
    __tablename__ = "access_sessions"

    id: Mapped[int] = mapped_column(ID_TYPE, Identity(always=True), primary_key=True)
    access_code_id: Mapped[int] = mapped_column(
        ID_TYPE, ForeignKey("access_codes.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AccessCodeAttempt(Base):
    __tablename__ = "access_code_attempts"
    __table_args__ = (Index("access_code_attempts_ip_time_idx", "ip_hash", "created_at"),)

    id: Mapped[int] = mapped_column(ID_TYPE, Identity(always=True), primary_key=True)
    ip_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
