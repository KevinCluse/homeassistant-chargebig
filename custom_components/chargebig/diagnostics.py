"""Diagnostics support for the chargeBIG integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN
from .coordinator import ChargebigConfigEntry

TO_REDACT = {
    "email",
    "password",
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    "paymentToken",
    "token",
    "hardwareId",
    "latitude",
    "longitude",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ChargebigConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for one config entry, with secrets redacted."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": dict(entry.options),
        "charge_point": (async_redact_data(data.charge_point.raw, TO_REDACT) if data else None),
        "process": (
            async_redact_data(data.process.raw, TO_REDACT) if data and data.process else None
        ),
    }
