from __future__ import annotations

from datetime import date
from uuid import uuid4

from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from fitness_bot.presentation.keyboards import profile_reminders_keyboard, training_reminder_keyboard
from fitness_bot.presentation.scheduler import handle_training_ask
from fitness_bot.presentation.templates_env import create_jinja_env
from fitness_bot.service.models.commands.training_reminder import (
    DisableTrainingRemindersCommand,
    MarkTrainingReminderSentCommand,
)
from fitness_bot.service.models.queries.training_reminder import DueTrainingReminderItem


def _callbacks(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _labels(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def test_profile_toggles_default_on() -> None:
    markup = profile_reminders_keyboard()
    assert "tr_tog:evening" in _callbacks(markup)
    assert "tr_tog:morning" in _callbacks(markup)
    labels = _labels(markup)
    assert "🌙 Завтра тренировка: вкл" in labels
    assert "☀️ Сегодня тренировка: вкл" in labels
    off = _labels(profile_reminders_keyboard(evening_enabled=False, morning_enabled=False))
    assert "🌙 Завтра тренировка: выкл" in off
    assert "☀️ Сегодня тренировка: выкл" in off


def test_reminder_buttons_split_morning_start_and_evening_draft() -> None:
    morning = training_reminder_keyboard(kind="morning", target_date=date(2026, 10, 19))
    assert _callbacks(morning) == ["sess_go", "tr_skip:2026-10-19"]
    assert _labels(morning) == ["✅ Да", "🚫 Пропущу"]
    evening = training_reminder_keyboard(kind="evening", target_date=date(2026, 10, 20))
    assert _callbacks(evening) == ["tr_yes:2026-10-20", "tr_skip:2026-10-20"]
    assert _labels(evening) == ["✅ Да, завтра", "🚫 Пропущу"]


def test_reminder_copy() -> None:
    env = create_jinja_env()
    evening = env.get_template("training_reminder.j2").render(kind="evening", day_title="Ноги")
    morning = env.get_template("training_reminder.j2").render(kind="morning", day_title="Верх <b>")
    assert evening.strip() == "Завтра тренировка: Ноги. Идёшь?"
    assert morning.strip() == "Сегодня тренировка: Верх &lt;b&gt;. Идёшь?"
    settings = env.get_template("training_reminder_settings.j2").render()
    assert "20:00" in settings
    assert "09:00" in settings
    assert "UTC" in settings


class _Mediator:
    def __init__(self) -> None:
        self.sent: list[object] = []

    async def send(self, request: object) -> None:
        self.sent.append(request)


class _Bot:
    def __init__(self, *, forbidden: bool = False) -> None:
        self.forbidden = forbidden
        self.sent: list[dict] = []

    async def send_message(self, **kwargs) -> None:
        if self.forbidden:
            raise TelegramForbiddenError(method=SendMessage, message="Forbidden: bot was blocked by the user")
        self.sent.append(kwargs)


def _item() -> DueTrainingReminderItem:
    return DueTrainingReminderItem(
        user_id=uuid4(),
        telegram_user_id=1,
        chat_id=10,
        kind="evening",
        target_date=date(2026, 10, 20),
        sent_on=date(2026, 10, 19),
        day_title="Ноги",
        weekday=2,
    )


async def test_training_ask_marks_sent_after_delivery() -> None:
    mediator = _Mediator()
    bot = _Bot()
    await handle_training_ask(bot=bot, mediator=mediator, jinja_env=create_jinja_env(), item=_item())
    assert bot.sent[0]["text"].strip() == "Завтра тренировка: Ноги. Идёшь?"
    assert isinstance(mediator.sent[0], MarkTrainingReminderSentCommand)
    assert mediator.sent[0].kind == "evening"
    assert mediator.sent[0].sent_on == date(2026, 10, 19)


async def test_blocked_bot_disables_reminders_without_marking_sent() -> None:
    mediator = _Mediator()
    await handle_training_ask(bot=_Bot(forbidden=True), mediator=mediator, jinja_env=create_jinja_env(), item=_item())
    assert len(mediator.sent) == 1
    assert isinstance(mediator.sent[0], DisableTrainingRemindersCommand)
