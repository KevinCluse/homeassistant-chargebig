"""Tests for the chargeBIG charging switch entity."""

from __future__ import annotations

from aioresponses import aioresponses
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chargebig.api import API_BASE_URL
from custom_components.chargebig.const import CONF_CHARGE_POINT_CODE, DOMAIN

from .conftest import charge_point_info_pattern, load_fixture, request_was_made

EMAIL = "test@example.com"
PASSWORD = "hunter2"
ENTITY_ID = "switch.test_location_charging"


def _mock_login_and_charge_point(mocked, charge_point_fixture: str) -> None:
    """Register the login + charge-point-info calls every refresh performs."""
    mocked.post(f"{API_BASE_URL}/v1/auth/charger-user/login", payload=load_fixture("login.json"))
    mocked.get(
        charge_point_info_pattern(API_BASE_URL, "XXYXX"),
        payload=load_fixture(charge_point_fixture),
    )


async def test_switch_on_resumes_paused_session(hass: HomeAssistant) -> None:
    """Turning the switch on while a session is merely paused resumes it, not restarts it."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"{EMAIL}:XXYXX",
        data={CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD, CONF_CHARGE_POINT_CODE: "XXYXX"},
    )
    entry.add_to_hass(hass)
    with aioresponses() as mocked:
        _mock_login_and_charge_point(mocked, "charge_point_info.json")
        mocked.get(
            f"{API_BASE_URL}/v1/charging-processes/light/100001",
            payload=load_fixture("process_light_paused.json"),
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == "off"

    with aioresponses() as mocked:
        mocked.post(f"{API_BASE_URL}/v1/charging-processes/100001/resume", status=200, body="")
        _mock_login_and_charge_point(mocked, "charge_point_info.json")
        mocked.get(
            f"{API_BASE_URL}/v1/charging-processes/light/100001",
            payload=load_fixture("process_light_charging.json"),
        )
        await hass.services.async_call(
            SWITCH_DOMAIN, SERVICE_TURN_ON, {"entity_id": ENTITY_ID}, blocking=True
        )
        assert request_was_made(
            mocked, "POST", f"{API_BASE_URL}/v1/charging-processes/100001/resume"
        )

    assert hass.states.get(ENTITY_ID).state == "on"


async def test_switch_on_starts_new_session_when_idle(hass: HomeAssistant) -> None:
    """Turning the switch on with no session running starts a new one via /charge."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"{EMAIL}:XXYXX",
        data={CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD, CONF_CHARGE_POINT_CODE: "XXYXX"},
    )
    entry.add_to_hass(hass)
    with aioresponses() as mocked:
        _mock_login_and_charge_point(mocked, "charge_point_info_idle.json")
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with aioresponses() as mocked:
        mocked.get(
            f"{API_BASE_URL}/v1/payment-methods", payload=load_fixture("payment_methods.json")
        )
        mocked.post(f"{API_BASE_URL}/v1/charge-point/XXYXX/charge", status=200, body="")
        _mock_login_and_charge_point(mocked, "charge_point_info.json")
        mocked.get(
            f"{API_BASE_URL}/v1/charging-processes/light/100001",
            payload=load_fixture("process_light_charging.json"),
        )
        await hass.services.async_call(
            SWITCH_DOMAIN, SERVICE_TURN_ON, {"entity_id": ENTITY_ID}, blocking=True
        )
        assert request_was_made(mocked, "POST", f"{API_BASE_URL}/v1/charge-point/XXYXX/charge")


async def test_switch_off_pauses_session(hass: HomeAssistant) -> None:
    """Turning the switch off pauses a currently charging session."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"{EMAIL}:XXYXX",
        data={CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD, CONF_CHARGE_POINT_CODE: "XXYXX"},
    )
    entry.add_to_hass(hass)
    with aioresponses() as mocked:
        _mock_login_and_charge_point(mocked, "charge_point_info.json")
        mocked.get(
            f"{API_BASE_URL}/v1/charging-processes/light/100001",
            payload=load_fixture("process_light_charging.json"),
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == "on"

    with aioresponses() as mocked:
        mocked.post(f"{API_BASE_URL}/v1/charging-processes/100001/pause", status=200, body="")
        _mock_login_and_charge_point(mocked, "charge_point_info.json")
        mocked.get(
            f"{API_BASE_URL}/v1/charging-processes/light/100001",
            payload=load_fixture("process_light_paused.json"),
        )
        await hass.services.async_call(
            SWITCH_DOMAIN, SERVICE_TURN_OFF, {"entity_id": ENTITY_ID}, blocking=True
        )
        assert request_was_made(
            mocked, "POST", f"{API_BASE_URL}/v1/charging-processes/100001/pause"
        )

    assert hass.states.get(ENTITY_ID).state == "off"
