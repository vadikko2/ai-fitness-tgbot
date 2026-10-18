from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class VideoSearchHit:
    platform: str
    url: str
    title: str


class YouTubeSearch(Protocol):
    async def search(self, query: str, *, limit: int = 5) -> Sequence[VideoSearchHit]:
        """Return YouTube results from the Data API only (no invented URLs)."""


class RutubeSearch(Protocol):
    async def search(self, query: str, *, limit: int = 5) -> Sequence[VideoSearchHit]:
        """Return Rutube results from the public search API only."""


@dataclass(frozen=True, slots=True)
class CatalogExerciseRecord:
    id: UUID
    name: str
    primary_muscles: tuple[str, ...]
    secondary_muscles: tuple[str, ...]
    places: tuple[str, ...] = ("gym",)


@dataclass(frozen=True, slots=True)
class CatalogVideoLink:
    platform: str
    url: str
    title: str


@dataclass(frozen=True, slots=True)
class CatalogExerciseGuide:
    id: UUID
    name: str
    technique: str
    videos: tuple[CatalogVideoLink, ...]
    primary_muscles: tuple[str, ...] = ()
    secondary_muscles: tuple[str, ...] = ()


class ExerciseCatalogReader(Protocol):
    async def list_exercises(self) -> Sequence[CatalogExerciseRecord]:
        """All catalog exercises available for matching."""

    async def get_guide(self, exercise_id: UUID) -> CatalogExerciseGuide | None:
        """Technique text and demo video links for one catalog exercise."""
