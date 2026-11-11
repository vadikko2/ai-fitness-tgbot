"""Load poster shells. The console document is built per sex folder."""

from __future__ import annotations

from pathlib import Path

from fitness_bot.domain.enums import Sex
from fitness_bot.presentation.widgets.glyphs import SILHOUETTE_SVG, glyph_markup
from fitness_bot.presentation.widgets.limits import WidgetLimitError
from fitness_bot.presentation.widgets.shell import FileWidgetShell, load_widget_shell, minify_html

_SHELLS = Path(__file__).resolve().parent.parent / "shells"
_CHROME = _SHELLS / "chrome.html"
_CHROME_MARK = "<!-- chrome -->"
_GLYPHS = "<!-- glyphs -->"


def load_static_shell(shell_id: str) -> FileWidgetShell:
    return load_widget_shell(shell_id, _SHELLS / f"{shell_id}.html", chrome=_CHROME)


def _console_document(markup: str) -> str:
    source = (_SHELLS / "console.html").read_text(encoding="utf-8")
    chrome = _CHROME.read_text(encoding="utf-8")
    source = source.replace(_CHROME_MARK, chrome).replace(_GLYPHS, markup)
    return minify_html(source)


def load_console_shell(sex: Sex | None) -> FileWidgetShell:
    """Inline that sex folder's SVGs. Over-budget art falls back to one shared silhouette."""
    try:
        return FileWidgetShell("console", _console_document(glyph_markup(sex)))
    except WidgetLimitError:
        return FileWidgetShell("console", _console_document(SILHOUETTE_SVG))


def load_shells() -> dict[str, FileWidgetShell]:
    return {
        "console-male": load_console_shell(Sex.MALE),
        "console-female": load_console_shell(Sex.FEMALE),
        "intake": load_static_shell("intake"),
        "week": load_static_shell("week"),
        "home": load_static_shell("home"),
        "summary": load_static_shell("summary"),
    }
