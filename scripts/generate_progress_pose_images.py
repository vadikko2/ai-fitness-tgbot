#!/usr/bin/env python3
"""Stylize / organize progress-pose PNGs (dev-only, Pillow).

Layout produced under data/progress_poses/:

  male/{front,side,back,overview}.png
  female/{front,side,back,overview}.png

Gender safety: prefer ``{male,female}_progress_{angle}`` staging assets so
we never collide with measurement-guide ``*_overview_v2.png``. Cross-copying
between genders is forbidden.

Footer chrome: strip prior CTA → navy bar · yellow ruler icon · yellow text
  (angles: «фронт» / «бок» / «спина»; overview: «3 ракурса»)

  uv run --with pillow python scripts/generate_progress_pose_images.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "data" / "progress_poses"
ASSETS = Path(
    "/Users/vadimkozyrevskij/.cursor/projects/"
    "Users-vadimkozyrevskij-project-folder-ai-fitness-tgbot/assets"
)

W, H = 900, 1200
FOOTER_H = 100
# Drop baked-in CTA chrome from sources.
FOOTER_CROP_FRAC = 0.22
NAVY = (2, 32, 70)
YELLOW = (245, 210, 45)
WHITE = (255, 255, 255)

POSE_CODES = ("front", "side", "back")

POSE_META: dict[str, tuple[str, str, str]] = {
    # title, hint, footer CTA
    "front": ("Фронт", "анфас, руки чуть в стороны", "фронт"),
    "side": ("Бок", "профиль, стопы вместе", "бок"),
    "back": ("Спина", "со спины, руки чуть в стороны", "спина"),
}

OVERVIEW_META = ("3 ракурса", "фронт · бок · спина", "3 ракурса")


def try_font(size: int) -> ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


FONT_FOOT = try_font(36)
FONT_TITLE = try_font(54)
FONT_HINT = try_font(28)


def draw_ruler_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int = 28) -> None:
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=YELLOW)
    ang = math.radians(-40)
    length, width = 34, 10
    dx, dy = math.cos(ang), math.sin(ang)
    px, py = -dy, dx
    corners = []
    for sx, sy in (
        (-length / 2, -width / 2),
        (length / 2, -width / 2),
        (length / 2, width / 2),
        (-length / 2, width / 2),
    ):
        corners.append((cx + sx * dx + sy * px, cy + sx * dy + sy * py))
    draw.polygon(corners, fill=NAVY)
    for t in (-12, -4, 4, 12):
        x0 = cx + t * dx - 4 * px
        y0 = cy + t * dy - 4 * py
        x1 = cx + t * dx + 4 * px
        y1 = cy + t * dy + 4 * py
        draw.line((x0, y0, x1, y1), fill=YELLOW, width=2)


def strip_prior_footer(img: Image.Image) -> Image.Image:
    """Crop away any baked-in bottom CTA so we never stack footers."""
    rgb = img.convert("RGB")
    sw, sh = rgb.size
    keep_h = max(1, int(sh * (1.0 - FOOTER_CROP_FRAC)))
    return rgb.crop((0, 0, sw, keep_h))


def paint_footer(canvas: Image.Image, *, text: str) -> Image.Image:
    """Paint the unified navy+yellow ruler footer on a W×H canvas."""
    if canvas.size != (W, H):
        canvas = canvas.convert("RGB").resize((W, H), Image.Resampling.LANCZOS)
    else:
        canvas = canvas.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    top = H - FOOTER_H
    draw.rectangle((0, top, W, H), fill=NAVY)
    cy = top + FOOTER_H // 2
    draw_ruler_icon(draw, 56, cy, r=30)
    sep_x = 110
    draw.line((sep_x, top + 22, sep_x, H - 22), fill=YELLOW, width=3)
    bbox = draw.textbbox((0, 0), text, font=FONT_FOOT)
    th = bbox[3] - bbox[1]
    draw.text((sep_x + 28, cy - th // 2 - 2), text, font=FONT_FOOT, fill=YELLOW)
    return canvas


def apply_footer(img: Image.Image, *, text: str, header_reserve: int = 150) -> Image.Image:
    """Strip prior CTA chrome, fit content below header band, paint footer."""
    content = strip_prior_footer(img)
    canvas = Image.new("RGB", (W, H), WHITE)
    area_h = H - FOOTER_H - header_reserve
    scale = min(W / content.width, area_h / content.height)
    nw, nh = max(1, int(content.width * scale)), max(1, int(content.height * scale))
    content = content.resize((nw, nh), Image.Resampling.LANCZOS)
    y = header_reserve + max(0, (area_h - nh) // 2)
    canvas.paste(content, ((W - nw) // 2, y))
    return paint_footer(canvas, text=text)


def apply_header(img: Image.Image, title: str, hint: str) -> Image.Image:
    """Redraw a clean header band at the top (covers old headers / baked titles)."""
    canvas = img.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, W, 150), fill=WHITE)
    tb = draw.textbbox((0, 0), title, font=FONT_TITLE)
    tw = tb[2] - tb[0]
    draw.text(((W - tw) // 2, 28), title, font=FONT_TITLE, fill=NAVY)
    hb = draw.textbbox((0, 0), hint, font=FONT_HINT)
    hw = hb[2] - hb[0]
    hy = 100
    draw.text(((W - hw) // 2, hy), hint, font=FONT_HINT, fill=NAVY)
    line_y = hy + 36
    gap = 16
    left_end = (W - hw) // 2 - gap
    right_start = (W + hw) // 2 + gap
    draw.line((48, line_y, max(48, left_end), line_y), fill=NAVY, width=2)
    draw.line((min(W - 48, right_start), line_y, W - 48, line_y), fill=NAVY, width=2)
    draw.ellipse((W // 2 - 4, line_y + 10, W // 2 + 4, line_y + 18), fill=NAVY)
    draw.line((W // 2 - 80, line_y + 14, W // 2 - 12, line_y + 14), fill=NAVY, width=2)
    draw.line((W // 2 + 12, line_y + 14, W // 2 + 80, line_y + 14), fill=NAVY, width=2)
    return canvas


def stylize_pose(src: Path, dest: Path, *, title: str, hint: str, footer_text: str) -> None:
    img = apply_footer(Image.open(src), text=footer_text)
    img = apply_header(img, title, hint)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, format="PNG", optimize=True)
    print(f"wrote {dest.relative_to(REPO_ROOT)} ({dest.stat().st_size} bytes)")


def _find_asset(*names: str) -> Path | None:
    for name in names:
        p = ASSETS / name
        if p.is_file():
            return p
    return None


def _import_gendered_pose(gender: str, code: str) -> Path | None:
    """Resolve a gender-prefixed staging asset. Never cross-imports the other gender.

    Prefer ``{gender}_progress_{code}`` so we do not collide with measurement-guide
    staging names such as ``male_overview_v2.png``.
    """
    names = [
        f"{gender}_progress_{code}_v2.png",
        f"{gender}_progress_{code}.png",
        f"progress_{gender}_{code}_v2.png",
        f"progress_{gender}_{code}.png",
    ]
    # Angle silhouettes may also live as male_front.png etc.; overview must not
    # fall back to measurement ``*_overview_v2.png``.
    if code != "overview":
        names.extend(
            (
                f"{gender}_{code}_v2.png",
                f"{gender}_{code}.png",
                f"{code}_{gender}_v2.png",
                f"{code}_{gender}.png",
            )
        )
    else:
        names.extend((f"{gender}_{code}.png", f"{code}_{gender}.png"))
    return _find_asset(*names)


def main() -> None:
    male_dir = OUT / "male"
    female_dir = OUT / "female"
    male_dir.mkdir(parents=True, exist_ok=True)
    female_dir.mkdir(parents=True, exist_ok=True)

    for gender, dest_dir in (("male", male_dir), ("female", female_dir)):
        for code in POSE_CODES:
            title, hint, footer = POSE_META[code]
            dest = dest_dir / f"{code}.png"
            staged = _import_gendered_pose(gender, code)
            src = staged if staged is not None else (dest if dest.is_file() else None)
            if src is None:
                print(f"ERROR: missing {gender}/{code}.png — refuse to fill from other gender")
                continue
            stylize_pose(src, dest, title=title, hint=hint, footer_text=footer)

        ov_title, ov_hint, ov_footer = OVERVIEW_META
        dest = dest_dir / "overview.png"
        staged = _import_gendered_pose(gender, "overview")
        src = staged if staged is not None else (dest if dest.is_file() else None)
        if src is None:
            print(f"ERROR: missing {gender}/overview.png — refuse to fill from other gender")
            continue
        stylize_pose(src, dest, title=ov_title, hint=ov_hint, footer_text=ov_footer)


if __name__ == "__main__":
    main()
