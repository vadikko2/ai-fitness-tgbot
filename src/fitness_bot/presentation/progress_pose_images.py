"""Resolve instructional PNGs for progress-photo pose angles."""

from __future__ import annotations

from pathlib import Path

from fitness_bot.domain.enums import Sex
from fitness_bot.shared.paths import PROGRESS_POSES_DIR

PROGRESS_POSE_ANGLES = frozenset({"front", "side", "back"})
_TELEGRAM_CAPTION_LIMIT = 1024

# Profile sex → asset folder. Unknown/None → male (same default as measurement guides).
_DEFAULT_GUIDE_SEX = Sex.MALE


def guide_sex_folder(sex: Sex | None) -> str:
    """Return ``male`` / ``female`` directory name for pose assets."""
    if sex is Sex.FEMALE:
        return "female"
    return _DEFAULT_GUIDE_SEX.value


def progress_pose_image_path(angle: str, *, sex: Sex | None = None) -> Path | None:
    """Return PNG path for a pose angle, or None if unknown / missing."""
    if angle not in PROGRESS_POSE_ANGLES:
        return None
    folder = guide_sex_folder(sex)
    path = PROGRESS_POSES_DIR / folder / f"{angle}.png"
    return path if path.is_file() else None


def progress_pose_overview_image_path(*, sex: Sex | None = None) -> Path | None:
    """Return overview PNG showing all three progress-photo angles."""
    folder = guide_sex_folder(sex)
    path = PROGRESS_POSES_DIR / folder / "overview.png"
    return path if path.is_file() else None


def caption_fits_telegram(text: str) -> bool:
    return len(text) <= _TELEGRAM_CAPTION_LIMIT
