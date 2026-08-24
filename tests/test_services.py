"""Tests for the chargebig.* services registered in services.py."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from aioresponses import aioresponses
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chargebig.api import API_BASE_URL, ChargebigApiError
from custom_components.chargebig.const import (
    CONF_CHARGE_POINT_CODE,
    DOMAIN,
    SERVICE_PAUSE_CHARGING,
    SERVICE_REFRESH,
    SERVICE_RESUME_CHARGING,
    SERVICE_START_CHARGING,
)

from .conftest import charge_point_info_pattern, load_fixture

EMAIL = "test@example.com"
PASSWORD = "hunter2"


async def _setup_entry(hass: HomeAssistant) -> tuple[MockConfigEntry, str]:
    """Set up a config entry and return it with its device's registry id."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"{EMAIL}:XXYXX",
        data={CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD, CONF_CHARGE_POINT_CODE: "XXYXX"},
    )
    entry.add_to_hass(hass)
    with aioresponses() as mocked:
        mocked.post(
            f"{API_BASE_URL}/v1/auth/charger-user/login", payload=load_fixture("login.json")
        )
        mocked.get(
            charge_point_info_pattern(API_BASE_URL, "XXYXX"),
            payload=load_fixture("charge_point_info_idle.json"),
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(identifiers={(DOMAIN, "XXYXX")})
    assert device is not None
    return entry, device.id


async def test_start_charging_service_routes_to_coordinator(hass: HomeAssistant) -> None:
    """chargebig.start_charging calls the coordinator for the target device's entry."""
    entry, device_id = await _setup_entry(hass)
    entry.runtime_data.async_start_charging = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_START_CHARGING,
        {"device_id": device_id, "tariff_id": 214},
        blocking=True,
    )

    entry.runtime_data.async_start_charging.assert_awaited_once_with(214)


async def test_pause_charging_service_routes_to_coordinator(hass: HomeAssistant) -> None:
    """chargebig.pause_charging calls the coordinator for the target device's entry."""
    entry, device_id = await _setup_entry(hass)
    entry.runtime_data.async_pause_charging = AsyncMock()

    await hass.services.async_call(
        DOMAIN, SERVICE_PAUSE_CHARGING, {"device_id": device_id}, blocking=True
    )

    entry.runtime_data.async_pause_charging.assert_awaited_once()


async def test_resume_charging_service_routes_to_coordinator(hass: HomeAssistant) -> None:
    """chargebig.resume_charging calls the coordinator for the target device's entry."""
    entry, device_id = await _setup_entry(hass)
    entry.runtime_data.async_resume_charging = AsyncMock()

    await hass.services.async_call(
        DOMAIN, SERVICE_RESUME_CHARGING, {"device_id": device_id}, blocking=True
    )

    entry.runtime_data.async_resume_charging.assert_awaited_once()


async def test_refresh_service_routes_to_coordinator(hass: HomeAssistant) -> None:
    """chargebig.refresh calls the coordinator's refresh for the target device's entry."""
    entry, device_id = await _setup_entry(hass)
    entry.runtime_data.async_request_refresh = AsyncMock()

    await hass.services.async_call(DOMAIN, SERVICE_REFRESH, {"device_id": device_id}, blocking=True)

    entry.runtime_data.async_request_refresh.assert_awaited_once()


async def test_service_call_with_unknown_device_raises(hass: HomeAssistant) -> None:
    """Calling a service with a device id that doesn't exist is a validation error."""
    await _setup_entry(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, SERVICE_REFRESH, {"device_id": "does-not-exist"}, blocking=True
        )


async def test_service_call_wraps_api_errors(hass: HomeAssistant) -> None:
    """An API error raised by the coordinator surfaces as a HomeAssistantError."""
    entry, device_id = await _setup_entry(hass)
    entry.runtime_data.async_pause_charging = AsyncMock(
        side_effect=ChargebigApiError(409, "No session")
    )

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, SERVICE_PAUSE_CHARGING, {"device_id": device_id}, blocking=True
        )
