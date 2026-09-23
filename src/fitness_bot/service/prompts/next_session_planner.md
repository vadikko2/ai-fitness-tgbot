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

Adjust weight and volume from the history. Keep exercise_id values from the catalog.
Every loaded slot must have a concrete `weight_kg` (kg). Progress or deload from recent actuals when available; if history has no load yet, set a conservative starting weight from body weight, experience, and equipment. Leave `weight_kg` null only for bodyweight or duration-based slots.
Preserve or set day `intensity` (`recovery` | `light` | `medium` | `heavy`); default `medium` if unsure.
Keep or refresh `warmup` and `cooldown` as short Russian text steps (not slots) at the start and end of the session.
Strictly respect profile limitations and equipment: do not prescribe contraindicated loads or movements for this session.

Profile fields Rules (null / unknown = do **not** invent):
- `session_minutes`: hard time budget for this session — fit slots/rest/density to it.
- `experience`: beginner → simpler patterns, lower RPE/volume; advanced → more intensity only when history supports it.
- `activity_level`: if `high`, prefer slightly easier density/recovery when fatigue cues exist; if missing — ignore.
- `body_fat_pct` / circumferences: use only when present; never invent body-fat %.
- Ignore supplements / diet_prefs / pharma for session programming; never recommend drugs.

Return JSON with keys document and reply.
