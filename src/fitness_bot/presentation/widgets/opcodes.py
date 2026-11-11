"""ASCII opcodes for widget taps. One grammar, dispatched only to the bound screen."""

from __future__ import annotations

import re
from dataclasses import dataclass

from fitness_bot.presentation.widgets.frame import WidgetScreenId

OPCODE_BYTE_LIMIT = 64

_CODE = re.compile(r"[A-Za-z0-9_-]+")
_INDEX = re.compile(r"0|[1-9][0-9]{0,3}")
_PRESETS = frozenset({"30", "45", "60", "90"})
_RPE = frozenset({"6", "7", "8", "9", "10"})
_ALTS = frozenset({"0", "1", "2"})

_EXACT: dict[str, WidgetScreenId] = {
    "sync": WidgetScreenId.CONSOLE,
    "ok": WidgetScreenId.CONSOLE,
    "w+": WidgetScreenId.CONSOLE,
    "w-": WidgetScreenId.CONSOLE,
    "r+": WidgetScreenId.CONSOLE,
    "r-": WidgetScreenId.CONSOLE,
    "skip": WidgetScreenId.CONSOLE,
    "alt": WidgetScreenId.CONSOLE,
    "back": WidgetScreenId.CONSOLE,
    "how": WidgetScreenId.CONSOLE,
    "vid": WidgetScreenId.CONSOLE,
    "sum": WidgetScreenId.CONSOLE,
    "view": WidgetScreenId.CONSOLE,
    "end": WidgetScreenId.CONSOLE,
    "inc": WidgetScreenId.INTAKE,
    "dec": WidgetScreenId.INTAKE,
    "done": WidgetScreenId.INTAKE,
    "text": WidgetScreenId.INTAKE,
    "day+": WidgetScreenId.WEEK,
    "day-": WidgetScreenId.WEEK,
    "drop": WidgetScreenId.WEEK,
    "swap": WidgetScreenId.WEEK,
    "approve": WidgetScreenId.WEEK,
    "go": WidgetScreenId.HOME,
    "again": WidgetScreenId.HOME,
    "menu": WidgetScreenId.HOME,
    "home": WidgetScreenId.SUMMARY,
}


@dataclass(frozen=True, slots=True)
class Opcode:
    raw: str
    screen: WidgetScreenId
    name: str
    arg: str | None = None


@dataclass(frozen=True, slots=True)
class OpcodeRejection:
    reason: str


def parse_opcode(raw: str) -> Opcode | OpcodeRejection:
    if raw == "":
        return OpcodeRejection("empty")
    if len(raw.encode("utf-8")) > OPCODE_BYTE_LIMIT:
        return OpcodeRejection("size")
    if not _is_opcode_ascii(raw):
        return OpcodeRejection("ascii")
    screen = _EXACT.get(raw)
    if screen is not None:
        return Opcode(raw=raw, screen=screen, name=raw)
    parsed = _parameter(raw)
    if parsed is None:
        return OpcodeRejection("unknown")
    return parsed


def _is_opcode_ascii(raw: str) -> bool:
    return raw.isascii() and all(33 <= ord(char) <= 126 for char in raw)


def _parameter(raw: str) -> Opcode | None:
    prefixed = (
        ("rpe:", WidgetScreenId.CONSOLE, "rpe", _RPE),
        ("alt:", WidgetScreenId.CONSOLE, "alt", _ALTS),
        ("preset:", WidgetScreenId.INTAKE, "preset", _PRESETS),
    )
    for prefix, screen, name, allowed in prefixed:
        if not raw.startswith(prefix):
            continue
        arg = raw[len(prefix) :]
        if arg not in allowed:
            return None
        return Opcode(raw=raw, screen=screen, name=name, arg=arg)
    if raw.startswith("pick:"):
        arg = raw[5:]
        if not arg or _CODE.fullmatch(arg) is None:
            return None
        return Opcode(raw=raw, screen=WidgetScreenId.INTAKE, name="pick", arg=arg)
    if raw.startswith("slot:"):
        arg = raw[5:]
        if _INDEX.fullmatch(arg) is None:
            return None
        return Opcode(raw=raw, screen=WidgetScreenId.WEEK, name="slot", arg=arg)
    if raw.startswith("swap:"):
        arg = raw[5:]
        if _INDEX.fullmatch(arg) is None:
            return None
        return Opcode(raw=raw, screen=WidgetScreenId.WEEK, name="swap", arg=arg)
    if raw.startswith("day:"):
        arg = raw[4:]
        if arg not in {"1", "2", "3", "4", "5", "6", "7"}:
            return None
        return Opcode(raw=raw, screen=WidgetScreenId.HOME, name="day", arg=arg)
    return None
