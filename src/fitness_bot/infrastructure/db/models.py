from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    telegram_username: Mapped[str | None] = mapped_column(Text)
    is_moderator: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    sex: Mapped[str | None] = mapped_column(Text)
    birth_year: Mapped[int | None] = mapped_column(Integer)
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    experience: Mapped[str | None] = mapped_column(Text)
    experience_details: Mapped[str | None] = mapped_column(Text)
    days_per_week: Mapped[int | None] = mapped_column(SmallInteger)
    equipment: Mapped[str | None] = mapped_column(Text)
    training_place: Mapped[str | None] = mapped_column(Text)
    limitations: Mapped[str | None] = mapped_column(Text)
    activity_level: Mapped[str | None] = mapped_column(Text)
    session_minutes: Mapped[int | None] = mapped_column(SmallInteger)
    body_fat_pct: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    body_fat_set: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    supplements: Mapped[str | None] = mapped_column(Text)
    supplements_other: Mapped[str | None] = mapped_column(Text)
    diet_prefs: Mapped[str | None] = mapped_column(Text)
    nutrition_constraints: Mapped[str | None] = mapped_column(Text)
    pharma: Mapped[str | None] = mapped_column(Text)
    timezone_offset: Mapped[str | None] = mapped_column(Text)
    goal: Mapped[str | None] = mapped_column(Text)
    nutrition_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    expected_input: Mapped[str] = mapped_column(Text, nullable=False, server_default="none")
    expected_field: Mapped[str | None] = mapped_column(Text)
    focus_slot: Mapped[int | None] = mapped_column(SmallInteger)
    active_program_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    active_session_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    pending_proposal_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    training_weekdays: Mapped[list[UserTrainingWeekdayRow]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class UserTrainingWeekdayRow(Base):
    __tablename__ = "user_training_weekdays"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    weekday: Mapped[int] = mapped_column(SmallInteger, primary_key=True)

    user: Mapped[UserRow] = relationship(back_populates="training_weekdays")


class WeightEntryRow(Base):
    __tablename__ = "weight_entries"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    kilograms: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)


class WeightReminderRow(Base):
    __tablename__ = "weight_reminders"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    local_time: Mapped[time] = mapped_column(Time, nullable=False)
    last_sent_on: Mapped[date | None] = mapped_column(Date)

    weekdays: Mapped[list[WeightReminderWeekdayRow]] = relationship(
        back_populates="reminder",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class TrainingReminderRow(Base):
    """Evening (20:00) and morning (09:00) training nudges. Times are fixed in code."""

    __tablename__ = "training_reminders"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    evening_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    morning_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_evening_sent_on: Mapped[date | None] = mapped_column(Date)
    last_morning_sent_on: Mapped[date | None] = mapped_column(Date)


class WeightReminderWeekdayRow(Base):
    __tablename__ = "weight_reminder_weekdays"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("weight_reminders.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    weekday: Mapped[int] = mapped_column(SmallInteger, primary_key=True)

    reminder: Mapped[WeightReminderRow] = relationship(back_populates="weekdays")


class MeasurementSiteRow(Base):
    __tablename__ = "measurement_sites"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))

    guide: Mapped[MeasurementGuideRow | None] = relationship(back_populates="site", uselist=False, lazy="selectin")


class MeasurementGuideRow(Base):
    __tablename__ = "measurement_guides"

    site_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("measurement_sites.id", ondelete="CASCADE"),
        primary_key=True,
    )
    instruction: Mapped[str] = mapped_column(Text, nullable=False)

    site: Mapped[MeasurementSiteRow] = relationship(back_populates="guide")


class MeasurementEntryRow(Base):
    __tablename__ = "measurement_entries"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    site_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("measurement_sites.id"), nullable=False)
    centimeters: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExerciseRow(Base):
    __tablename__ = "exercises"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_normalized: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    technique: Mapped[str] = mapped_column(Text, nullable=False)
    places: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{gym}")

    muscles: Mapped[list[ExerciseMuscleRow]] = relationship(
        back_populates="exercise",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    videos: Mapped[list[ExerciseVideoRow]] = relationship(
        back_populates="exercise",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ExerciseVideoRow.position",
    )


class ExerciseMuscleRow(Base):
    __tablename__ = "exercise_muscles"

    exercise_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("exercises.id", ondelete="CASCADE"),
        primary_key=True,
    )
    muscle: Mapped[str] = mapped_column(Text, primary_key=True)
    role: Mapped[str] = mapped_column(Text, primary_key=True)

    exercise: Mapped[ExerciseRow] = relationship(back_populates="muscles")


class ExerciseVideoRow(Base):
    __tablename__ = "exercise_videos"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    exercise_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("exercises.id", ondelete="CASCADE"),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    exercise: Mapped[ExerciseRow] = relationship(back_populates="videos")


class ProgramRow(Base):
    __tablename__ = "programs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    program_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    distribution_code: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_program_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("programs.id"))
    source_author_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    assigned_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    author_label: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    days: Mapped[list[WorkoutDayRow]] = relationship(
        back_populates="program",
        cascade="all, delete-orphan",
        lazy="selectin",
        foreign_keys="WorkoutDayRow.program_id",
    )


class ProposalRow(Base):
    __tablename__ = "proposals"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    program_type: Mapped[str | None] = mapped_column(Text)
    base_program_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("programs.id"))
    base_session_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("sessions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    days: Mapped[list[WorkoutDayRow]] = relationship(
        back_populates="proposal",
        cascade="all, delete-orphan",
        lazy="selectin",
        foreign_keys="WorkoutDayRow.proposal_id",
    )


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_day_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    day: Mapped[WorkoutDayRow | None] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
        uselist=False,
        foreign_keys="WorkoutDayRow.session_id",
    )


class WorkoutDayRow(Base):
    __tablename__ = "workout_days"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    program_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("programs.id", ondelete="CASCADE"),
    )
    proposal_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("proposals.id", ondelete="CASCADE"),
    )
    session_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
    )
    weekday: Mapped[int | None] = mapped_column(SmallInteger)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    intensity: Mapped[str] = mapped_column(Text, nullable=False, server_default="medium")
    training_style: Mapped[str] = mapped_column(Text, nullable=False, server_default="classic")
    warmup: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    cooldown: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    program: Mapped[ProgramRow | None] = relationship(back_populates="days", foreign_keys=[program_id])
    proposal: Mapped[ProposalRow | None] = relationship(back_populates="days", foreign_keys=[proposal_id])
    session: Mapped[SessionRow | None] = relationship(back_populates="day", foreign_keys=[session_id])
    slots: Mapped[list[ExerciseSlotRow]] = relationship(
        back_populates="day",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ExerciseSlotRow.position",
    )


class ExerciseSlotRow(Base):
    __tablename__ = "exercise_slots"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    day_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workout_days.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    exercise_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("exercises.id"))
    custom_request: Mapped[str | None] = mapped_column(Text)
    muscle_group: Mapped[str | None] = mapped_column(Text)
    sets: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    reps: Mapped[int | None] = mapped_column(SmallInteger)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    rest_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    rpe: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    technique_note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    day: Mapped[WorkoutDayRow] = relationship(back_populates="slots")
    actual: Mapped[SlotActualRow | None] = relationship(
        back_populates="slot",
        cascade="all, delete-orphan",
        lazy="selectin",
        uselist=False,
    )


class SlotActualRow(Base):
    __tablename__ = "slot_actuals"

    slot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("exercise_slots.id", ondelete="CASCADE"),
        primary_key=True,
    )
    sets: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    reps: Mapped[int | None] = mapped_column(SmallInteger)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    slot: Mapped[ExerciseSlotRow] = relationship(back_populates="actual")


class TechniqueVideoRow(Base):
    __tablename__ = "technique_videos"

    slot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("exercise_slots.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    object_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    telegram_file_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class NutritionRecommendationRow(Base):
    __tablename__ = "nutrition_recommendations"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    program_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("programs.id"), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    kcal: Mapped[Decimal] = mapped_column(Numeric(7, 1), nullable=False)
    protein_g: Mapped[Decimal] = mapped_column(Numeric(6, 1), nullable=False)
    fat_g: Mapped[Decimal] = mapped_column(Numeric(6, 1), nullable=False)
    carb_g: Mapped[Decimal] = mapped_column(Numeric(6, 1), nullable=False)
    calculation: Mapped[str] = mapped_column(Text, nullable=False)
    meal_regularity: Mapped[str] = mapped_column(Text, nullable=False)
    sports_nutrition: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_sex: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_birth_year: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_height_cm: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False)
    snapshot_weight_kg: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    snapshot_days_per_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    snapshot_program_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CoachProfileRow(Base):
    __tablename__ = "coach_profiles"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    bio: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    portfolio_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="none")
    accepting_clients: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    rating_avg: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CoachApplicationRow(Base):
    __tablename__ = "coach_applications"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    bio: Mapped[str] = mapped_column(Text, nullable=False)
    portfolio_url: Mapped[str] = mapped_column(Text, nullable=False)
    credential_object_key: Mapped[str] = mapped_column(Text, nullable=False)
    credential_content_type: Mapped[str] = mapped_column(Text, nullable=False)
    credential_byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    credential_caption: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    moderator_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))


class CoachApplicationModeratorMessageRow(Base):
    __tablename__ = "coach_application_moderator_messages"
    __table_args__ = (UniqueConstraint("application_id", "moderator_user_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    application_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("coach_applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    moderator_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    media_message_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CoachInviteRow(Base):
    __tablename__ = "coach_invites"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    coach_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uses_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_uses: Mapped[int | None] = mapped_column(Integer)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CoachClientLinkRow(Base):
    __tablename__ = "coach_client_links"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    coach_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    client_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))


class CoachReviewRow(Base):
    __tablename__ = "coach_reviews"
    __table_args__ = (UniqueConstraint("coach_user_id", "author_user_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    coach_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    stars: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CoachReportRow(Base):
    __tablename__ = "coach_reports"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    reporter_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    coach_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CoachNoteRow(Base):
    __tablename__ = "coach_notes"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    coach_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    client_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    visibility: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
    )
    slot_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("exercise_slots.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProgressPhotoSetRow(Base):
    __tablename__ = "progress_photo_sets"
    __table_args__ = (UniqueConstraint("user_id", "local_date", name="uq_progress_photo_sets_user_local_date"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    photos: Mapped[list[ProgressPhotoRow]] = relationship(
        back_populates="photo_set",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ProgressPhotoRow(Base):
    __tablename__ = "progress_photos"
    __table_args__ = (UniqueConstraint("set_id", "angle", name="uq_progress_photos_set_angle"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    set_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("progress_photo_sets.id", ondelete="CASCADE"),
        nullable=False,
    )
    angle: Mapped[str] = mapped_column(Text, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    telegram_file_id: Mapped[str | None] = mapped_column(Text)

    photo_set: Mapped[ProgressPhotoSetRow] = relationship(back_populates="photos")


class ProgressPhotoReminderRow(Base):
    __tablename__ = "progress_photo_reminders"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    local_time: Mapped[time] = mapped_column(Time, nullable=False)
    last_sent_on: Mapped[date | None] = mapped_column(Date)

    weekdays: Mapped[list[ProgressPhotoReminderWeekdayRow]] = relationship(
        back_populates="reminder",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ProgressPhotoReminderWeekdayRow(Base):
    __tablename__ = "progress_photo_reminder_weekdays"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("progress_photo_reminders.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    weekday: Mapped[int] = mapped_column(SmallInteger, primary_key=True)

    reminder: Mapped[ProgressPhotoReminderRow] = relationship(back_populates="weekdays")


class FeedbackTicketRow(Base):
    __tablename__ = "feedback_tickets"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    author_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    moderator_reply: Mapped[str | None] = mapped_column(Text)
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    photo_file_ids: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FeedbackModeratorMessageRow(Base):
    __tablename__ = "feedback_moderator_messages"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    ticket_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("feedback_tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    moderator_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WellbeingEntryRow(Base):
    __tablename__ = "wellbeing_entries"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    proposal_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("proposals.id", ondelete="SET NULL"),
    )


# Satisfy UniqueConstraint import used via table args in future migrations if needed.
_ = UniqueConstraint
