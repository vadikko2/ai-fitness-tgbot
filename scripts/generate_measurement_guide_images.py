#!/usr/bin/env python3
"""Stylize / organize measurement-guide PNGs (dev-only, Pillow).

Layout produced under data/measurement_guides/:

  male/{site}.png, male/overview.png
  female/{site}.png, female/overview.png
  overview_source.png   # FB/VK-inspired reference only (not served)

Gender safety: male_* staging assets only feed male/; female_* only feed
female/. Cross-copying between genders is forbidden.

Footer chrome: strip prior CTA → navy bar · yellow ruler icon · yellow text
  (sites: «одно число в см»; overviews: «выбери точку»)

  uv run --with pillow python scripts/generate_measurement_guide_images.py
"""
from __future__ import annotations

import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "data" / "measurement_guides"
ASSETS = Path(
    "/Users/vadimkozyrevskij/.cursor/projects/"
    "Users-vadimkozyrevskij-project-folder-ai-fitness-tgbot/assets"
)

W, H = 900, 1200
FOOTER_H = 100
# Drop baked-in CTA chrome (white pill and/or prior navy bars) from sources.
# ~22% covers stacked double footers without eating site photo/insets.
FOOTER_CROP_FRAC = 0.22
NAVY = (2, 32, 70)
YELLOW = (245, 210, 45)
WHITE = (255, 255, 255)

SITE_CODES = (
    "neck",
    "chest",
    "waist",
    "hips",
    "biceps",
    "thigh",
    "calf",
    "shoulder_girdle",
)

SITE_META: dict[str, tuple[str, str]] = {
    "neck": ("Шея", "чуть выше ключиц"),
    "chest": ("Грудь", "под мышками, только торс"),
    "waist": ("Талия", "самый узкий участок"),
    "hips": ("Бёдра/таз", "самая широкая часть"),
    "biceps": ("Бицепс", "самая толстая часть плеча"),
    "thigh": ("Бедро", "верхняя треть"),
    "calf": ("Голень", "самая толстая часть"),
    "shoulder_girdle": ("Плечевой пояс", "через дельты"),
}


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
    # tilted ruler rectangle
    ang = math.radians(-40)
    length, width = 34, 10
    dx, dy = math.cos(ang), math.sin(ang)
    px, py = -dy, dx
    corners = []
    for sx, sy in ((-length / 2, -width / 2), (length / 2, -width / 2), (length / 2, width / 2), (-length / 2, width / 2)):
        corners.append((cx + sx * dx + sy * px, cy + sx * dy + sy * py))
    draw.polygon(corners, fill=NAVY)
    # tick marks on ruler
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


def paint_footer(canvas: Image.Image, *, text: str = "одно число в см") -> Image.Image:
    """Paint the unified navy+yellow ruler footer on a W×H canvas (bottom band only)."""
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


def apply_footer(img: Image.Image, *, text: str = "одно число в см") -> Image.Image:
    """Strip prior CTA chrome, fit content, paint a single navy+yellow footer."""
    content = strip_prior_footer(img)
    canvas = Image.new("RGB", (W, H), WHITE)
    area_h = H - FOOTER_H
    scale = min(W / content.width, area_h / content.height)
    nw, nh = max(1, int(content.width * scale)), max(1, int(content.height * scale))
    content = content.resize((nw, nh), Image.Resampling.LANCZOS)
    # Top-align so existing headers stay at the top; white gap above footer is fine.
    canvas.paste(content, ((W - nw) // 2, 0))
    return paint_footer(canvas, text=text)


def apply_header(img: Image.Image, title: str, hint: str) -> Image.Image:
    """Redraw a clean thigh-style header band at the top (covers old headers)."""
    canvas = img.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, W, 150), fill=WHITE)
    # title
    tb = draw.textbbox((0, 0), title, font=FONT_TITLE)
    tw = tb[2] - tb[0]
    draw.text(((W - tw) // 2, 28), title, font=FONT_TITLE, fill=NAVY)
    # hint + decorative lines/dot
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


def stylize_site(src: Path, dest: Path, *, title: str, hint: str, redraw_header: bool = False) -> None:
    img = Image.open(src)
    img = apply_footer(img)
    if redraw_header:
        img = apply_header(img, title, hint)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, format="PNG", optimize=True)
    print(f"wrote {dest.relative_to(REPO_ROOT)} ({dest.stat().st_size} bytes)")


def build_overview_from_source(dest: Path, *, title: str, hint: str, footer_text: str) -> None:
    """Compose overview card from overview_source.png (watermark cropped away)."""
    source = OUT / "overview_source.png"
    if not source.is_file():
        raise FileNotFoundError(f"missing {source}")
    fig = Image.open(source).convert("RGBA")
    # Crop bottom watermark band (~12% of height)
    fw, fh = fig.size
    fig = fig.crop((0, 0, fw, int(fh * 0.88)))
    canvas = Image.new("RGB", (W, H), WHITE)
    # Fit figure into middle area
    max_w, max_h = W - 80, H - 320
    scale = min(max_w / fig.width, max_h / fig.height)
    nw, nh = int(fig.width * scale), int(fig.height * scale)
    fig = fig.resize((nw, nh), Image.Resampling.LANCZOS)
    # composite on white (flatten alpha)
    base = Image.new("RGBA", fig.size, (255, 255, 255, 255))
    fig = Image.alpha_composite(base, fig).convert("RGB")
    x = (W - nw) // 2
    y = 170 + (max_h - nh) // 2
    canvas.paste(fig, (x, y))
    canvas = apply_header(canvas, title, hint)
    canvas = paint_footer(canvas, text=footer_text)
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest, format="PNG", optimize=True)
    print(f"wrote {dest.relative_to(REPO_ROOT)} ({dest.stat().st_size} bytes)")


def _find_asset(*names: str) -> Path | None:
    for name in names:
        p = ASSETS / name
        if p.is_file():
            return p
    return None


def _import_gendered_site(gender: str, code: str) -> Path | None:
    """Resolve a gender-prefixed staging asset. Never cross-imports the other gender."""
    prefix = gender  # "male" | "female"
    return _find_asset(
        f"{prefix}_{code}_v2.png",
        f"{prefix}_{code}.png",
        f"{code}_{prefix}_v2.png",
        f"{code}_{prefix}.png",
    )


def _stamp_overview(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    img = apply_footer(Image.open(src).convert("RGB").resize((W, H), Image.Resampling.LANCZOS), text="выбери точку")
    img.save(dest, format="PNG", optimize=True)
    print(f"wrote {dest.relative_to(REPO_ROOT)} ({dest.stat().st_size} bytes) [overview]")


def main() -> None:
    male_dir = OUT / "male"
    female_dir = OUT / "female"
    male_dir.mkdir(parents=True, exist_ok=True)
    female_dir.mkdir(parents=True, exist_ok=True)

    # Migrate legacy flat PNGs → male/ ONLY (never into female/)
    for code in SITE_CODES:
        legacy = OUT / f"{code}.png"
        male_target = male_dir / f"{code}.png"
        if legacy.is_file() and not male_target.is_file():
            shutil.move(str(legacy), str(male_target))
            print(f"moved {legacy.name} → male/{code}.png")

    # Male sites: prefer male_* staging assets, else restamp existing male/
    for code in SITE_CODES:
        title, hint = SITE_META[code]
        dest = male_dir / f"{code}.png"
        staged = _import_gendered_site("male", code)
        src = staged if staged is not None else (dest if dest.is_file() else None)
        if src is None:
            print(f"ERROR: missing male/{code}.png — refuse to fill from female/")
            continue
        # Chest redo uses raw staged photos without chrome — always redraw header.
        redraw = code == "chest" and staged is not None
        stylize_site(src, dest, title=title, hint=hint, redraw_header=redraw)

    # Female sites: female_* only — NEVER copy from male/
    for code in SITE_CODES:
        title, hint = SITE_META[code]
        dest = female_dir / f"{code}.png"
        staged = _import_gendered_site("female", code)
        src = staged if staged is not None else (dest if dest.is_file() else None)
        if src is None:
            print(f"ERROR: missing female/{code}.png — refuse to fill from male/")
            continue
        redraw = code == "chest" and staged is not None
        stylize_site(src, dest, title=title, hint=hint, redraw_header=redraw)

    # Dual overviews (inspired by overview_source.png; no watermarked ship)
    male_ov = male_dir / "overview.png"
    female_ov = female_dir / "overview.png"
    male_ov_asset = _find_asset(
        "male_overview_v2.png",
        "male_overview.png",
        "overview_male_v2.png",
        "overview_male.png",
    )
    female_ov_asset = _find_asset(
        "female_overview_v2.png",
        "female_overview.png",
        "overview_female_v2.png",
        "overview_female.png",
    )

    if male_ov_asset is not None:
        _stamp_overview(male_ov_asset, male_ov)
    elif male_ov.is_file():
        _stamp_overview(male_ov, male_ov)
    else:
        build_overview_from_source(
            male_ov,
            title="Обхваты",
            hint="куда приложить ленту",
            footer_text="выбери точку",
        )

    if female_ov_asset is not None:
        _stamp_overview(female_ov_asset, female_ov)
    elif female_ov.is_file():
        _stamp_overview(female_ov, female_ov)
    else:
        print("ERROR: missing female/overview.png — refuse to copy male overview")

    # Remove leftover flat root site PNGs (keep NOTICE + overview_source)
    for code in SITE_CODES:
        leftover = OUT / f"{code}.png"
        if leftover.is_file():
            leftover.unlink()
            print(f"removed legacy {leftover.name}")
    leftover_ov = OUT / "overview.png"
    if leftover_ov.is_file():
        leftover_ov.unlink()
        print("removed legacy overview.png")


if __name__ == "__main__":
    main()
