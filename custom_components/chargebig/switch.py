"""Switch entity for the chargeBIG integration."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import ChargebigApiError, ChargebigConnectionError
from .coordinator import ChargebigConfigEntry
from .entity import ChargebigEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChargebigConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the chargeBIG charging switch for one charge point."""
    async_add_entities([ChargebigChargingSwitch(entry.runtime_data)])


class ChargebigChargingSwitch(ChargebigEntity, SwitchEntity):
    """Start/resume charging when turned on, pause it when turned off."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_translation_key = "charging"

    def __init__(self, coordinator) -> None:
        """Bind this switch to the coordinator's charging entity."""
        super().__init__(coordinator, "charging")

    @property
    def is_on(self) -> bool | None:
        """Return True while a session is running (charging or paused)."""
        if self._data is None or self._data.process is None:
            return False
        return self._data.process.is_charging

    async def async_turn_on(self, **kwargs) -> None:
        """Start a new session, or resume one that is paused."""
        try:
            await self.coordinator.async_set_charging(True)
        except (ChargebigApiError, ChargebigConnectionError) as err:
            raise HomeAssistantError(
                f"Could not start charging at {self.coordinator.code}: {err}"
            ) from err

    async def async_turn_off(self, **kwargs) -> None:
        """Pause the running session."""
        try:
            await self.coordinator.async_set_charging(False)
        except (ChargebigApiError, ChargebigConnectionError) as err:
            raise HomeAssistantError(
                f"Could not pause charging at {self.coordinator.code}: {err}"
            ) from err
