"""Load poster shells. One document per screen, with no figures inlined."""

from __future__ import annotations

from pathlib import Path

from fitness_bot.presentation.widgets.shell import FileWidgetShell, load_widget_shell

_SHELLS = Path(__file__).resolve().parent.parent / "shells"
_CHROME = _SHELLS / "chrome.html"
_IDS = ("console", "intake", "week", "home", "summary")


def load_static_shell(shell_id: str) -> FileWidgetShell:
    return load_widget_shell(shell_id, _SHELLS / f"{shell_id}.html", chrome=_CHROME)


def load_shells() -> dict[str, FileWidgetShell]:
    return {shell_id: load_static_shell(shell_id) for shell_id in _IDS}
