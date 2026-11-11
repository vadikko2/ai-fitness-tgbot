"""Entry helpers. Routers try a widget, then keep the keyboard screen."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from fitness_bot.presentation.widgets.frame import WidgetScreenId
from fitness_bot.presentation.widgets.gateway import WidgetGateway, widget_gateway
from fitness_bot.presentation.widgets.state import as_number, pack_state, read_state


async def open_widget(user_id: int, screen: WidgetScreenId, chat_id: int) -> bool:
    """True when the widget bubble is on screen. False means draw the keyboard."""
    gateway = widget_gateway()
    if gateway is None:
        return False
    opened = await gateway.open(user_id, screen, chat_id=chat_id)
    return not opened.use_keyboard


async def show_main_menu(user_id: int, chat_id: int, *, note: str | None = None) -> bool:
    """Wipe the page and open the main menu widget (or classic fallback inside the gateway)."""
    gateway = widget_gateway()
    if gateway is None:
        return False
    await gateway.return_to_menu(user_id, chat_id, note=note)
    return True


async def refresh_widget(user_id: int) -> bool:
    gateway = widget_gateway()
    if gateway is None:
        return False
    frame = await gateway.refresh(user_id)
    return frame is not None


def intake_is_open(user_id: int) -> bool:
    gateway = widget_gateway()
    if gateway is None:
        return False
    binding = gateway.bindings.get(user_id)
    return binding is not None and binding.screen is WidgetScreenId.INTAKE


async def write_console_kg(gateway: WidgetGateway, user_id: int, kilograms: Decimal) -> bool:
    """Put a typed weight into the console draft and redraw that same bubble."""
    binding = gateway.bindings.get(user_id)
    if binding is None or binding.screen is not WidgetScreenId.CONSOLE or binding.frame is None:
        return False
    data = read_state(binding.frame.chat_data)
    if data.get("ph") not in (None, "work"):
        return False
    data["kg"] = as_number(kilograms)
    updated = replace(binding.frame, chat_data=pack_state(data))
    gateway.bindings.put(user_id, replace(binding, frame=updated))
    await gateway.refresh(user_id)
    return True
