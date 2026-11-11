"""Widget screens without Telegram: commands, phases, glyphs, zlib."""

from __future__ import annotations

import json
import zlib
from types import SimpleNamespace
from uuid import uuid4

from fitness_bot.domain.enums import ProfileField, ProgramType, Sex
from fitness_bot.domain.workout.document import ExerciseSlot, WorkoutDay, WorkoutDocument
from fitness_bot.presentation.widgets.frame import WidgetBinding, WidgetFrame, WidgetScreenId
from fitness_bot.presentation.widgets.glyphs import exercise_glyph_path
from fitness_bot.presentation.widgets.screen import ScreenContext
from fitness_bot.presentation.widgets.screens.console import ConsoleScreen
from fitness_bot.presentation.widgets.screens.intake import IntakeScreen, measurement_guide_png
from fitness_bot.presentation.widgets.screens.load import load_shells
from fitness_bot.presentation.widgets.screens.week import WeekScreen
from fitness_bot.presentation.widgets.state import pack_state
from fitness_bot.service.models.commands.program import ApproveProposalCommand
from fitness_bot.service.models.commands.session import (
    ConfirmExerciseAsPlannedCommand,
    RecordSlotActualCommand,
)
from fitness_bot.service.models.commands.users import UpdateProfileCommand
from fitness_bot.service.models.queries.session import GetTodayWorkoutQuery
from fitness_bot.service.models.queries.users import GetProfileQuery


class _Shell:
    def __init__(self, html: str = "<b>ok</b>", shell_id: str = "console") -> None:
        self.shell_id = shell_id
        self._html = html

    def html(self) -> str:
        return self._html


class _Mediator:
    def __init__(self, replies: dict[type[object], object] | None = None) -> None:
        self.sent: list[object] = []
        self.replies = replies or {}
        self.profiles: list[object] = []

    async def send(self, request: object) -> object:
        self.sent.append(request)
        if isinstance(request, GetProfileQuery) and self.profiles:
            return self.profiles.pop(0)
        for kind, reply in self.replies.items():
            if isinstance(request, kind):
                return reply
        return SimpleNamespace(
            blocked_empty=False,
            blocked_unresolved=False,
            blocked_schedule=False,
            names={},
            primary_muscles={},
            items=[],
            document=None,
        )


def _ctx(mediator: _Mediator, frame: WidgetFrame | None = None, *, screen: WidgetScreenId) -> ScreenContext:
    return ScreenContext(
        user_id=7,
        binding=WidgetBinding(chat_id=7, message_id=3, screen=screen, frame=frame),
        mediator=mediator,  # type: ignore[arg-type]
    )


def _rebind(ctx: ScreenContext, frame: WidgetFrame) -> ScreenContext:
    return ScreenContext(
        user_id=ctx.user_id,
        binding=WidgetBinding(
            chat_id=ctx.binding.chat_id,
            message_id=ctx.binding.message_id,
            screen=ctx.binding.screen,
            frame=frame,
        ),
        mediator=ctx.mediator,
    )


def _workout() -> WorkoutDocument:
    return WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(
                weekday=1,
                title="Ноги",
                position=1,
                slots=[
                    ExerciseSlot(
                        position=1,
                        exercise_id=uuid4(),
                        sets=3,
                        reps=8,
                        rest_seconds=90,
                        rpe=7,
                    ),
                ],
            ),
        ],
    )


def _console() -> tuple[ConsoleScreen, _Mediator, ScreenContext]:
    today = SimpleNamespace(document=_workout(), screen="session", technique_video_positions=[], weekday=1)
    mediator = _Mediator({GetTodayWorkoutQuery: today})
    screen = ConsoleScreen({"male": _Shell("male-shell"), "female": _Shell("female-shell")})
    return screen, mediator, _ctx(mediator, screen=WidgetScreenId.CONSOLE)


def _writes(mediator: _Mediator) -> list[object]:
    return [
        item for item in mediator.sent if isinstance(item, (RecordSlotActualCommand, ConfirmExerciseAsPlannedCommand))
    ]


async def test_console_ok_records_a_set_and_a_second_ok_in_rest_writes_nothing() -> None:
    screen, mediator, ctx = _console()
    frame = await screen.open(ctx)
    stepped = await screen.apply(_rebind(ctx, frame), "r+")
    assert _writes(mediator) == []
    recorded = await screen.apply(_rebind(ctx, stepped.frame), "ok")
    assert any(isinstance(item, RecordSlotActualCommand) for item in mediator.sent)
    assert json.loads(recorded.frame.chat_data)["ph"] == "rest"
    before = len(mediator.sent)
    again = await screen.apply(_rebind(ctx, recorded.frame), "ok")
    assert len(mediator.sent) == before
    assert json.loads(again.frame.chat_data)["ph"] == "rest"


async def test_console_sync_after_rest_until_advances_the_phase() -> None:
    screen, mediator, ctx = _console()
    data = {
        "ph": "rest",
        "restUntil": 1,
        "set": 1,
        "sets": 3,
        "i": 1,
        "n": 1,
        "pos": 1,
        "name": "Присед",
        "plan": "3×8 · 90 с",
        "kg": None,
        "reps": 8,
        "glyph": "q",
        "log": 1,
        "rest": 90,
    }
    frame = WidgetFrame(
        screen=WidgetScreenId.CONSOLE,
        chat_data=pack_state(data),
        caption="Отдых",
        shell_id="console",
    )
    result = await screen.apply(_rebind(ctx, frame), "sync")
    body = json.loads(result.frame.chat_data)
    assert body["ph"] == "work"
    assert body["set"] == 2
    assert _writes(mediator) == []


async def test_console_shell_follows_profile_sex() -> None:
    screen = ConsoleScreen({"male": _Shell("male-shell"), "female": _Shell("female-shell")})
    female = SimpleNamespace(sex=Sex.FEMALE)
    unknown = SimpleNamespace(sex=None)
    mediator = _Mediator()
    mediator.profiles = [female, unknown]
    ctx = _ctx(mediator, screen=WidgetScreenId.CONSOLE)
    assert await screen.html_for(ctx) == "female-shell"
    assert await screen.html_for(ctx) == "male-shell"


def test_glyph_path_uses_the_sex_folder(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("fitness_bot.presentation.widgets.glyphs.EXERCISE_GLYPHS_DIR", tmp_path)
    assert exercise_glyph_path("q", sex=Sex.FEMALE) is None
    assert exercise_glyph_path("q", sex=None) is None
    female = tmp_path / "female"
    female.mkdir()
    (female / "squat.png").write_bytes(b"png")
    (tmp_path / "squat.png").write_bytes(b"flat")
    found = exercise_glyph_path("q", sex=Sex.FEMALE)
    assert found is not None
    assert found.parent.name == "female"
    assert exercise_glyph_path("q", sex=Sex.MALE) is None
    assert exercise_glyph_path("q", sex=None) is None


def test_measurement_png_uses_guide_sex_folder(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "fitness_bot.presentation.widgets.screens.intake.MEASUREMENT_GUIDES_DIR",
        tmp_path,
    )
    assert measurement_guide_png("waist", Sex.FEMALE) is None
    female = tmp_path / "female"
    female.mkdir()
    (female / "waist.png").write_bytes(b"png")
    found = measurement_guide_png("waist", Sex.FEMALE)
    assert found is not None
    assert found.endswith("/female/waist.png")
    assert measurement_guide_png("waist", None) is None
    assert measurement_guide_png("height", Sex.FEMALE) is None


async def test_intake_pick_sends_update_profile() -> None:
    first = SimpleNamespace(
        profile_complete=False,
        next_field=ProfileField.SEX,
        goal=None,
        sex=None,
        days_per_week=None,
        birth_year=None,
        height_cm=None,
        weight_kg=None,
        body_fat_pct=None,
        session_minutes=None,
    )
    second = SimpleNamespace(
        profile_complete=False,
        next_field=ProfileField.BIRTH_YEAR,
        goal=None,
        sex=Sex.MALE,
        days_per_week=None,
        birth_year=None,
        height_cm=None,
        weight_kg=None,
        body_fat_pct=None,
        session_minutes=None,
    )
    mediator = _Mediator()
    mediator.profiles = [first, second]
    screen = IntakeScreen(_Shell(shell_id="intake"))
    ctx = _ctx(mediator, screen=WidgetScreenId.INTAKE)
    frame = await screen.open(ctx)
    result = await screen.apply(_rebind(ctx, frame), "pick:male")
    updates = [item for item in mediator.sent if isinstance(item, UpdateProfileCommand)]
    assert updates
    assert updates[0].field is ProfileField.SEX
    assert updates[0].value == "male"
    assert json.loads(result.frame.chat_data)["step"] == "birth_year"


async def test_week_approve_sends_approve_proposal() -> None:
    mediator = _Mediator()
    screen = WeekScreen(_Shell(shell_id="week"))
    frame = WidgetFrame(
        screen=WidgetScreenId.WEEK,
        chat_data=pack_state({"day": 0, "title": "Ноги", "slots": [], "sel": 0}),
        caption="Черновик",
        shell_id="week",
    )
    ctx = _ctx(mediator, frame, screen=WidgetScreenId.WEEK)
    result = await screen.apply(ctx, "approve")
    assert any(isinstance(item, ApproveProposalCommand) for item in mediator.sent)
    assert result.navigate is WidgetScreenId.HOME


def test_shell_zlib_stays_within_4096() -> None:
    shells = load_shells()
    sizes = {key: len(zlib.compress(shell.html().encode("utf-8"), 9)) for key, shell in shells.items()}
    assert sizes
    assert all(size <= 4096 for size in sizes.values()), sizes
