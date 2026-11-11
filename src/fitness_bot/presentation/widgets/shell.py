"""Load a widget document, minify it, and refuse HTML that zlib cannot keep under 4096 bytes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

from fitness_bot.presentation.widgets.limits import ensure_widget_html

_CHROME = "<!-- chrome -->"
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_SPACE = re.compile(r"\s+")


class WidgetShell(Protocol):
    shell_id: str

    def html(self) -> str:
        """Minified document. The loader refuses it when zlib level 9 is over 4096 bytes."""


class FileWidgetShell:
    def __init__(self, shell_id: str, html: str) -> None:
        ensure_widget_html(html)
        self.shell_id = shell_id
        self._html = html

    def html(self) -> str:
        return self._html


def minify_html(source: str) -> str:
    without_comments = _COMMENT.sub("", source)
    return _SPACE.sub(" ", without_comments).strip()


def load_widget_shell(shell_id: str, path: Path, *, chrome: Path | None = None) -> FileWidgetShell:
    source = path.read_text(encoding="utf-8")
    chrome_html = chrome.read_text(encoding="utf-8") if chrome is not None else ""
    if _CHROME in source:
        source = source.replace(_CHROME, chrome_html)
    return FileWidgetShell(shell_id, minify_html(source))
