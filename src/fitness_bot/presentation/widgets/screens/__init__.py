"""Register the widget screens on a gateway."""

from __future__ import annotations

from fitness_bot.presentation.widgets.screens.console import ConsoleScreen
from fitness_bot.presentation.widgets.screens.home import HomeScreen
from fitness_bot.presentation.widgets.screens.intake import IntakeScreen
from fitness_bot.presentation.widgets.screens.load import load_shells
from fitness_bot.presentation.widgets.screens.menu import MenuScreen
from fitness_bot.presentation.widgets.screens.summary import SummaryScreen
from fitness_bot.presentation.widgets.screens.week import WeekScreen


def build_widget_screens() -> tuple[
    ConsoleScreen,
    IntakeScreen,
    WeekScreen,
    HomeScreen,
    SummaryScreen,
    MenuScreen,
]:
    shells = load_shells()
    console = ConsoleScreen(shells["console"])
    return (
        console,
        IntakeScreen(shells["intake"]),
        WeekScreen(shells["week"]),
        HomeScreen(shells["home"]),
        SummaryScreen(shells["summary"]),
        MenuScreen(shells["menu"]),
    )


def register_widget_screens(gateway: object) -> None:
    for screen in build_widget_screens():
        gateway.register_screen(screen)  # type: ignore[attr-defined]
