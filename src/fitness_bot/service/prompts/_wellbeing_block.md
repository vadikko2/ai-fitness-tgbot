{% if wellbeing_json is defined and wellbeing_json %}
{% if wellbeing_mode is defined and wellbeing_mode == "hard" %}
Recent wellbeing notes (HARD constraints — the user explicitly asked to adapt to them; never ignore them for “staying on template”):
{{ wellbeing_json }}
- Adapt every affected day: reduce load/volume, swap the offending movement pattern, or deload that area. Prefer safer alternatives from the catalog.
- Leave unaffected exercises as they are. In `reply`, briefly say in Russian what you changed because of the notes.
{% else %}
Recent wellbeing notes from the last days (soft context — take into account, do not overreact):
{{ wellbeing_json }}
- Pain, injury, or illness → avoid loading that area or movement and pick a safer alternative from the catalog.
- Mild fatigue or poor sleep → slightly trim volume or intensity; keep the plan structure.
- Positive or neutral notes → no changes needed because of them. Mention in `reply` only if a note changed something.
{% endif %}
- Notes are not medical advice: on sharp or persistent pain, suggest in `reply` to see a doctor.
{% endif %}
