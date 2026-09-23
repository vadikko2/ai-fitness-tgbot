"""Resolve instructional photos for fixed body-girth measurement sites."""

from __future__ import annotations

from pathlib import Path

from fitness_bot.domain.body.measurement import FIXED_MEASUREMENT_SITES
from fitness_bot.domain.enums import Sex
from fitness_bot.shared.paths import MEASUREMENT_GUIDES_DIR

_FIXED_CODES = frozenset(code for code, _ in FIXED_MEASUREMENT_SITES)
_TELEGRAM_CAPTION_LIMIT = 1024

# Profile sex → asset folder. Unknown/None → male (onboarding usually sets sex
# before measurements; male matches the historical default figure set).
_DEFAULT_GUIDE_SEX = Sex.MALE


def guide_sex_folder(sex: Sex | None) -> str:
    """Return ``male`` / ``female`` directory name for guide assets."""
    if sex is Sex.FEMALE:
        return "female"
    return _DEFAULT_GUIDE_SEX.value


def measurement_guide_image_path(site_code: str, *, sex: Sex | None = None) -> Path | None:
    """Return PNG path for a fixed site code, or None if missing / custom."""
    if site_code not in _FIXED_CODES:
        return None
    folder = guide_sex_folder(sex)
    path = MEASUREMENT_GUIDES_DIR / folder / f"{site_code}.png"
    if path.is_file():
        return path
    # Backward-compat: flat legacy path (pre gender split).
    legacy = MEASUREMENT_GUIDES_DIR / f"{site_code}.png"
    return legacy if legacy.is_file() else None


def measurement_overview_image_path(*, sex: Sex | None = None) -> Path | None:
    """Return full-body overview PNG for the measurement site menu."""
    folder = guide_sex_folder(sex)
    path = MEASUREMENT_GUIDES_DIR / folder / "overview.png"
    if path.is_file():
        return path
    legacy = MEASUREMENT_GUIDES_DIR / "overview.png"
    return legacy if legacy.is_file() else None


def caption_fits_telegram(text: str) -> bool:
    return len(text) <= _TELEGRAM_CAPTION_LIMIT
