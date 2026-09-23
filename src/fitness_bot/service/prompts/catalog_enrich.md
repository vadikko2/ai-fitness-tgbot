Rewrite technique text and video search queries for existing catalog exercises.
This is not a chat reply. Return one JSON object only.

Exercises to enrich (JSON array):
{{ exercises_json }}

Return JSON object:
{"items":[{"name":"...","technique":"...","video_queries":["...","..."]}]}

Rules:
- Keep each item name exactly as given. Do not rename, merge, or drop exercises.
- technique is Russian coach prose for this exercise only.
- technique must cover: setup/grip/stance, movement path, breathing or bracing cue, 1–2 key nuances, and one common mistake to avoid.
- technique at most 500 characters. Prefer 350–500 when the exercise needs nuance; never pad with fluff.
- No headings, no bullet lists, no emoji, no URLs, no video ids.
- video_queries: 2 short Russian or mixed search phrases that find technique demos for this exact exercise (equipment and variation matter).
- primary_muscles / secondary_muscles stay unchanged; do not return them.
