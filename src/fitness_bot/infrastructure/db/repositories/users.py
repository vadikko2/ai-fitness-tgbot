from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fitness_bot.domain.users.user import User
from fitness_bot.infrastructure.db.mappers import apply_user_to_row, user_to_domain
from fitness_bot.infrastructure.db.models import UserRow
from fitness_bot.service.interfaces.uow import IUsersRepository


class SqlAlchemyUsersRepository(IUsersRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_user_id: int) -> User | None:
        stmt = (
            select(UserRow)
            .where(UserRow.telegram_user_id == telegram_user_id)
            .options(selectinload(UserRow.training_weekdays))
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return user_to_domain(row) if row else None

    async def get_by_id(self, user_id: UUID) -> User | None:
        stmt = select(UserRow).where(UserRow.id == user_id).options(selectinload(UserRow.training_weekdays))
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return user_to_domain(row) if row else None

    async def add(self, user: User) -> User:
        row = UserRow(id=user.id, telegram_user_id=user.telegram_user_id, chat_id=user.chat_id)
        apply_user_to_row(row, user)
        row.created_at = user.created_at
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row, attribute_names=["training_weekdays"])
        return user_to_domain(row)

    async def ensure(self, *, telegram_user_id: int, chat_id: int) -> tuple[User, bool]:
        existing = await self.get_by_telegram_id(telegram_user_id)
        if existing is not None:
            return await self._sync_chat_id(existing, chat_id), False

        candidate = User(telegram_user_id=telegram_user_id, chat_id=chat_id)
        stmt = (
            insert(UserRow)
            .values(
                id=candidate.id,
                telegram_user_id=candidate.telegram_user_id,
                chat_id=candidate.chat_id,
                nutrition_stale=candidate.nutrition_stale,
                expected_input=candidate.expected_input.value,
                created_at=candidate.created_at,
                updated_at=candidate.updated_at,
            )
            .on_conflict_do_nothing(index_elements=[UserRow.telegram_user_id])
            .returning(UserRow.id)
        )
        inserted_id = (await self._session.execute(stmt)).scalar_one_or_none()
        ensured = await self.get_by_telegram_id(telegram_user_id)
        if ensured is None:
            raise RuntimeError(f"failed to ensure user for telegram_user_id={telegram_user_id}")
        if inserted_id is None:
            return await self._sync_chat_id(ensured, chat_id), False
        return ensured, True

    async def save(self, user: User) -> User:
        stmt = select(UserRow).where(UserRow.id == user.id).options(selectinload(UserRow.training_weekdays))
        row = (await self._session.execute(stmt)).scalar_one()
        apply_user_to_row(row, user)
        await self._session.flush()
        return user_to_domain(row)

    async def list_with_timezone(self) -> list[User]:
        stmt = (
            select(UserRow).where(UserRow.timezone_offset.is_not(None)).options(selectinload(UserRow.training_weekdays))
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [user_to_domain(row) for row in rows]

    async def list_moderators(self) -> list[User]:
        stmt = select(UserRow).where(UserRow.is_moderator.is_(True)).options(selectinload(UserRow.training_weekdays))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [user_to_domain(row) for row in rows]

    async def count_moderators(self) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(UserRow).where(UserRow.is_moderator.is_(True))
        return int((await self._session.execute(stmt)).scalar_one())

    async def _sync_chat_id(self, user: User, chat_id: int) -> User:
        if user.chat_id == chat_id:
            return user
        user.chat_id = chat_id
        user.updated_at = datetime.now(UTC)
        return await self.save(user)
