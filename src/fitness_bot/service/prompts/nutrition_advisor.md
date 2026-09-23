Write the one-time nutrition note for this user. Do not invent a training program.

Profile snapshot:
{{ profile_json }}

Goal:
{{ goal }}

Weekly training plan (days with intensity and training_style):
{{ program_json }}

Recent completed sessions (history — intensity, style, volume cues):
{{ history_json }}

Latest weight, kg:
{{ weight_kg }}

Rules:
- Anchor kcal and macros to the stated goal:
  - fat_loss — deficit; muscle_gain — surplus; strength — fuel hard sessions, near maintenance or slight surplus;
  - maintenance — hold current body weight (kcal at TDEE);
  - recovery — easier fueling, avoid aggressive deficit, prioritize protein and sleep cues;
  - stay_fit — keep composition/performance without a strict cut or bulk (mild maintenance ± small swings);
  - healthy_lifestyle — sustainable balanced intake, not aggressive body-comp targets.
- Scale energy and carbs to the weekly plan: more for heavy / strength / hit / circuit volume; less for recovery / light weeks.
- Use recent session history when present (missed weeks, high actual volume, hard intensity) to nudge kcal/carbs up or down.
- Keep advice practical for this equipment and limitations from the profile.
- Profile fields Rules (null / unknown = do **not** invent; use heuristics from the rest of the profile instead):
  - `activity_level`: primary TDEE / kcal anchor together with training days and weekly intensity.
  - `body_fat_pct` / `body_fat_unknown` / `circumferences_cm`: adjust deficit/surplus sizing for fat_loss / muscle_gain when composition cues exist; if unknown — do not invent a body-fat %.
  - `supplements` / `supplements_other`: reflect protein / creatine / caffeine / vitamins already used in advice text; do not prescribe pharmaceuticals.
  - `diet_prefs`: `meal_regularity` and `reply` must respect dietary restrictions and preferences.
  - `pharma` (only if present in profile_json): never recommend or discuss drug protocols; if the user noted use, apply only cautious recovery / volume context; if absent — ignore.
- Never recommend anabolic steroids, SARMs, or other performance-enhancing drugs.

Return JSON with keys kcal, protein_g, fat_g, carb_g, calculation, meal_regularity, reply.
calculation, meal_regularity, and reply are Russian and each is at most 500 characters.
