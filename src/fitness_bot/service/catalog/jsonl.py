from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from fitness_bot.domain.catalog.normalize import normalize_exercise_name
from fitness_bot.domain.catalog.places import normalize_exercise_places
from fitness_bot.domain.enums import ExercisePlace

Platform = Literal["youtube", "rutube"]
Place = Literal["gym", "home", "outdoor"]


@dataclass(slots=True)
class ExerciseVideoLine:
    platform: Platform
    url: str
    title: str

    def to_dict(self) -> dict[str, str]:
        return {"platform": self.platform, "url": self.url, "title": self.title}


@dataclass(slots=True)
class ExerciseJsonlRecord:
    name: str
    primary_muscles: list[str]
    secondary_muscles: list[str]
    technique: str
    places: list[str] = field(default_factory=lambda: [ExercisePlace.GYM.value])
    videos: list[ExerciseVideoLine] = field(default_factory=list)

    @property
    def name_normalized(self) -> str:
        return normalize_exercise_name(self.name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "primary_muscles": list(self.primary_muscles),
            "secondary_muscles": list(self.secondary_muscles),
            "technique": self.technique,
            "places": list(self.places),
            "videos": [video.to_dict() for video in self.videos],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ExerciseJsonlRecord:
        videos: list[ExerciseVideoLine] = []
        for item in raw.get("videos") or []:
            platform = item["platform"]
            if platform not in ("youtube", "rutube"):
                raise ValueError(f"unsupported video platform: {platform!r}")
            videos.append(
                ExerciseVideoLine(
                    platform=platform,
                    url=str(item["url"]),
                    title=str(item.get("title") or ""),
                ),
            )
        places = list(normalize_exercise_places(raw.get("places")))
        return cls(
            name=str(raw["name"]),
            primary_muscles=[str(m) for m in raw.get("primary_muscles") or []],
            secondary_muscles=[str(m) for m in raw.get("secondary_muscles") or []],
            technique=str(raw.get("technique") or ""),
            places=places,
            videos=videos,
        )


def read_muscle_groups(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"muscle groups file not found: {path}")
    groups: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            groups.append(text)
    return groups


def load_exercises_jsonl(path: Path) -> dict[str, ExerciseJsonlRecord]:
    if not path.is_file():
        return {}
    by_name: dict[str, ExerciseJsonlRecord] = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{line_no}") from exc
        if not isinstance(raw, dict):
            raise ValueError(f"JSONL object expected at {path}:{line_no}")
        record = ExerciseJsonlRecord.from_dict(raw)
        by_name[record.name_normalized] = record
    return by_name


def write_exercises_jsonl(path: Path, records: Iterable[ExerciseJsonlRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda item: item.name_normalized)
    lines = [json.dumps(record.to_dict(), ensure_ascii=False, separators=(",", ":")) for record in ordered]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def upsert_exercise(store: dict[str, ExerciseJsonlRecord], record: ExerciseJsonlRecord) -> None:
    store[record.name_normalized] = record
