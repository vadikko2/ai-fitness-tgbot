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

What to produce
- `kcal`, `protein_g`, `fat_g`, `carb_g` — daily targets as numbers.
- `calculation` — plain Russian: how you got the numbers from this profile, goal, and training load (not a formula dump).
- `meal_regularity` — plain Russian: meal rhythm for training days vs rest/light days; how to place food around sessions.
- `sports_nutrition` — plain Russian: a dedicated sports-supplements paragraph (see rules below). Never leave empty.
- `reply` — the main friendly note in Russian: readable, concrete, tied to this person.

Ground every number and tip in the data above
- Name the goal in ordinary Russian (not the enum code) and say how it shapes surplus / deficit / maintenance.
- Use current profile cues: sex, age, height, weight, activity_level, session_minutes, experience, body composition when known, diet_prefs, equipment/limitations only when they affect eating practicality.
- Use the weekly plan: day count, intensity mix, training_style (classic / strength / circuit / hit). Heavier or more glycolytic weeks → more energy and carbs; recovery / light weeks → pull back.
- Use recent session history when present (missed weeks, high logged volume, hard intensity) to nudge kcal/carbs up or down and to explain why.
- Do not invent missing profile fields (null / unknown). Prefer heuristics from what is known.

Training × food
- Explain how to fuel around workouts from this plan: what matters before and after harder sessions vs easy or rest days.
- Keep it practical (timing windows in plain language, not lab protocols). Match carbs/protein emphasis to intensity and style on those days.

Sports supplements (`sports_nutrition` only — not inside `reply` / `meal_regularity`)
- Always write a separate paragraph for sports nutrition / OTC supplements.
- If `supplements` / `supplements_other` list anything the user already uses: focus on how to take what they already take — timing with meals and training, food context for uptake/tolerance/effect. Do not push new products unless one clear gap remains.
- If those lists are empty / none: suggest what can help for this goal and training (usually 1–3 common options, e.g. protein powder, creatine, caffeine, omega-3, vitamin D when relevant), and how to take each — when relative to food and sessions, in plain language. Keep it optional and calm.
- Use established sports-nutrition practice. Do not invent exotic stacks, dosages as medical advice, or “must buy” pressure.
- Never recommend pharmaceuticals, anabolic steroids, SARMs, or other PEDs. If `pharma` is present in profile_json: never discuss drug protocols; use only cautious recovery / volume context. If absent — ignore.

Tone and shape
- Write like a kind friend who knows training: warm, supportive, conversational Russian with «ты», soft addresses («смотри», «тебе сейчас важно», «давай так»), and concrete tips — not a dry report or lecture.
- Prefer short paragraphs that feel like a spoken story: why these numbers fit them, then how to live with them day to day.
- No emoji, no markdown headings, no long bullet lists inside the prose fields (a blank line is enough structure).
- Explicitly connect goal + training process + profile so the user sees why these numbers and habits fit them.
- Respect `diet_prefs` in `meal_regularity` and `reply`.
- Keep sports-supplement detail only in `sports_nutrition`; in `reply` you may mention food first, not stacks.

Fixed reply structure the user will see (keep each field to its role)
1. `reply` — personal friendly advice (story tone).
2. macros — numbers only (kcal / protein / fat / carbs).
3. `calculation` — how the numbers were chosen.
4. `meal_regularity` — meal rhythm around training vs rest.
5. `sports_nutrition` — supplements: how to take current ones, or what/how if none yet.

Limits (override the global 500-character default for this action only)
- `reply` — Russian, at most 1200 characters.
- `calculation`, `meal_regularity`, and `sports_nutrition` — Russian, each at most 800 characters.
- Use fewer characters when fewer are enough.

Return JSON with keys kcal, protein_g, fat_g, carb_g, calculation, meal_regularity, sports_nutrition, reply.
