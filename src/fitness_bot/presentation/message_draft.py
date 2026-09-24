from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from aiogram import Bot

from fitness_bot.service.ports.generation_stream import generation_delta_scope

logger = logging.getLogger(__name__)

_REPLY_PARTIAL_RE = re.compile(r'"reply"\s*:\s*"((?:\\.|[^"\\])*)', re.DOTALL)
_MIN_UPDATE_INTERVAL_S = 0.35
_DRAFT_TEXT_MAX = 3900
_WAITING_CHAR_DELAY_S = 0.045
_WAITING_PHRASE_INTERVAL_S = 5.0
_WAITING_PHRASES: tuple[str, ...] = (
    "Собираю план...",
    "Подбираю упражнения...",
    "Сверяю нагрузку...",
    "Думаю над неделей...",
)


def draft_preview_from_partial(raw: str) -> str:
    """Extract a user-visible preview from a partial JSON model response."""
    match = _REPLY_PARTIAL_RE.search(raw)
    if match is None:
        return ""
    try:
        return str(json.loads(f'"{match.group(1)}"'))
    except (json.JSONDecodeError, ValueError):
        return match.group(1)


def assistant_parse_failure_text(
    reply: str | None = None,
    *,
    hint: str = "Не удалось разобрать ответ помощника. Скажи иначе.",
) -> str:
    """Final bot reply: keep streamed/parsed reply with the parse-failure hint.

    Sending only the hint after ``sendMessageDraft`` showed a different reply leaves
    two bubbles on some Telegram clients (draft text ≠ final sendMessage text).
    """
    cleaned = (reply or "").strip()
    if cleaned:
        return f"{cleaned}\n\n{hint}"
    return hint


class MessageDraftStream:
    """Telegram Bot API sendMessageDraft live preview (ephemeral until sendMessage).

    While the model has not yet produced a ``reply`` preview, cycles short Russian
    waiting lines: each is typed character-by-character, then replaced every
    ``_WAITING_PHRASE_INTERVAL_S`` seconds (clear draft → next phrase).
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        *,
        draft_id: int | None = None,
        waiting_phrases: Sequence[str] | None = None,
        waiting_char_delay_s: float = _WAITING_CHAR_DELAY_S,
        waiting_phrase_interval_s: float = _WAITING_PHRASE_INTERVAL_S,
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._draft_id = draft_id if draft_id not in (None, 0) else random.randint(1, 2_147_483_647)
        self._last_text: str | None = None
        self._last_sent_at = 0.0
        self._pending: str | None = None
        self._lock = asyncio.Lock()
        self._has_model_preview = False
        self._waiting_task: asyncio.Task[None] | None = None
        self._waiting_phrases = tuple(waiting_phrases) if waiting_phrases else _WAITING_PHRASES
        self._waiting_char_delay_s = waiting_char_delay_s
        self._waiting_phrase_interval_s = waiting_phrase_interval_s

    @property
    def draft_id(self) -> int:
        return self._draft_id

    @property
    def preview_text(self) -> str:
        """Last user-visible *model* reply preview (waiting phrases are excluded)."""
        return self._pending or ""

    async def start(self) -> None:
        await self._send("")
        if self._waiting_phrases:
            self._waiting_task = asyncio.create_task(self._waiting_loop(), name="message-draft-waiting")

    async def publish_accumulated(self, raw: str) -> None:
        preview = draft_preview_from_partial(raw).strip()
        if not preview:
            return
        if len(preview) > _DRAFT_TEXT_MAX:
            preview = preview[:_DRAFT_TEXT_MAX]
        await self._stop_waiting()
        first_model_preview = self._pending is None
        self._pending = preview
        await self._send(preview, throttle=not first_model_preview)

    async def flush(self) -> None:
        await self._stop_waiting()
        if self._pending is not None:
            await self._send(self._pending, throttle=False)

    async def aclose(self) -> None:
        await self._stop_waiting()

    async def _stop_waiting(self) -> None:
        self._has_model_preview = True
        task = self._waiting_task
        self._waiting_task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _waiting_loop(self) -> None:
        index = 0
        try:
            while not self._has_model_preview:
                phrase = self._waiting_phrases[index % len(self._waiting_phrases)]
                started = time.monotonic()
                for end in range(1, len(phrase) + 1):
                    if self._has_model_preview:
                        return
                    await self._send(phrase[:end], throttle=False, waiting=True)
                    await asyncio.sleep(self._waiting_char_delay_s)
                elapsed = time.monotonic() - started
                remaining = self._waiting_phrase_interval_s - elapsed
                if remaining > 0:
                    await asyncio.sleep(remaining)
                if self._has_model_preview:
                    return
                # Clear the ephemeral draft so the next line feels like a fresh bubble.
                await self._send("", waiting=True)
                index += 1
        except asyncio.CancelledError:
            raise

    async def _send(self, text: str, *, throttle: bool = False, waiting: bool = False) -> None:
        async with self._lock:
            if waiting and self._has_model_preview:
                return
            if text == self._last_text:
                return
            now = time.monotonic()
            if throttle and self._last_text is not None and (now - self._last_sent_at) < _MIN_UPDATE_INTERVAL_S:
                return
            try:
                await self._bot.send_message_draft(
                    chat_id=self._chat_id,
                    draft_id=self._draft_id,
                    text=text,
                )
            except Exception:
                logger.warning("send_message_draft failed", exc_info=True)
                return
            self._last_text = text
            self._last_sent_at = now


@asynccontextmanager
async def message_draft_scope(bot: Bot, chat_id: int) -> AsyncIterator[MessageDraftStream]:
    draft = MessageDraftStream(bot, chat_id)
    await draft.start()
    async with generation_delta_scope(draft.publish_accumulated):
        try:
            yield draft
        finally:
            await draft.aclose()
            await draft.flush()
