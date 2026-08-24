"""Tests for ChargebigCoordinator: polling interval and action routing."""

from __future__ import annotations

from datetime import timedelta

from aioresponses import aioresponses
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chargebig.api import API_BASE_URL
from custom_components.chargebig.const import (
    CONF_CHARGE_POINT_CODE,
    DEFAULT_SCAN_INTERVAL_CHARGING,
    DEFAULT_SCAN_INTERVAL_IDLE,
    DOMAIN,
)

from .conftest import charge_point_info_pattern, get_requests, load_fixture

EMAIL = "test@example.com"
PASSWORD = "hunter2"


def _mock_login_and_charge_point(mocked, charge_point_fixture: str) -> None:
    """Register the login + charge-point-info calls every refresh performs."""
    mocked.post(f"{API_BASE_URL}/v1/auth/charger-user/login", payload=load_fixture("login.json"))
    mocked.get(
        charge_point_info_pattern(API_BASE_URL, "XXYXX"),
        payload=load_fixture(charge_point_fixture),
    )


async def _setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Set up a config entry against a mocked, currently-charging backend."""
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
    return entry


async def test_first_refresh_uses_charging_interval(hass: HomeAssistant) -> None:
    """While a session is CHARGING, the coordinator polls at the fast interval."""
    entry = await _setup_entry(hass)
    coordinator = entry.runtime_data
    assert coordinator.data.is_charging is True
    assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL_CHARGING)


async def test_idle_charge_point_uses_idle_interval(hass: HomeAssistant) -> None:
    """A charge point with no running session polls at the slow interval."""
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

    coordinator = entry.runtime_data
    assert coordinator.data.process is None
    assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL_IDLE)


async def test_pause_charging_calls_pause_endpoint(hass: HomeAssistant) -> None:
    """async_pause_charging pauses the session found in the last poll."""
    entry = await _setup_entry(hass)
    coordinator = entry.runtime_data

    with aioresponses() as mocked:
        mocked.post(f"{API_BASE_URL}/v1/charging-processes/100001/pause", status=200, body="")
        _mock_login_and_charge_point(mocked, "charge_point_info.json")
        mocked.get(
            f"{API_BASE_URL}/v1/charging-processes/light/100001",
            payload=load_fixture("process_light_paused.json"),
        )
        await coordinator.async_pause_charging()

    assert coordinator.data.process.is_paused is True


async def test_resume_charging_calls_resume_endpoint(hass: HomeAssistant) -> None:
    """async_resume_charging resumes the session found in the last poll."""
    entry = await _setup_entry(hass)
    coordinator = entry.runtime_data

    with aioresponses() as mocked:
        mocked.post(f"{API_BASE_URL}/v1/charging-processes/100001/resume", status=200, body="")
        _mock_login_and_charge_point(mocked, "charge_point_info.json")
        mocked.get(
            f"{API_BASE_URL}/v1/charging-processes/light/100001",
            payload=load_fixture("process_light_charging.json"),
        )
        await coordinator.async_resume_charging()

    assert coordinator.data.process.is_charging is True


async def test_start_charging_picks_tariff_and_payment(hass: HomeAssistant) -> None:
    """async_start_charging posts the charge point's default tariff and stored token."""
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
    coordinator = entry.runtime_data

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
        await coordinator.async_start_charging()
        request = get_requests(mocked, "POST", f"{API_BASE_URL}/v1/charge-point/XXYXX/charge")[0]

    assert request.kwargs["json"]["tariffId"] == 214
    assert request.kwargs["json"]["paymentToken"] == "TESTTOKEN123456"
    assert request.kwargs["json"]["paymentMethod"] == "SEPA"
