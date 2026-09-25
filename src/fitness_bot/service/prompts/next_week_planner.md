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
- CRITICAL — `exercise_id`: every non-null value must be a full UUID copied verbatim from the catalog. Invented, truncated, or name-as-id values reject the whole week. If unsure, set `exercise_id` to null and fill `custom_request` plus `muscle_group`.
- Every catalog row has `places` (`gym` | `home` | `outdoor`). Only pick exercises that match the user's `training_place`.
- Each day needs ISO `weekday` (1=Mon … 7=Sun), `title`, `position`, `intensity` (`recovery` | `light` | `medium` | `heavy`), `warmup`, `cooldown`, and `slots`.
- Each slot needs `position`, `sets`, `rest_seconds`, `rpe`, either `reps` or `duration_seconds`, and `weight_kg`.
- Keep or update `weight_kg` for every loaded exercise (machines, free weights, cables, kettlebell). Progress or deload from history when justified; if a loaded slot still has `null`, fill a conservative starting weight. Leave `null` only for bodyweight, stretching, or duration-based slots.
- Strictly respect profile limitations, training_place, and equipment when changing the week.
- `training_place` + `limitations` have **maximum priority** (home → `home` in places + listed gear only; outdoor → `outdoor` in places, no gym machines; gym/mixed accordingly).
- Profile fields Rules (null / unknown = do **not** invent):
  - `session_minutes`: keep each day within the time budget (slot count, rest, density).
  - `experience`: beginner → conservative volume/complexity; advanced → more progression latitude when history supports it.
  - `activity_level`: high outside-gym load → favor more `light` / `recovery`; sedentary → slightly higher volume only if recovery looks fine.
  - `body_fat_pct` / circumferences: use only when present for fat_loss accents; never invent %.
  - Do not use supplements / diet_prefs / nutrition_constraints / pharma to change the program; never recommend drugs.
- `reply` is a short Russian summary of what changed (diff-style: weights / volume / intensity).
