"""Tests for the chargeBIG config entry diagnostics."""

from __future__ import annotations

from aioresponses import aioresponses
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chargebig.api import API_BASE_URL
from custom_components.chargebig.const import CONF_CHARGE_POINT_CODE, DOMAIN
from custom_components.chargebig.diagnostics import async_get_config_entry_diagnostics

from .conftest import charge_point_info_pattern, load_fixture

EMAIL = "test@example.com"
PASSWORD = "hunter2"


async def test_diagnostics_redacts_secrets(hass: HomeAssistant) -> None:
    """Password and email are redacted; non-secret charge point data survives."""
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
            payload=load_fixture("charge_point_info.json"),
        )
        mocked.get(
            f"{API_BASE_URL}/v1/charging-processes/light/100001",
            payload=load_fixture("process_light_charging.json"),
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry_data"][CONF_PASSWORD] == "**REDACTED**"
    assert diagnostics["entry_data"]["email"] == "**REDACTED**"
    assert diagnostics["charge_point"]["hardwareId"] == "**REDACTED**"
    # Non-secret fields survive so the dump is still useful for debugging.
    assert diagnostics["charge_point"]["code"] == "XXYXX"
    assert diagnostics["process"]["chargingProcessDto"]["chargingStatus"] == "CHARGING"
