Build a weekly program proposal.

Profile:
{{ profile_json }}

Goal:
{{ goal }}

Training weekdays:
{{ weekdays_json }}

Days per week:
{{ days_per_week }}

Program structure (fixed — use exactly this value in program.program_type):
{{ program_type }}

Russian name for this structure (use in reply only):
{{ program_type_label }}

Structure guide:
{{ program_type_hint }}

Training styles (assign per day in `days[].training_style` — classic | strength | circuit | hit):
{{ training_styles_guide }}

Exercise catalog, id, name, and muscles only:
{{ catalog_json }}

JSON Schema for WorkoutDocument (follow field types and nesting):
{{ schema_json }}

Return one JSON object with keys `program` and `reply`.

Rules:
- `program.program_type` must be `{{ program_type }}`. Do not set a program-level `training_style`.
- Day count in `program.days` must equal days per week.
- Every day must have ISO `weekday` (1=Mon … 7=Sun), `title`, `position`, `intensity`, `training_style`, `warmup`, `cooldown`, and `slots`. Weekdays must be unique and should match the training weekdays from the profile when provided.
- Split days according to the structure guide above (full_body, upper_lower, push_pull, antagonist, synergist, or bro-split).
- Set `training_style` per day to match sets, reps, rest, and RPE for that session:
  - classic: 3–4 sets, moderate rest (60–120 s), RPE ~7–8
  - strength: base lifts ~5×5 or 3–5 reps, rest 180–300 s, RPE ~8–9 on working sets
  - circuit: 2–4 rounds, rest 20–45 s between exercises, slightly higher reps or mixed
  - hit: 1–2 hard working sets per exercise, RPE 9–10, longer rest only where needed
- Use a sensible weekly mix of styles (not every day `hit`; default a day to `classic` when unsure).
- Heuristic (not strict): 2 days → often full_body; 4 days → upper_lower or push_pull; 5–6 days → split or push_pull.
- `intensity` for each day: `recovery` | `light` | `medium` | `heavy`. Prefer a sensible weekly mix (e.g. heavy / medium / light); default a day to `medium` when unsure. Map Russian: восстановительная→recovery, легкая→light, средняя→medium, тяжелая→heavy.
- Prefer variety within the week: do not reuse the same `exercise_id` across days when catalog alternatives exist. For full_body, vary accessories and machine/cable options day to day; only repeat a key compound when progression truly needs it.
- Every day must include `warmup` and `cooldown` as short Russian text (1–3 sentences). These are separate steps shown before and after working exercises — not exercise slots and not interactive buttons.
- Do **not** put warm-up or cool-down movements into `slots`; only use the `warmup` / `cooldown` text fields. Match warm-up to that day's main work (e.g. hips/knees before squats).
- Every `exercise_id` must be a full UUID copied exactly from the catalog. Prefer catalog ids. Never invent ids, never truncate them, never put exercise names in `exercise_id`. If you cannot match an exercise, set `exercise_id` to null and fill `custom_request` plus `muscle_group`.
- Each slot needs `position`, `sets`, `rest_seconds`, `rpe`, either `reps` or `duration_seconds`, and `weight_kg`.
- `weight_kg` is the planned working load in kilograms. Set a concrete starting weight for every loaded exercise (machines, free weights, cables, smith). Estimate from body weight, experience, equipment, and goal — conservative for beginners. Use `null` only for true bodyweight work or duration-based slots (plank, cardio intervals) where external load does not apply.
- Respect limitations and equipment from the profile. Current limitations are hard constraints: never prescribe movements, loads, or styles that conflict with them (e.g. no deadlift loading, no free weights, avoid straining / Valsalva, back hernia → avoid spinal compression and max-effort holds).
- Profile fields Rules (null / unknown = do **not** invent):
  - `session_minutes`: hard time budget for each training day — fit slot count, rest, and density to it (prefer `circuit` / fewer accessories when short).
  - `experience` (`beginner` | `intermediate` | `advanced`): beginner → fewer complex patterns, lower RPE/volume; advanced → more variety and intensity when appropriate.
  - `activity_level` (outside the gym): `high` → bias the week toward more `light` / `recovery` days; `sedentary` → volume may be slightly higher for the same goal if recovery allows.
  - `body_fat_pct` / `body_fat_unknown` / `circumferences_cm`: when goal is `fat_loss`, use known composition cues for emphasis only (not medicine). If missing or unknown — do not invent a body-fat %.
  - Ignore `supplements` / `diet_prefs` / `pharma` for programming (nutrition noise). Never recommend drugs or pharma protocols.
- `reply` follows the system rules. Name the structure with «{{ program_type_label }}» — never write enum codes like `push_pull` or `full_body` in reply.

Example shape (types must match the schema above):
{
  "program_type": "{{ program_type }}",
  "days": [
    {
      "weekday": 1,
      "title": "день 1",
      "position": 1,
      "intensity": "medium",
      "training_style": "classic",
      "warmup": "5–8 мин лёгкого кардио и динамическая мобилизация таза, коленей и грудного отдела.",
      "cooldown": "3–5 мин спокойной ходьбы и лёгкая растяжка рабочих мышц.",
      "slots": [
        {
          "position": 1,
          "exercise_id": "<uuid from catalog>",
          "sets": 3,
          "reps": 10,
          "duration_seconds": null,
          "weight_kg": 40,
          "rest_seconds": 90,
          "rpe": 7,
          "technique_note": ""
        }
      ]
    }
  ]
}
