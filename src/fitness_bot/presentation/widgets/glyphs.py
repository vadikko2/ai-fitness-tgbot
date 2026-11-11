"""Sex-specific exercise glyphs. Same folder rule as pose and measurement guides."""

from __future__ import annotations

from pathlib import Path

from fitness_bot.domain.enums import Sex
from fitness_bot.presentation.progress_pose_images import guide_sex_folder
from fitness_bot.shared.paths import EXERCISE_GLYPHS_DIR

# One letter in chat_data → file name under male/ or female/.
GLYPH_FILES: dict[str, str] = {
    "q": "squat",
    "h": "hinge",
    "p": "push",
    "l": "pull",
    "c": "core",
    "u": "lunge",
}

_COVERS: dict[str, str] = {}

# One shared figure when a sex folder has no SVG yet, or when six of them miss the zlib budget.
SILHOUETTE_SVG = (
    '<svg class="g" data-g="*" viewBox="0 0 64 64">'
    '<path fill="#8fb4d9" d="M28 6h8v8h-8zM22 16h20l2 12H20z"/>'
    '<path fill="#022046" d="M20 30h24v4H20zM24 36l-6 20h6l4-12 4 12h6l-6-20z"/>'
    '<path fill="#F5D22D" d="M6 28h52v3H6z"/>'
    "</svg>"
)


def exercise_glyph_path(code: str, *, sex: Sex | None = None, kind: str = "png") -> Path | None:
    """Return the sex-folder glyph, or None when the code is unknown or the file is missing.

    ``Sex.FEMALE`` selects ``female``; every other value, including a profile with no sex yet,
    selects ``male`` via :func:`guide_sex_folder`.
    """
    name = GLYPH_FILES.get(code)
    if name is None or kind not in {"png", "svg"}:
        return None
    path = EXERCISE_GLYPHS_DIR / guide_sex_folder(sex) / f"{name}.{kind}"
    return path if path.is_file() else None


def glyph_code_for(name: str, muscles: list[str] | tuple[str, ...] | None = None) -> str:
    """Map an exercise name and its primary muscles onto ``q|h|p|l|c|u``."""
    text = " ".join([name, *(muscles or ())]).casefold()
    if any(word in text for word in ("выпад", "lunge")):
        return "u"
    if any(word in text for word in ("присед", "squat", "квадрицепс")):
        return "q"
    if any(word in text for word in ("станов", "румын", "hinge", "бицепс бедра", "ягодиц")):
        return "h"
    if any(word in text for word in ("жим", "отжим", "push", "грудь", "трицепс", "плеч")):
        return "p"
    if any(word in text for word in ("пресс", "планка", "скруч", "core", "косые")):
        return "c"
    if any(word in text for word in ("тяг", "подтяг", "pull", "спин", "широчай", "бицепс")):
        return "l"
    return "q"


def glyph_markup(sex: Sex | None) -> str:
    """Inline SVG for one sex folder. A missing file falls back to the shared silhouette."""
    folder = EXERCISE_GLYPHS_DIR / guide_sex_folder(sex)
    parts: list[str] = []
    for code, name in GLYPH_FILES.items():
        path = folder / f"{name}.svg"
        if not path.is_file():
            return SILHOUETTE_SVG
        svg = path.read_text(encoding="utf-8").strip()
        if svg.startswith("<?xml"):
            svg = svg.split("?>", 1)[1].strip()
        if not svg.startswith("<svg"):
            return SILHOUETTE_SVG
        parts.append(svg.replace("<svg", f'<svg class="g" data-g="{code}"', 1))
    return "".join(parts)


def remember_glyph_cover(path: str, file_id: str) -> None:
    """Keep the Telegram file_id of a glyph PNG so the next video can use it as cover."""
    _COVERS[path] = file_id


def glyph_cover_file_id(path: str | None) -> str | None:
    if path is None:
        return None
    return _COVERS.get(path)
