from __future__ import annotations

import json
import re
from typing import Any

from fitness_bot.domain.catalog.normalize import tokenize
from fitness_bot.service.catalog.jsonl import ExerciseVideoLine
from fitness_bot.service.ports.video_search import VideoSearchHit

_JSON_ARRAY_RE = re.compile(r"\[[\s\S]*\]")
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")
_VIDEO_STOPWORDS = {
    "a",
    "and",
    "for",
    "of",
    "the",
    "to",
    "with",
    "в",
    "видео",
    "выполнения",
    "гантелей",
    "гантели",
    "гантель",
    "гантелями",
    "гантелью",
    "для",
    "двумя",
    "и",
    "из",
    "к",
    "лежа",
    "лёжа",
    "на",
    "нюансы",
    "одной",
    "по",
    "рукой",
    "руками",
    "с",
    "сидя",
    "со",
    "советы",
    "стоя",
    "техника",
    "упражнение",
    "упражнения",
    "штанга",
    "штанги",
    "штангой",
}


def _fold(text: str) -> str:
    return text.casefold().replace("ё", "е")


def video_title_conflicts(exercise_name: str, video_title: str) -> bool:
    """True when a video title clearly belongs to a different exercise family."""
    name = _fold(exercise_name)
    title = _fold(video_title)
    if not title.strip():
        return False

    if "бытовые навыки" in title or "надевание носков" in title:
        return True
    if "жира на груди" in title or "поднимите грудь" in title:
        return True

    if "французск" in title and "французск" not in name:
        overhead_extension = "разгибание" in name and ("голов" in name or "рук" in name)
        if not overhead_extension:
            return True

    if "французск" in name and "французск" not in title:
        chest_like = (
            "наклонн" in title
            or "верх груди" in title
            or "жим в смите" in title
            or "жим штанги лежа" in title
            or "жим гантелей на наклон" in title
            or "жим гантелями на наклон" in title
        )
        if chest_like:
            return True

    if ("жим ногами" in title or "жим одной ногой" in title) and "ног" not in name and "платформ" not in name:
        return True

    if "становая" in title and not any(token in name for token in ("становая", "румынск", "мертвая", "deadlift")):
        return True

    if "румынск" in title and "румынск" not in name and "мертвая" not in name:
        return True

    if "присед" in title and "без присед" not in title:
        squat_ok = any(token in name for token in ("присед", "сплит", "гакк", "выпад", "squat"))
        # Step-downs often surface as one-leg box squats.
        box_step = "тумб" in name and "тумб" in title
        if not squat_ok and not box_step:
            return True

    if "выпад" in title and not any(token in name for token in ("выпад", "сплит", "lunge")):
        return True

    if "подтягиван" in title and "ног" not in title:
        if not any(token in name for token in ("подтягиван", "турник", "перекладин", "hang")):
            return True

    if "отжиман" in title and not any(token in name for token in ("отжиман", "бёрпи", "берпи", "burpee", "push")):
        return True

    title_tokens = tokenize(video_title)
    if any(token in name for token in ("мобилити", "растяжка", "скорпион")) and "жим" in title_tokens:
        return True

    if "доставание носков" in name and any(
        token in title for token in ("мостик", "подъем таза", "французск", "надевание")
    ):
        return True

    return False


def extract_json_value(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_OBJECT_RE.search(text) or _JSON_ARRAY_RE.search(text)
        if not match:
            raise ValueError("model response is not JSON")
        return json.loads(match.group(0))


def extract_json_array(text: str) -> list[Any]:
    payload = extract_json_value(text)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "exercises", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    raise ValueError("model response must be a JSON array")


def distinctive_name_tokens(exercise_name: str) -> set[str]:
    return {token for token in tokenize(exercise_name) if len(token) > 2 and token not in _VIDEO_STOPWORDS}


def filter_relevant_video_hits(
    hits: list[VideoSearchHit],
    *,
    exercise_name: str,
) -> list[VideoSearchHit]:
    """Keep hits whose titles overlap the exercise name and do not conflict by family."""
    name_tokens = distinctive_name_tokens(exercise_name)
    relevant: list[VideoSearchHit] = []
    for hit in hits:
        if video_title_conflicts(exercise_name, hit.title):
            continue
        if not name_tokens:
            relevant.append(hit)
            continue
        title_tokens = tokenize(hit.title)
        need = 1 if len(name_tokens) <= 2 else max(2, (len(name_tokens) + 1) // 2)
        if len(name_tokens & title_tokens) >= need:
            relevant.append(hit)
    return relevant


def dedupe_videos(hits: list[VideoSearchHit], *, limit_per_platform: int) -> list[ExerciseVideoLine]:
    seen: set[tuple[str, str]] = set()
    by_platform: dict[str, list[ExerciseVideoLine]] = {"youtube": [], "rutube": []}
    for hit in hits:
        if hit.platform not in ("youtube", "rutube"):
            continue
        key = (hit.platform, hit.url)
        if key in seen or not hit.url:
            continue
        seen.add(key)
        bucket = by_platform[hit.platform]
        if len(bucket) >= limit_per_platform:
            continue
        bucket.append(ExerciseVideoLine(platform=hit.platform, url=hit.url, title=hit.title or ""))
    return by_platform["youtube"] + by_platform["rutube"]
