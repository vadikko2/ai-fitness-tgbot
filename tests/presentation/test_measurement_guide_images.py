from __future__ import annotations

from fitness_bot.domain.body.measurement import FIXED_MEASUREMENT_SITES
from fitness_bot.domain.enums import Sex
from fitness_bot.presentation.measurement_guide_images import (
    caption_fits_telegram,
    guide_sex_folder,
    measurement_guide_image_path,
    measurement_overview_image_path,
)
from fitness_bot.shared.paths import MEASUREMENT_GUIDES_DIR


def test_guide_sex_folder_defaults_unknown_to_male() -> None:
    assert guide_sex_folder(None) == "male"
    assert guide_sex_folder(Sex.MALE) == "male"
    assert guide_sex_folder(Sex.FEMALE) == "female"


def test_measurement_guide_images_resolve_for_all_fixed_sites_both_sexes() -> None:
    assert MEASUREMENT_GUIDES_DIR.is_dir()
    for sex in (Sex.MALE, Sex.FEMALE, None):
        for code, _ in FIXED_MEASUREMENT_SITES:
            path = measurement_guide_image_path(code, sex=sex)
            assert path is not None, f"missing guide image for {code} sex={sex}"
            assert path.is_file()
            assert path.suffix == ".png"
            assert path.stat().st_size > 0
            assert guide_sex_folder(sex) in path.parts


def test_measurement_overview_images_resolve_both_sexes() -> None:
    for sex in (Sex.MALE, Sex.FEMALE, None):
        path = measurement_overview_image_path(sex=sex)
        assert path is not None, f"missing overview for sex={sex}"
        assert path.is_file()
        assert path.name == "overview.png"
        assert guide_sex_folder(sex) in path.parts


def test_measurement_guide_image_missing_for_custom_or_unknown() -> None:
    assert measurement_guide_image_path("custom:forearm", sex=Sex.MALE) is None
    assert measurement_guide_image_path("not_a_site", sex=Sex.FEMALE) is None


def test_guide_caption_fits_telegram_limit() -> None:
    assert caption_fits_telegram("short")
    assert not caption_fits_telegram("x" * 1025)
