from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiogram import Bot

from fitness_bot.service.ports.generation_stream import generation_delta_scope

logger = logging.getLogger(__name__)

_REPLY_PARTIAL_RE = re.compile(r'"reply"\s*:\s*"((?:\\.|[^"\\])*)', re.DOTALL)
_MIN_UPDATE_INTERVAL_S = 0.35
_DRAFT_TEXT_MAX = 3900


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
    """Telegram Bot API sendMessageDraft live preview (ephemeral until sendMessage)."""

    def __init__(self, bot: Bot, chat_id: int, *, draft_id: int | None = None) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._draft_id = draft_id if draft_id not in (None, 0) else random.randint(1, 2_147_483_647)
        self._last_text: str | None = None
        self._last_sent_at = 0.0
        self._pending: str | None = None
        self._lock = asyncio.Lock()

    @property
    def draft_id(self) -> int:
        return self._draft_id

    @property
    def preview_text(self) -> str:
        """Last user-visible draft preview (for merging into the final bot reply)."""
        if self._pending is not None:
            return self._pending
        return self._last_text or ""

    async def start(self) -> None:
        # Empty text → Telegram shows a Thinking… placeholder.
        await self._send("")

    async def publish_accumulated(self, raw: str) -> None:
        preview = draft_preview_from_partial(raw).strip()
        if not preview:
            return
        if len(preview) > _DRAFT_TEXT_MAX:
            preview = preview[:_DRAFT_TEXT_MAX]
        self._pending = preview
        await self._send(preview, throttle=True)

    async def flush(self) -> None:
        if self._pending is not None:
            await self._send(self._pending, throttle=False)

    async def _send(self, text: str, *, throttle: bool = False) -> None:
        async with self._lock:
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
            await draft.flush()
