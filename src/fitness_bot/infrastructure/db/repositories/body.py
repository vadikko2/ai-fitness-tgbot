from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fitness_bot.domain.body.measurement import MeasurementEntry, MeasurementGuide, MeasurementSite
from fitness_bot.domain.body.progress_photo import ProgressPhotoSet
from fitness_bot.domain.body.reminder import ProgressPhotoReminder, WeightReminder
from fitness_bot.domain.body.weight import WeightEntry
from fitness_bot.infrastructure.db.mappers import (
    apply_progress_photo_reminder_to_row,
    apply_progress_photo_set_to_row,
    apply_reminder_to_row,
    apply_weight_to_row,
    guide_to_domain,
    measurement_to_domain,
    new_measurement_row,
    new_site_row,
    new_weight_row,
    progress_photo_reminder_to_domain,
    progress_photo_set_to_domain,
    reminder_to_domain,
    site_to_domain,
    weight_to_domain,
)
from fitness_bot.infrastructure.db.models import (
    MeasurementEntryRow,
    MeasurementGuideRow,
    MeasurementSiteRow,
    ProgressPhotoReminderRow,
    ProgressPhotoSetRow,
    WeightEntryRow,
    WeightReminderRow,
)
from fitness_bot.service.interfaces.uow import (
    IMeasurementRepository,
    IProgressPhotoReminderRepository,
    IProgressPhotoRepository,
    IWeightReminderRepository,
    IWeightRepository,
)


class SqlAlchemyWeightRepository(IWeightRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_for_local_day(
        self,
        entry: WeightEntry,
        *,
        day_start: datetime,
        day_end: datetime,
    ) -> WeightEntry:
        stmt = (
            select(WeightEntryRow)
            .where(
                WeightEntryRow.user_id == entry.user_id,
                WeightEntryRow.measured_at >= day_start,
                WeightEntryRow.measured_at < day_end,
            )
            .order_by(WeightEntryRow.measured_at.desc())
        )
        rows = list((await self._session.execute(stmt)).scalars().all())
        if not rows:
            row = new_weight_row(entry)
            self._session.add(row)
            await self._session.flush()
            return weight_to_domain(row)
        primary = rows[0]
        kept = entry.model_copy(update={"id": primary.id})
        apply_weight_to_row(primary, kept)
        for extra in rows[1:]:
            await self._session.delete(extra)
        await self._session.flush()
        return weight_to_domain(primary)

    async def latest_for_user(self, user_id: UUID) -> WeightEntry | None:
        stmt = (
            select(WeightEntryRow)
            .where(WeightEntryRow.user_id == user_id)
            .order_by(WeightEntryRow.measured_at.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return weight_to_domain(row) if row else None

    async def history_for_user(self, user_id: UUID, *, limit: int = 50) -> list[WeightEntry]:
        stmt = (
            select(WeightEntryRow)
            .where(WeightEntryRow.user_id == user_id)
            .order_by(WeightEntryRow.measured_at.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [weight_to_domain(row) for row in rows]


class SqlAlchemyWeightReminderRepository(IWeightReminderRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UUID) -> WeightReminder | None:
        stmt = (
            select(WeightReminderRow)
            .where(WeightReminderRow.user_id == user_id)
            .options(selectinload(WeightReminderRow.weekdays))
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return reminder_to_domain(row) if row else None

    async def save(self, reminder: WeightReminder) -> WeightReminder:
        stmt = (
            select(WeightReminderRow)
            .where(WeightReminderRow.user_id == reminder.user_id)
            .options(selectinload(WeightReminderRow.weekdays))
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = WeightReminderRow(user_id=reminder.user_id, local_time=reminder.local_time)
            self._session.add(row)
            await self._session.flush()
            await self._session.refresh(row, attribute_names=["weekdays"])
        apply_reminder_to_row(row, reminder)
        await self._session.flush()
        return reminder_to_domain(row)

    async def list_all(self) -> list[WeightReminder]:
        stmt = select(WeightReminderRow).options(selectinload(WeightReminderRow.weekdays))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [reminder_to_domain(row) for row in rows]


class SqlAlchemyProgressPhotoRepository(IProgressPhotoRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_set(self, set_id: UUID) -> ProgressPhotoSet | None:
        stmt = (
            select(ProgressPhotoSetRow)
            .where(ProgressPhotoSetRow.id == set_id)
            .options(selectinload(ProgressPhotoSetRow.photos))
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return progress_photo_set_to_domain(row) if row else None

    async def get_incomplete_for_user(self, user_id: UUID) -> ProgressPhotoSet | None:
        stmt = (
            select(ProgressPhotoSetRow)
            .where(
                ProgressPhotoSetRow.user_id == user_id,
                ProgressPhotoSetRow.complete.is_(False),
            )
            .options(selectinload(ProgressPhotoSetRow.photos))
            .order_by(ProgressPhotoSetRow.local_date.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return progress_photo_set_to_domain(row) if row else None

    async def get_for_user_local_date(self, user_id: UUID, local_date: date) -> ProgressPhotoSet | None:
        stmt = (
            select(ProgressPhotoSetRow)
            .where(
                ProgressPhotoSetRow.user_id == user_id,
                ProgressPhotoSetRow.local_date == local_date,
            )
            .options(selectinload(ProgressPhotoSetRow.photos))
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return progress_photo_set_to_domain(row) if row else None

    async def save_set(self, photo_set: ProgressPhotoSet) -> ProgressPhotoSet:
        stmt = (
            select(ProgressPhotoSetRow)
            .where(ProgressPhotoSetRow.id == photo_set.id)
            .options(selectinload(ProgressPhotoSetRow.photos))
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = ProgressPhotoSetRow(
                id=photo_set.id,
                user_id=photo_set.user_id,
                captured_at=photo_set.captured_at,
                local_date=photo_set.local_date,
                complete=photo_set.complete,
            )
            self._session.add(row)
            await self._session.flush()
            await self._session.refresh(row, attribute_names=["photos"])
        apply_progress_photo_set_to_row(row, photo_set)
        await self._session.flush()
        return progress_photo_set_to_domain(row)

    async def list_complete_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 30,
        offset: int = 0,
    ) -> list[ProgressPhotoSet]:
        stmt = (
            select(ProgressPhotoSetRow)
            .where(
                ProgressPhotoSetRow.user_id == user_id,
                ProgressPhotoSetRow.complete.is_(True),
            )
            .options(selectinload(ProgressPhotoSetRow.photos))
            .order_by(ProgressPhotoSetRow.local_date.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [progress_photo_set_to_domain(row) for row in rows]


class SqlAlchemyProgressPhotoReminderRepository(IProgressPhotoReminderRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UUID) -> ProgressPhotoReminder | None:
        stmt = (
            select(ProgressPhotoReminderRow)
            .where(ProgressPhotoReminderRow.user_id == user_id)
            .options(selectinload(ProgressPhotoReminderRow.weekdays))
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return progress_photo_reminder_to_domain(row) if row else None

    async def save(self, reminder: ProgressPhotoReminder) -> ProgressPhotoReminder:
        stmt = (
            select(ProgressPhotoReminderRow)
            .where(ProgressPhotoReminderRow.user_id == reminder.user_id)
            .options(selectinload(ProgressPhotoReminderRow.weekdays))
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = ProgressPhotoReminderRow(user_id=reminder.user_id, local_time=reminder.local_time)
            self._session.add(row)
            await self._session.flush()
            await self._session.refresh(row, attribute_names=["weekdays"])
        apply_progress_photo_reminder_to_row(row, reminder)
        await self._session.flush()
        return progress_photo_reminder_to_domain(row)

    async def list_all(self) -> list[ProgressPhotoReminder]:
        stmt = select(ProgressPhotoReminderRow).options(selectinload(ProgressPhotoReminderRow.weekdays))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [progress_photo_reminder_to_domain(row) for row in rows]


class SqlAlchemyMeasurementRepository(IMeasurementRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_site_by_id(self, site_id: UUID) -> MeasurementSite | None:
        row = await self._session.get(MeasurementSiteRow, site_id)
        return site_to_domain(row) if row else None

    async def get_fixed_site_by_code(self, code: str) -> MeasurementSite | None:
        stmt = select(MeasurementSiteRow).where(
            MeasurementSiteRow.code == code,
            MeasurementSiteRow.is_custom.is_(False),
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return site_to_domain(row) if row else None

    async def list_sites_for_user(self, user_id: UUID) -> list[MeasurementSite]:
        stmt = (
            select(MeasurementSiteRow)
            .where((MeasurementSiteRow.is_custom.is_(False)) | (MeasurementSiteRow.user_id == user_id))
            .order_by(MeasurementSiteRow.is_custom, MeasurementSiteRow.name)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [site_to_domain(row) for row in rows]

    async def add_site(self, site: MeasurementSite) -> MeasurementSite:
        row = new_site_row(site)
        self._session.add(row)
        await self._session.flush()
        return site_to_domain(row)

    async def get_custom_site_by_name(self, user_id: UUID, name: str) -> MeasurementSite | None:
        stmt = select(MeasurementSiteRow).where(
            MeasurementSiteRow.user_id == user_id,
            MeasurementSiteRow.is_custom.is_(True),
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        needle = name.strip().casefold()
        for row in rows:
            if row.name.casefold() == needle:
                return site_to_domain(row)
        return None

    async def get_guide(self, site_id: UUID) -> MeasurementGuide | None:
        row = await self._session.get(MeasurementGuideRow, site_id)
        return guide_to_domain(row) if row else None

    async def upsert_guide(self, guide: MeasurementGuide) -> MeasurementGuide:
        row = await self._session.get(MeasurementGuideRow, guide.site_id)
        if row is None:
            row = MeasurementGuideRow(site_id=guide.site_id, instruction=guide.instruction)
            self._session.add(row)
        else:
            row.instruction = guide.instruction
        await self._session.flush()
        return guide_to_domain(row)

    async def add_entry(self, entry: MeasurementEntry) -> MeasurementEntry:
        row = new_measurement_row(entry)
        self._session.add(row)
        await self._session.flush()
        return measurement_to_domain(row)

    async def history_for_user(
        self,
        user_id: UUID,
        *,
        site_id: UUID | None = None,
        limit: int = 50,
    ) -> list[MeasurementEntry]:
        stmt = select(MeasurementEntryRow).where(MeasurementEntryRow.user_id == user_id)
        if site_id is not None:
            stmt = stmt.where(MeasurementEntryRow.site_id == site_id)
        stmt = stmt.order_by(MeasurementEntryRow.measured_at.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [measurement_to_domain(row) for row in rows]
