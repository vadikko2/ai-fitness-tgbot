from __future__ import annotations

from fitness_bot.domain.enums import Sex
from fitness_bot.presentation.progress_pose_images import (
    PROGRESS_POSE_ANGLES,
    caption_fits_telegram,
    guide_sex_folder,
    progress_pose_image_path,
    progress_pose_overview_image_path,
)
from fitness_bot.shared.paths import PROGRESS_POSES_DIR


def test_guide_sex_folder_defaults_unknown_to_male() -> None:
    assert guide_sex_folder(None) == "male"
    assert guide_sex_folder(Sex.MALE) == "male"
    assert guide_sex_folder(Sex.FEMALE) == "female"


def test_progress_pose_images_resolve_for_all_angles_both_sexes() -> None:
    assert PROGRESS_POSES_DIR.is_dir()
    for sex in (Sex.MALE, Sex.FEMALE, None):
        for angle in sorted(PROGRESS_POSE_ANGLES):
            path = progress_pose_image_path(angle, sex=sex)
            assert path is not None, f"missing pose image for {angle} sex={sex}"
            assert path.is_file()
            assert path.suffix == ".png"
            assert path.stat().st_size > 0
            assert guide_sex_folder(sex) in path.parts


def test_progress_pose_overview_images_resolve_both_sexes() -> None:
    for sex in (Sex.MALE, Sex.FEMALE, None):
        path = progress_pose_overview_image_path(sex=sex)
        assert path is not None, f"missing overview for sex={sex}"
        assert path.is_file()
        assert path.name == "overview.png"
        assert guide_sex_folder(sex) in path.parts


def test_progress_pose_image_missing_for_unknown_angle() -> None:
    assert progress_pose_image_path("diagonal", sex=Sex.MALE) is None
    assert progress_pose_image_path("", sex=Sex.FEMALE) is None


def test_guide_caption_fits_telegram_limit() -> None:
    assert caption_fits_telegram("short")
    assert not caption_fits_telegram("x" * 1025)
