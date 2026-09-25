from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from fitness_bot.domain.body.wellbeing import WellbeingEntry
from fitness_bot.infrastructure.db.models import WellbeingEntryRow
from fitness_bot.service.interfaces.uow import IWellbeingRepository


def _to_domain(row: WellbeingEntryRow) -> WellbeingEntry:
    return WellbeingEntry(
        id=row.id,
        user_id=row.user_id,
        text=row.text,
        created_at=row.created_at,
        applied_at=row.applied_at,
    )


class SqlAlchemyWellbeingRepository(IWellbeingRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: WellbeingEntry) -> WellbeingEntry:
        row = WellbeingEntryRow(
            id=entry.id,
            user_id=entry.user_id,
            text=entry.text,
            created_at=entry.created_at,
            applied_at=entry.applied_at,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_domain(row)

    async def list_recent(self, user_id: UUID, *, limit: int = 20) -> list[WellbeingEntry]:
        result = await self._session.execute(
            select(WellbeingEntryRow)
            .where(WellbeingEntryRow.user_id == user_id)
            .order_by(WellbeingEntryRow.created_at.desc())
            .limit(limit),
        )
        return [_to_domain(row) for row in result.scalars().all()]

    async def list_unapplied(self, user_id: UUID, *, limit: int = 20) -> list[WellbeingEntry]:
        result = await self._session.execute(
            select(WellbeingEntryRow)
            .where(
                WellbeingEntryRow.user_id == user_id,
                WellbeingEntryRow.applied_at.is_(None),
            )
            .order_by(WellbeingEntryRow.created_at.desc())
            .limit(limit),
        )
        return [_to_domain(row) for row in result.scalars().all()]

    async def mark_applied(self, entry_ids: list[UUID], *, applied_at: datetime | None = None) -> None:
        if not entry_ids:
            return
        moment = applied_at or datetime.now(UTC)
        await self._session.execute(
            update(WellbeingEntryRow)
            .where(WellbeingEntryRow.id.in_(entry_ids))
            .values(applied_at=moment),
        )
