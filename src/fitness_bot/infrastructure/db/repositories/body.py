from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fitness_bot.domain.body.measurement import MeasurementEntry, MeasurementGuide, MeasurementSite
from fitness_bot.domain.body.reminder import WeightReminder
from fitness_bot.domain.body.weight import WeightEntry
from fitness_bot.infrastructure.db.mappers import (
    apply_reminder_to_row,
    apply_weight_to_row,
    guide_to_domain,
    measurement_to_domain,
    new_measurement_row,
    new_site_row,
    new_weight_row,
    reminder_to_domain,
    site_to_domain,
    weight_to_domain,
)
from fitness_bot.infrastructure.db.models import (
    MeasurementEntryRow,
    MeasurementGuideRow,
    MeasurementSiteRow,
    WeightEntryRow,
    WeightReminderRow,
)
from fitness_bot.service.interfaces.uow import (
    IMeasurementRepository,
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
