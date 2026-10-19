"""The chargeBIG integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import ChargebigConfigEntry, ChargebigCoordinator
from .services import async_setup_services

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ChargebigConfigEntry) -> bool:
    """Set up chargeBIG from a config entry."""
    coordinator = ChargebigCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_setup_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ChargebigConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
