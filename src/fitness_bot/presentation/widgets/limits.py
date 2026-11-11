"""Byte limits shared by the widget transport and the HTML loader."""

from __future__ import annotations

import zlib

HTML_ZLIB_LIMIT = 4096
STATE_BYTE_LIMIT = 1024


class WidgetLimitError(ValueError):
    """HTML or state that Telegram would reject for a widget."""


def ensure_widget_html(html: str) -> None:
    if "\x00" in html:
        raise WidgetLimitError("widget html contains NUL")
    size = len(zlib.compress(html.encode("utf-8"), 9))
    if size > HTML_ZLIB_LIMIT:
        raise WidgetLimitError(f"widget html zlib size {size} exceeds {HTML_ZLIB_LIMIT}")


def ensure_widget_state(value: str, *, what: str) -> None:
    size = len(value.encode("utf-8"))
    if size > STATE_BYTE_LIMIT:
        raise WidgetLimitError(f"{what} is {size} UTF-8 bytes; limit is {STATE_BYTE_LIMIT}")
