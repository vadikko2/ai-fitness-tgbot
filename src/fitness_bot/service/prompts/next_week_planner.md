Propose an updated weekly program template from the current program and recent history.

Current program:
{{ program_json }}

Recent completed sessions (documents + actuals):
{{ history_json }}

Profile:
{{ profile_json }}

Goal:
{{ goal }}

Week progress:
{{ week_progress_json }}

Catalog:
{{ catalog_json }}

JSON Schema for WorkoutDocument (follow field types and nesting):
{{ schema_json }}

Return one JSON object with keys `document` and `reply`.

Rules:
- Return a full weekly `document` (same shape as a PROGRAM proposal), not a single session day.
- Preserve the split structure and training weekdays from the current program unless history clearly requires a change.
- Update weights, volume, and intensity where progression (or deload) is justified by history and body weight; leave unchanged where already appropriate.
- Prefer variety: avoid repeating the same `exercise_id` across days when catalog alternatives exist; keep intentional compound repeats only when progression needs them.
- Every day must include `warmup` and `cooldown` as short Russian text steps (not slots). Keep existing text when still appropriate; otherwise refresh to match the day's work.
- Do not put warm-up/cool-down into `slots`.
- Every `exercise_id` must come from the catalog. Prefer catalog ids. If you cannot match an exercise, set `exercise_id` to null and fill `custom_request` plus `muscle_group`.
- Each day needs ISO `weekday` (1=Mon … 7=Sun), `title`, `position`, `intensity` (`recovery` | `light` | `medium` | `heavy`), `warmup`, `cooldown`, and `slots`.
- Each slot needs `position`, `sets`, `rest_seconds`, `rpe`, and either `reps` or `duration_seconds`.
- Strictly respect profile limitations and equipment when changing the week.
- Profile fields Rules (null / unknown = do **not** invent):
  - `session_minutes`: keep each day within the time budget (slot count, rest, density).
  - `experience`: beginner → conservative volume/complexity; advanced → more progression latitude when history supports it.
  - `activity_level`: high outside-gym load → favor more `light` / `recovery`; sedentary → slightly higher volume only if recovery looks fine.
  - `body_fat_pct` / circumferences: use only when present for fat_loss accents; never invent %.
  - Do not use supplements / diet_prefs / pharma to change the program; never recommend drugs.
- `reply` is a short Russian summary of what changed (diff-style: weights / volume / intensity).
