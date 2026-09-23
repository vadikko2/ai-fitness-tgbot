from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar, Token

GenerationDeltaHandler = Callable[[str], Awaitable[None]]

_generation_delta: ContextVar[GenerationDeltaHandler | None] = ContextVar(
    "generation_delta",
    default=None,
)


@contextmanager
def bind_generation_delta(handler: GenerationDeltaHandler | None) -> Iterator[None]:
    token: Token[GenerationDeltaHandler | None] = _generation_delta.set(handler)
    try:
        yield
    finally:
        _generation_delta.reset(token)


async def emit_generation_delta(text: str) -> None:
    handler = _generation_delta.get()
    if handler is not None:
        await handler(text)


@asynccontextmanager
async def generation_delta_scope(handler: GenerationDeltaHandler | None) -> AsyncIterator[None]:
    with bind_generation_delta(handler):
        yield
