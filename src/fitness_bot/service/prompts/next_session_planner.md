Propose the next session as a draft in the same document shape.

Day template:
{{ template_json }}

Recent completed sessions:
{{ history_json }}

Profile:
{{ profile_json }}

Goal:
{{ goal }}

Catalog:
{{ catalog_json }}

Adjust weight and volume from the history.
CRITICAL — `exercise_id`: keep or copy full UUIDs verbatim from the catalog. Invented, truncated, or name-as-id values break the session draft. If unsure, set `exercise_id` to null and fill `custom_request` plus `muscle_group`.
Every loaded slot must have a concrete `weight_kg` (kg). Progress or deload from recent actuals when available; if history has no load yet, set a conservative starting weight from body weight, experience, and equipment. Leave `weight_kg` null only for bodyweight or duration-based slots.
Preserve or set day `intensity` (`recovery` | `light` | `medium` | `heavy`); default `medium` if unsure.
Keep or refresh `warmup` and `cooldown` as short Russian text steps (not slots) at the start and end of the session.
Strictly respect profile limitations, training_place, and equipment: do not prescribe contraindicated loads or movements for this session.
`training_place` + `limitations` have **maximum priority**:
- `home` → only listed home equipment; no gym machines / cables / smith.
- `outdoor` → no gym; bodyweight / portable only.
- `gym` / `mixed` → match available place and gear accordingly.

{% if wellbeing_json %}
Recent wellbeing notes (hard constraints for TODAY — adapt or replace exercises; never ignore for “staying on template”):
{{ wellbeing_json }}
If a note mentions joint pain, illness, poor sleep, or fatigue: reduce load/volume, swap the offending pattern, or deload that area. Prefer safer alternatives from the catalog.
{% endif %}

Profile fields Rules (null / unknown = do **not** invent):
- `session_minutes`: hard time budget for this session — fit slots/rest/density to it.
- `experience`: beginner → simpler patterns, lower RPE/volume; advanced → more intensity only when history supports it.
- `activity_level`: if `high`, prefer slightly easier density/recovery when fatigue cues exist; if missing — ignore.
- `body_fat_pct` / circumferences: use only when present; never invent body-fat %.
- Ignore supplements / diet_prefs / nutrition_constraints / pharma for session programming; never recommend drugs.

Return JSON with keys document and reply.
