from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from fitness_bot.domain.body.wellbeing import WellbeingEntry, fresh_unapplied
from fitness_bot.domain.errors import NoFreshWellbeing
from fitness_bot.service.interfaces.uow import IUowRepositories

WELLBEING_CONTEXT_LIMIT = 20

# Fixed instruction for the explicit «Подстроить под самочувствие» edit paths.
WELLBEING_ADAPT_UTTERANCE = (
    "Подстрой под моё текущее самочувствие (заметки ниже): снизь нагрузку или замени упражнения, "
    "которые могут навредить. Остальное оставь как есть."
)


@dataclass(frozen=True)
class WellbeingContext:
    entries: list[WellbeingEntry] = field(default_factory=list)
    mode: str = ""

    @property
    def entry_ids(self) -> list[UUID]:
        return [entry.id for entry in self.entries]

    @property
    def json(self) -> str:
        if not self.entries:
            return ""
        return json.dumps(
            [{"text": entry.text, "created_at": entry.created_at.isoformat()} for entry in self.entries],
            ensure_ascii=False,
        )

    def prompt_context(self) -> dict[str, str]:
        return {"wellbeing_json": self.json, "wellbeing_mode": self.mode if self.entries else ""}


async def load_wellbeing_context(
    repos: IUowRepositories,
    user_id: UUID,
    *,
    hard: bool = False,
    now: datetime | None = None,
) -> WellbeingContext:
    """Fresh unapplied notes: ``hard`` for explicit adaptation, soft context otherwise."""
    moment = now or datetime.now(UTC)
    entries = fresh_unapplied(
        await repos.wellbeing.list_unapplied(user_id, limit=WELLBEING_CONTEXT_LIMIT),
        now=moment,
    )
    if hard and not entries:
        raise NoFreshWellbeing("no fresh unapplied wellbeing entries")
    return WellbeingContext(entries=entries, mode="hard" if hard else "soft")


async def link_wellbeing_to_proposal(
    repos: IUowRepositories,
    context: WellbeingContext,
    proposal_id: UUID,
) -> None:
    if context.entries:
        await repos.wellbeing.link_to_proposal(context.entry_ids, proposal_id)
