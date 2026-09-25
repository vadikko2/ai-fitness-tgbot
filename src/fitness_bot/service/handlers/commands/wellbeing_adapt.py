from __future__ import annotations

from uuid import UUID

# proposal_id → wellbeing entry ids to mark applied on approve
_PENDING_WELLBEING_BY_PROPOSAL: dict[UUID, list[UUID]] = {}


def remember_wellbeing_adapt(*, proposal_id: UUID, entry_ids: list[UUID]) -> None:
    if entry_ids:
        _PENDING_WELLBEING_BY_PROPOSAL[proposal_id] = list(entry_ids)
    else:
        _PENDING_WELLBEING_BY_PROPOSAL.pop(proposal_id, None)


def pop_wellbeing_adapt(proposal_id: UUID) -> list[UUID]:
    return _PENDING_WELLBEING_BY_PROPOSAL.pop(proposal_id, [])


def clear_wellbeing_adapt(proposal_id: UUID | None = None) -> None:
    if proposal_id is None:
        _PENDING_WELLBEING_BY_PROPOSAL.clear()
        return
    _PENDING_WELLBEING_BY_PROPOSAL.pop(proposal_id, None)
