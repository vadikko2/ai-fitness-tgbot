Edit the current document using the user's latest message. Return the **full** `document`, not a diff.

Current document:
{{ document_json }}

User message:
{{ utterance }}

User limitations (hard constraints — never violate):
{{ limitations }}

{% if training_place %}
Training place (hard constraint — never violate):
{{ training_place }}
- home → only exercises with `home` in catalog `places` and listed equipment; no gym machines.
- outdoor → only exercises with `outdoor` in `places`; no gym equipment.
- gym / mixed → match place and available gear; prefer multi-place tags for mixed.
{% endif %}

Catalog ids allowed (each row has `places`):
{{ catalog_json }}

JSON Schema for WorkoutDocument (follow field types and nesting):
{{ schema_json }}

Rules:
{% if focus_day_position %}
- Scope: edit ONLY this single training day (position {{ focus_day_position }}). The document above already contains that one day.
- Return a document with **exactly one** day. Keep the same `position` and `weekday` unless the user explicitly asked to change the weekday.
- Do not invent, remove, or rewrite other weekdays — they are not in scope.
{% else %}
- Always return the complete week document after applying the edit.
- If the user changes how many days they train, update `days` accordingly (count may change).
- Prefer exercise variety across the week: avoid repeating the same `exercise_id` on different days when a good alternative exists. Intentional repeats of a key compound lift are OK only when the split structure truly needs them; accessories and machine alternatives should differ day to day.
{% endif %}
- If the user names weekdays (пн/вт/… or Mon/Tue/…), set ISO `weekday` on each day: пн=1 … вс=7.
- Every day must have `weekday` (1–7), `title`, `position`, `intensity`, `warmup`, `cooldown`, and `slots`. Weekdays must be unique.
- `intensity` is the effort level for that day: `recovery` | `light` | `medium` | `heavy`. Default to `medium` when the user does not specify. Map Russian: восстановительная→recovery, легкая→light, средняя→medium, тяжелая→heavy.
- If the user asks to change intensity for a day (or the whole week), update that day's `intensity` and keep other fields unless they also asked to change them.
- If `days` is empty and the user asks to build a program, create a full week with the requested schedule.
- Every day must include `warmup` and `cooldown` as short Russian text (1–3 sentences each). These are separate session steps: warmup first, then working `slots`, then cooldown last.
- Do **not** put warm-up or cool-down movements into `slots` and do not invent per-movement buttons for them — only fill the `warmup` / `cooldown` text fields.
- Keep or improve existing warmup/cooldown text when editing unless the user asked to change them; if missing, invent sensible ones for that day's work.
- CRITICAL — `exercise_id`: copy the full UUID verbatim from the catalog. One wrong character, a truncated id, an invented id, or an exercise name in `exercise_id` breaks the edit for the user. If the exercise is not in the catalog, set `exercise_id` to null, `custom_request` to their words, and `muscle_group` to the muscle they named.
- If the message is off topic, return the document unchanged.
- Each slot needs `position`, `sets`, `rest_seconds`, `rpe`, either `reps` or `duration_seconds`, and `weight_kg`.
- Preserve existing `weight_kg` unless the user asks to change load. When adding a new loaded exercise, set a concrete starting `weight_kg`; use `null` only for bodyweight or duration-based slots.
- Strictly respect user limitations: never add contraindicated movements, loads, or styles (e.g. no deadlift loading / free weights / Valsalva when limited). Prefer «ЛФК:» / «Беременность:» / «Для пожилых:» / «Для детей:» when limitations imply rehab, pregnancy, older age, or kids.
- Honor `training_place` the same way: only pick catalog rows whose `places` fit the place; home/outdoor must not introduce gym-only machines.
- If profile context is present in the utterance or known limitations text: honor `session_minutes` as a soft time budget for density; honor experience level (beginner = simpler / lower RPE). Do not invent missing profile fields. Never recommend pharma / drugs.

Return JSON with keys `document` and `reply`.
