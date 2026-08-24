"""Tests for the chargeBIG config flow."""

from __future__ import annotations

from unittest.mock import patch

from aioresponses import aioresponses
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chargebig.api import API_BASE_URL
from custom_components.chargebig.const import CONF_CHARGE_POINT_CODE, DOMAIN

from .conftest import charge_point_info_pattern, load_fixture

EMAIL = "test@example.com"
PASSWORD = "hunter2"


async def _start_user_flow(hass: HomeAssistant):
    """Kick off the config flow up to (and including) the user step."""
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_full_flow_creates_entry(hass: HomeAssistant) -> None:
    """A valid login followed by a valid charge point code creates a config entry."""
    result = await _start_user_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with aioresponses() as mocked:
        mocked.post(
            f"{API_BASE_URL}/v1/auth/charger-user/login", payload=load_fixture("login.json")
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "charge_point"

    with aioresponses() as mocked:
        mocked.post(
            f"{API_BASE_URL}/v1/auth/charger-user/login", payload=load_fixture("login.json")
        )
        mocked.get(
            charge_point_info_pattern(API_BASE_URL, "XXYXX"),
            payload=load_fixture("charge_point_info.json"),
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CHARGE_POINT_CODE: "xxyxx"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test Location"
    assert result["data"][CONF_CHARGE_POINT_CODE] == "XXYXX"


async def test_invalid_password_shows_error(hass: HomeAssistant) -> None:
    """A rejected login re-shows the user step with invalid_auth."""
    result = await _start_user_flow(hass)
    with aioresponses() as mocked:
        mocked.post(
            f"{API_BASE_URL}/v1/auth/charger-user/login",
            status=401,
            payload=load_fixture("error_invalid_credentials.json"),
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: "wrong"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_connection_error_shows_error(hass: HomeAssistant) -> None:
    """A network failure during login re-shows the user step with cannot_connect."""
    result = await _start_user_flow(hass)
    with aioresponses() as mocked:
        mocked.post(f"{API_BASE_URL}/v1/auth/charger-user/login", exception=TimeoutError())
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
        )

    assert result["errors"] == {"base": "cannot_connect"}


async def test_unknown_charge_point_shows_error(hass: HomeAssistant) -> None:
    """A charge point code the account can't see re-shows that step with an error."""
    result = await _start_user_flow(hass)
    with aioresponses() as mocked:
        mocked.post(
            f"{API_BASE_URL}/v1/auth/charger-user/login", payload=load_fixture("login.json")
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
        )

    with aioresponses() as mocked:
        mocked.post(
            f"{API_BASE_URL}/v1/auth/charger-user/login", payload=load_fixture("login.json")
        )
        mocked.get(charge_point_info_pattern(API_BASE_URL, "NOPE"), status=404, payload={})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CHARGE_POINT_CODE: "nope"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "charge_point"
    assert result["errors"] == {"base": "charge_point_not_found"}


async def test_duplicate_charge_point_aborts(hass: HomeAssistant) -> None:
    """Configuring the same account + charge point twice aborts as already configured."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"{EMAIL}:XXYXX",
        data={CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD, CONF_CHARGE_POINT_CODE: "XXYXX"},
    ).add_to_hass(hass)

    result = await _start_user_flow(hass)
    with aioresponses() as mocked:
        mocked.post(
            f"{API_BASE_URL}/v1/auth/charger-user/login", payload=load_fixture("login.json")
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
        )

    with aioresponses() as mocked:
        mocked.post(
            f"{API_BASE_URL}/v1/auth/charger-user/login", payload=load_fixture("login.json")
        )
        mocked.get(
            charge_point_info_pattern(API_BASE_URL, "XXYXX"),
            payload=load_fixture("charge_point_info.json"),
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CHARGE_POINT_CODE: "XXYXX"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow_updates_password(hass: HomeAssistant) -> None:
    """A successful reauth updates the stored password and reloads the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"{EMAIL}:XXYXX",
        data={CONF_EMAIL: EMAIL, CONF_PASSWORD: "old-password", CONF_CHARGE_POINT_CODE: "XXYXX"},
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    with (
        aioresponses() as mocked,
        patch(
            "custom_components.chargebig.async_setup_entry",
            return_value=True,
        ),
    ):
        mocked.post(
            f"{API_BASE_URL}/v1/auth/charger-user/login", payload=load_fixture("login.json")
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "new-password"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new-password"
