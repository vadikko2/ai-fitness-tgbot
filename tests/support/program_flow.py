from __future__ import annotations

from fitness_bot.domain.enums import ProgramType
from fitness_bot.infrastructure.uow.in_memory import InMemoryUow
from fitness_bot.service.handlers.commands.program import ChooseProgramTypeCommandHandler
from fitness_bot.service.models.commands.program import ChooseProgramTypeCommand


async def choose_program_structure(
    uow: InMemoryUow,
    *,
    telegram_user_id: int = 7,
    program_type: ProgramType = ProgramType.FULL_BODY,
) -> None:
    await ChooseProgramTypeCommandHandler(uow).handle(
        ChooseProgramTypeCommand(telegram_user_id=telegram_user_id, program_type=program_type),
    )


# Backward-compatible alias for tests importing the old name.
choose_program_structure_and_style = choose_program_structure
