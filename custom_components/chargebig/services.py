"""Service actions for the chargeBIG integration.

Registered once per Home Assistant instance (not per config entry); each call is routed
to the coordinator of the charge point named by ``device_id``.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .api import ChargebigApiError, ChargebigConnectionError
from .const import (
    ATTR_TARIFF_ID,
    DOMAIN,
    SERVICE_PAUSE_CHARGING,
    SERVICE_REFRESH,
    SERVICE_RESUME_CHARGING,
    SERVICE_START_CHARGING,
)
from .coordinator import ChargebigConfigEntry, ChargebigCoordinator

ATTR_DEVICE_ID = "device_id"

SERVICE_DEVICE_SCHEMA = vol.Schema({vol.Required(ATTR_DEVICE_ID): cv.string})
SERVICE_START_SCHEMA = SERVICE_DEVICE_SCHEMA.extend({vol.Optional(ATTR_TARIFF_ID): vol.Coerce(int)})


def _coordinator_for_device(hass: HomeAssistant, device_id: str) -> ChargebigCoordinator:
    """Resolve the service call's target device to its coordinator."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)
    if device is None:
        raise ServiceValidationError(f"Unknown device {device_id}")
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is not None and entry.domain == DOMAIN:
            config_entry: ChargebigConfigEntry = entry
            return config_entry.runtime_data
    raise ServiceValidationError(f"Device {device_id} is not a chargeBIG charge point")


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the chargebig.* services, once per Home Assistant instance."""
    if hass.services.has_service(DOMAIN, SERVICE_START_CHARGING):
        return

    async def _handle(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator_for_device(hass, call.data[ATTR_DEVICE_ID])
        try:
            if call.service == SERVICE_START_CHARGING:
                await coordinator.async_start_charging(call.data.get(ATTR_TARIFF_ID))
            elif call.service == SERVICE_PAUSE_CHARGING:
                await coordinator.async_pause_charging()
            elif call.service == SERVICE_RESUME_CHARGING:
                await coordinator.async_resume_charging()
            elif call.service == SERVICE_REFRESH:
                await coordinator.async_request_refresh()
        except (ChargebigApiError, ChargebigConnectionError) as err:
            raise HomeAssistantError(str(err)) from err
        return None

    hass.services.async_register(
        DOMAIN, SERVICE_START_CHARGING, _handle, schema=SERVICE_START_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_PAUSE_CHARGING, _handle, schema=SERVICE_DEVICE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RESUME_CHARGING, _handle, schema=SERVICE_DEVICE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        _handle,
        schema=SERVICE_DEVICE_SCHEMA,
        supports_response=SupportsResponse.NONE,
    )
