from __future__ import annotations

from fitness_bot.domain.body.measurement import (
    DEFAULT_MEASUREMENT_GUIDES,
    FIXED_MEASUREMENT_SITES,
    MeasurementEntry,
    MeasurementGuide,
    MeasurementSite,
    default_guide_for,
)
from fitness_bot.domain.body.nutrition import NutritionRecommendation
from fitness_bot.domain.body.progress_photo import (
    MAX_PROGRESS_PHOTO_BYTES,
    PROGRESS_PHOTO_ANGLE_ORDER,
    ProgressPhoto,
    ProgressPhotoSet,
    progress_photo_object_key,
)
from fitness_bot.domain.body.reminder import ProgressPhotoReminder, WeightReminder
from fitness_bot.domain.body.weight import WeightEntry

__all__ = [
    "DEFAULT_MEASUREMENT_GUIDES",
    "FIXED_MEASUREMENT_SITES",
    "MAX_PROGRESS_PHOTO_BYTES",
    "PROGRESS_PHOTO_ANGLE_ORDER",
    "MeasurementEntry",
    "MeasurementGuide",
    "MeasurementSite",
    "NutritionRecommendation",
    "ProgressPhoto",
    "ProgressPhotoReminder",
    "ProgressPhotoSet",
    "WeightEntry",
    "WeightReminder",
    "default_guide_for",
    "progress_photo_object_key",
]
