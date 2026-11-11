"""Intake wizard: chips and steppers over the profile commands that already exist."""

from __future__ import annotations

from fitness_bot.domain.body.measurement import FIXED_MEASUREMENT_SITES
from fitness_bot.domain.enums import ExpectedInput, Goal, ProfileField, Sex, WeightSource
from fitness_bot.domain.errors import DomainError
from fitness_bot.presentation.progress_pose_images import guide_sex_folder
from fitness_bot.presentation.widgets.frame import WidgetFrame, WidgetScreenId
from fitness_bot.presentation.widgets.opcodes import OpcodeRejection, parse_opcode
from fitness_bot.presentation.widgets.screen import ScreenContext, ScreenResult
from fitness_bot.presentation.widgets.shell import WidgetShell
from fitness_bot.presentation.widgets.state import PHASE_ERROR, as_number, pack_state, read_state
from fitness_bot.service.models.commands.body import RecordWeightCommand
from fitness_bot.service.models.commands.users import ExpectInputCommand, SetGoalCommand, UpdateProfileCommand
from fitness_bot.service.models.queries.users import GetProfileQuery, GetProfileQueryResult
from fitness_bot.shared.paths import MEASUREMENT_GUIDES_DIR

_SITE_CODES = frozenset(code for code, _ in FIXED_MEASUREMENT_SITES)
_MULTI = frozenset({ProfileField.TRAINING_WEEKDAYS.value, ProfileField.SUPPLEMENTS.value})
_TEXT = frozenset(
    {
        ProfileField.EQUIPMENT.value,
        ProfileField.LIMITATIONS.value,
        ProfileField.DIET_PREFS.value,
        ProfileField.NUTRITION_CONSTRAINTS.value,
    },
)
_STEPS = {
    ProfileField.BIRTH_YEAR.value: 1,
    ProfileField.HEIGHT.value: 1,
    ProfileField.WEIGHT.value: 0.5,
    ProfileField.BODY_FAT.value: 0.5,
}
_DEFAULTS = {
    ProfileField.BIRTH_YEAR.value: 1995,
    ProfileField.HEIGHT.value: 170,
    ProfileField.WEIGHT.value: 70,
    ProfileField.BODY_FAT.value: 20,
}
_BOUNDS = {
    ProfileField.BIRTH_YEAR.value: (1940, 2015),
    ProfileField.HEIGHT.value: (120, 230),
    ProfileField.WEIGHT.value: (30, 250),
    ProfileField.BODY_FAT.value: (3, 60),
}
_CAPTION = {
    "goal": "🎯 Выбери одну цель.",
    "sex": "👤 Укажи пол.",
    "birth_year": "🎂 Год рождения.",
    "height": "📐 Рост в см — одно число.",
    "weight": "⚖️ Вес в кг — одно число.",
    "experience": "📈 Выбери уровень опыта.",
    "days_per_week": "🔢 Сколько дней в неделю? Число от 1 до 7.",
    "training_weekdays": "📅 Отметь дни, затем «Готово».",
    "equipment": "🛠️ Какое оборудование доступно? Напиши в чат.",
    "training_place": "📍 Где обычно занимаешься?",
    "limitations": "⚠️ Травмы или ограничения? Напиши в чат или нажми «Нет ограничений».",
    "activity_level": "🚶 Какой уровень активности вне зала?",
    "session_minutes": "⏱ Сколько минут обычно длится тренировка?",
    "body_fat": "🧪 Укажи % жира или нажми «Не знаю».",
    "supplements": "💊 Что из спортпита принимаешь? Можно несколько, затем «Готово».",
    "diet_prefs": "🥗 Пищевые предпочтения? Напиши в чат или «Без предпочтений».",
    "nutrition_constraints": "🚫 Болезни, аллергии или противопоказания? Напиши в чат или «Нет ограничений».",
}


def measurement_guide_png(step: str, sex: Sex | None) -> str | None:
    """Sex folder from guide_sex_folder. Missing files stay None so tests need no PNGs."""
    if step not in _SITE_CODES:
        return None
    path = MEASUREMENT_GUIDES_DIR / guide_sex_folder(sex) / f"{step}.png"
    return str(path) if path.is_file() else None


class IntakeScreen:
    screen_id = WidgetScreenId.INTAKE

    def __init__(self, shell: WidgetShell) -> None:
        self.shell = shell

    async def open(self, ctx: ScreenContext) -> WidgetFrame:
        profile = await self._profile(ctx)
        previous = read_state(ctx.binding.frame.chat_data if ctx.binding.frame else None)
        return self._frame(self._payload(profile, previous))

    async def companion(self, ctx: ScreenContext, frame: WidgetFrame) -> ScreenResult | None:
        data = read_state(frame.chat_data)
        profile = await self._profile(ctx)
        png = measurement_guide_png(str(data.get("step") or ""), getattr(profile, "sex", None))
        if png is None:
            return None
        return ScreenResult(frame=frame, answer=frame.chat_data, photo_path=png)

    async def apply(self, ctx: ScreenContext, opcode: str) -> ScreenResult:
        parsed = parse_opcode(opcode)
        frame = ctx.binding.frame or await self.open(ctx)
        if isinstance(parsed, OpcodeRejection) or parsed.screen is not WidgetScreenId.INTAKE:
            return ScreenResult(frame=frame, answer=PHASE_ERROR)
        data = read_state(frame.chat_data)
        step = str(data.get("step") or "")
        if parsed.name == "pick":
            return await self._pick(ctx, data, step, parsed.arg or "")
        if parsed.name in {"inc", "dec"}:
            return self._nudge(data, step, 1 if parsed.name == "inc" else -1)
        if parsed.name == "preset":
            return await self._save(ctx, ProfileField.SESSION_MINUTES.value, int(parsed.arg or "0"), data)
        if parsed.name == "done":
            return await self._done(ctx, data, step)
        if parsed.name == "text":
            return self._text(ctx, data, step)
        return ScreenResult(frame=self._frame(data), answer=PHASE_ERROR)

    async def _pick(self, ctx: ScreenContext, data: dict[str, object], step: str, code: str) -> ScreenResult:
        if step in _MULTI:
            picked = [str(item) for item in data.get("picked") or []]
            if step == ProfileField.SUPPLEMENTS.value and code == "none":
                picked = [] if "none" in picked else ["none"]
            elif code in picked:
                picked = [item for item in picked if item != code]
            else:
                picked = [item for item in picked if item != "none"]
                picked.append(code)
            data["picked"] = picked
            return self._result(data)
        if step == ProfileField.BODY_FAT.value and code == "unknown":
            return await self._save(ctx, step, "unknown", data)
        if step in _TEXT and code == "none":
            return await self._save(ctx, step, "", data)
        return await self._save(ctx, step, code, data)

    def _nudge(self, data: dict[str, object], step: str, sign: int) -> ScreenResult:
        if step not in _STEPS:
            return ScreenResult(frame=self._frame(data), answer=PHASE_ERROR)
        delta = _STEPS[step] * sign
        current = float(data.get("value") if data.get("value") is not None else _DEFAULTS[step])
        low, high = _BOUNDS[step]
        value = min(high, max(low, round(current + delta, 2)))
        data["value"] = as_number(value)
        return self._result(data)

    async def _done(self, ctx: ScreenContext, data: dict[str, object], step: str) -> ScreenResult:
        if step in _MULTI:
            picked = [str(item) for item in data.get("picked") or []]
            if not picked:
                return ScreenResult(frame=self._frame(data), answer=PHASE_ERROR)
            if step == ProfileField.TRAINING_WEEKDAYS.value:
                return await self._save(ctx, step, [int(item) for item in picked], data)
            return await self._save(ctx, step, picked, data)
        if step in _STEPS:
            return await self._save(ctx, step, data.get("value"), data)
        return ScreenResult(frame=self._frame(data), answer=PHASE_ERROR)

    def _text(self, ctx: ScreenContext, data: dict[str, object], step: str) -> ScreenResult:
        if step not in _TEXT:
            return ScreenResult(frame=self._frame(data), answer=PHASE_ERROR)
        frame = self._frame(data)
        return ScreenResult(
            frame=frame,
            answer=frame.chat_data,
            expect=ExpectInputCommand(
                telegram_user_id=ctx.user_id,
                expected_input=ExpectedInput.PROFILE_FIELD,
                expected_field=step,
            ),
        )

    async def _save(self, ctx: ScreenContext, step: str, value: object, data: dict[str, object]) -> ScreenResult:
        try:
            if step == "goal":
                await ctx.mediator.send(SetGoalCommand(telegram_user_id=ctx.user_id, goal=Goal(str(value))))
            elif step == ProfileField.WEIGHT.value:
                await ctx.mediator.send(
                    RecordWeightCommand(
                        telegram_user_id=ctx.user_id,
                        kilograms=value if value is not None else 0,
                        source=WeightSource.ONBOARDING,
                    ),
                )
            elif step == ProfileField.DAYS_PER_WEEK.value:
                await ctx.mediator.send(
                    UpdateProfileCommand(
                        telegram_user_id=ctx.user_id,
                        field=ProfileField.DAYS_PER_WEEK,
                        value=int(str(value)),
                    ),
                )
            elif step == ProfileField.SESSION_MINUTES.value:
                await ctx.mediator.send(
                    UpdateProfileCommand(
                        telegram_user_id=ctx.user_id,
                        field=ProfileField.SESSION_MINUTES,
                        value=int(str(value)),
                    ),
                )
            else:
                await ctx.mediator.send(
                    UpdateProfileCommand(
                        telegram_user_id=ctx.user_id,
                        field=ProfileField(step),
                        value=value,  # type: ignore[arg-type]
                    ),
                )
        except (DomainError, ValueError):
            return ScreenResult(frame=self._frame(data), answer=PHASE_ERROR)
        return await self._advance(ctx)

    async def _advance(self, ctx: ScreenContext) -> ScreenResult:
        profile = await self._profile(ctx)
        data = self._payload(profile, {})
        frame = self._frame(data)
        if _complete(profile):
            return ScreenResult(frame=frame, answer=frame.chat_data, navigate=WidgetScreenId.HOME)
        return ScreenResult(frame=frame, answer=frame.chat_data)

    def _payload(self, profile: GetProfileQueryResult, previous: dict[str, object]) -> dict[str, object]:
        step = _step_name(profile)
        if step is None:
            return {"step": "goal", "value": None, "picked": [], "title": "🏠 Анкета готова"}
        title = _CAPTION.get(step, "Продолжим.")
        if step == ProfileField.TRAINING_WEEKDAYS.value and profile.days_per_week:
            title = f"📅 Отметь ровно {profile.days_per_week} дня(ей), затем «Готово»."
        value = _current_value(profile, step)
        picked: list[str] = []
        if previous.get("step") == step:
            picked = [str(item) for item in previous.get("picked") or []]
            if step in _STEPS and previous.get("value") is not None:
                value = previous.get("value")
        return {"step": step, "value": value, "picked": picked, "title": title}

    def _frame(self, data: dict[str, object]) -> WidgetFrame:
        title = str(data.get("title") or "Продолжим.")
        return WidgetFrame(
            screen=WidgetScreenId.INTAKE,
            chat_data=pack_state(data),
            caption=title,
            shell_id="intake",
        )

    def _result(self, data: dict[str, object]) -> ScreenResult:
        frame = self._frame(data)
        return ScreenResult(frame=frame, answer=frame.chat_data)

    async def _profile(self, ctx: ScreenContext) -> GetProfileQueryResult:
        return await ctx.mediator.send(GetProfileQuery(telegram_user_id=ctx.user_id))


def _complete(profile: GetProfileQueryResult) -> bool:
    return bool(profile.profile_complete)


def _step_name(profile: GetProfileQueryResult) -> str | None:
    if profile.profile_complete:
        return None
    if profile.next_field is None:
        return "goal" if profile.goal is None else None
    return profile.next_field.value


def _current_value(profile: GetProfileQueryResult, step: str) -> object:
    if step == ProfileField.BIRTH_YEAR.value:
        return profile.birth_year or _DEFAULTS[step]
    if step == ProfileField.HEIGHT.value:
        return as_number(profile.height_cm) or _DEFAULTS[step]
    if step == ProfileField.WEIGHT.value:
        return as_number(profile.weight_kg) or _DEFAULTS[step]
    if step == ProfileField.BODY_FAT.value:
        return as_number(profile.body_fat_pct) or _DEFAULTS[step]
    if step == ProfileField.SESSION_MINUTES.value:
        return profile.session_minutes
    return None
