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
    "для",
    "и",
    "из",
    "к",
    "на",
    "по",
    "с",
    "со",
    "техника",
    "упражнение",
    "упражнения",
}


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
    """Keep hits whose titles overlap the exercise name; fall back to all hits if none match."""
    name_tokens = distinctive_name_tokens(exercise_name)
    if not name_tokens:
        return hits
    need = 1 if len(name_tokens) <= 2 else max(2, (len(name_tokens) + 1) // 2)
    relevant: list[VideoSearchHit] = []
    for hit in hits:
        title_tokens = tokenize(hit.title)
        if len(name_tokens & title_tokens) >= need:
            relevant.append(hit)
    return relevant if relevant else hits


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
