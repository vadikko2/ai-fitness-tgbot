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

Exercise catalog, id, name, muscles, and places only:
{{ catalog_json }}

{% include "_wellbeing_block.md" %}

JSON Schema for WorkoutDocument (follow field types and nesting):
{{ schema_json }}

Return one JSON object with keys `program` and `reply`.

Rules:
- `program.program_type` must be `{{ program_type }}`. Do not set a program-level `training_style`.
- Day count in `program.days` must equal days per week.
- Every day must have ISO `weekday` (1=Mon … 7=Sun), `title`, `position`, `intensity`, `training_style`, `warmup`, `cooldown`, and `slots`. Weekdays must be unique and should match the training weekdays from the profile when provided.
- `title` is one short Russian phrase of what that session works (for example «Ноги и махи»). Do not repeat the program type, do not list tags, and do not use a colon.
- Split days according to the structure guide above (muscle splits, kettlebell, cardio, bodyweight_recovery, or stretching).
- **CRITICAL — choose exercises by place:** every catalog row has `places` (`gym` | `home` | `outdoor`, can be several). The catalog already filtered to the user's `training_place` when possible — still only pick rows whose `places` fit where the session will be done. Never prescribe a gym-machine / cable / smith exercise for `home` or `outdoor`. Prefer multi-place options for `mixed`.
- For `kettlebell`: predominantly kettlebell patterns; for `cardio`: pulse work / intervals / jump rope / runs; for `bodyweight_recovery`: light bodyweight activation only; for `stretching`: prefer catalog names starting with «Растяжка:» / «Мобилити:» (duration_seconds OK; recovery/light intensity).
- Set `training_style` per day to match sets, reps, rest, and RPE for that session:
  - classic: 3–4 sets, moderate rest (60–120 s), RPE ~7–8
  - strength: base lifts ~5×5 or 3–5 reps, rest 180–300 s, RPE ~8–9 on working sets
  - circuit: 2–4 rounds, rest 20–45 s between exercises, slightly higher reps or mixed
  - hit: 1–2 hard working sets per exercise, RPE 9–10, longer rest only where needed
- Use a sensible weekly mix of styles (not every day `hit`; default a day to `classic` when unsure).
- Heuristic (not strict): 2 days → often full_body; 4 days → upper_lower or push_pull; 5–6 days → split or push_pull; kettlebell/cardio/recovery/stretching follow their structure guide instead.
- `intensity` for each day: `recovery` | `light` | `medium` | `heavy`. Prefer a sensible weekly mix (e.g. heavy / medium / light); default a day to `medium` when unsure. Map Russian: восстановительная→recovery, легкая→light, средняя→medium, тяжелая→heavy. For bodyweight_recovery / stretching prefer `recovery` / `light`.
- Prefer variety within the week: do not reuse the same `exercise_id` across days when catalog alternatives exist. For full_body, vary accessories and machine/cable options day to day; only repeat a key compound when progression truly needs it.
- Every day must include `warmup` and `cooldown` as short Russian text (1–3 sentences). These are separate steps shown before and after working exercises — not exercise slots and not interactive buttons.
- Do **not** put warm-up or cool-down movements into `slots`; only use the `warmup` / `cooldown` text fields. Match warm-up to that day's main work (e.g. hips/knees before squats).
- CRITICAL — `exercise_id` (hard failure if wrong):
  - Every non-null `exercise_id` MUST be a full UUID copied **verbatim** from `catalog_json` above (same characters, same hyphens, no shortening).
  - NEVER invent a UUID. NEVER truncate. NEVER rearrange digits. NEVER put a Russian/English exercise name in `exercise_id`.
  - If you are not 100% sure the id is in `catalog_json`, set `exercise_id` to null and fill `custom_request` (real exercise name in Russian) plus `muscle_group`.
  - A single bad `exercise_id` rejects the whole week: the bot shows a parse error and the user gets no plan. Accuracy here beats creativity.
- Each slot needs `position`, `sets`, `rest_seconds`, `rpe`, either `reps` or `duration_seconds`, and `weight_kg`.
- `weight_kg` is the planned working load in kilograms. Set a concrete starting weight for every loaded exercise (machines, free weights, cables, smith, kettlebell). Estimate from body weight, experience, equipment, and goal — conservative for beginners. Use `null` only for true bodyweight work, stretching, or duration-based slots (plank, cardio intervals) where external load does not apply.
- Respect limitations and equipment from the profile. Current limitations are hard constraints: never prescribe movements, loads, or styles that conflict with them (e.g. no deadlift loading, no free weights, avoid straining / Valsalva, back hernia → avoid spinal compression and max-effort holds).
- When limitations mention illness, injury, rehab, pregnancy, older age, or kids — prefer catalog names starting with «ЛФК:», «Беременность:», «Для пожилых:», «Для детей:» (and other light bodyweight / mobility). Never prescribe high-impact, heavy axial loading, Valsalva, or contact/plyometrics for those profiles. This is gentle programming support, not medical advice — stay conservative.
- `training_place` and `limitations` have **maximum priority** over variety and progression:
  - `home` → only exercises with `home` in `places` and equipment the user listed; never prescribe gym machines, cable stacks, smith, or other facility-only gear.
  - `outdoor` → only exercises with `outdoor` in `places`; bodyweight / portable gear only; no gym machines or indoor-only equipment.
  - `gym` → exercises with `gym` in `places`; full gym equipment is fine when it matches `equipment` / common gym access.
  - `mixed` → prefer options tagged for more than one place; never require unavailable gear.
- Profile fields Rules (null / unknown = do **not** invent):
  - `session_minutes`: hard time budget for each training day — fit slot count, rest, and density to it (prefer `circuit` / fewer accessories when short).
  - `experience` (`beginner` | `intermediate` | `advanced`): beginner → fewer complex patterns, lower RPE/volume; advanced → more variety and intensity when appropriate.
  - `activity_level` (outside the gym): `high` → bias the week toward more `light` / `recovery` days; `sedentary` → volume may be slightly higher for the same goal if recovery allows.
  - `body_fat_pct` / `body_fat_unknown` / `circumferences_cm`: when goal is `fat_loss`, use known composition cues for emphasis only (not medicine). If missing or unknown — do not invent a body-fat %.
  - Ignore `supplements` / `diet_prefs` / `nutrition_constraints` / `pharma` for programming (nutrition noise). Never recommend drugs or pharma protocols.
- `reply` follows the system rules. Name the structure with «{{ program_type_label }}» — never write enum codes like `push_pull` or `full_body` in reply.

{% if validation_hint %}
Correction required:
{{ validation_hint }}
{% endif %}

Example shape (types must match the schema above):
{
  "program_type": "{{ program_type }}",
  "days": [
    {
      "weekday": 1,
      "title": "Ноги и махи",
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
