from __future__ import annotations

from fitness_bot.service.models.commands import body as body_commands
from fitness_bot.service.models.commands import users as user_commands
from fitness_bot.service.models.queries import body as body_queries
from fitness_bot.service.models.queries import users as user_queries

__all__ = [
    "body_commands",
    "body_queries",
    "user_commands",
    "user_queries",
]
