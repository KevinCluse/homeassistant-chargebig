"""Tests for custom_components.chargebig.api.ChargebigClient."""

from __future__ import annotations

import pytest
from aioresponses import aioresponses
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.chargebig.api import (
    API_BASE_URL,
    ChargebigApiError,
    ChargebigAuthError,
    ChargebigClient,
)
from custom_components.chargebig.models import PaymentToken, Tokens

from .conftest import charge_point_info_pattern, get_requests, load_fixture, request_was_made

EMAIL = "test@example.com"
PASSWORD = "hunter2"


def make_client(hass: HomeAssistant, **kwargs) -> ChargebigClient:
    """Build a client bound to the test HA instance's aiohttp session."""
    return ChargebigClient(async_get_clientsession(hass), EMAIL, PASSWORD, **kwargs)


async def test_login_stores_tokens(hass: HomeAssistant) -> None:
    """A successful login stores the returned access and refresh tokens."""
    client = make_client(hass)
    with aioresponses() as mocked:
        mocked.post(
            f"{API_BASE_URL}/v1/auth/charger-user/login",
            payload=load_fixture("login.json"),
        )
        tokens = await client.async_login()

    assert tokens.access_token == "eyJhbGciOiJIUzUxMiJ9.example-access-token.signature"
    assert client.tokens == tokens


async def test_login_sends_expected_body(hass: HomeAssistant) -> None:
    """The login request carries email, password and the fixed extra fields."""
    client = make_client(hass)
    with aioresponses() as mocked:
        mocked.post(
            f"{API_BASE_URL}/v1/auth/charger-user/login",
            payload=load_fixture("login.json"),
        )
        await client.async_login()
        request = get_requests(mocked, "POST", f"{API_BASE_URL}/v1/auth/charger-user/login")[0]

    assert request.kwargs["json"] == {
        "email": EMAIL,
        "password": PASSWORD,
        "fireBaseId": "",
        "language": "de",
    }


async def test_authenticated_request_sends_bearer_token(hass: HomeAssistant) -> None:
    """Once logged in, subsequent requests carry the access token as a bearer header."""
    client = make_client(
        hass, tokens=Tokens(access_token="stored-token", refresh_token="stored-refresh")
    )
    with aioresponses() as mocked:
        mocked.get(
            f"{API_BASE_URL}/v1/charger-user/get-account",
            payload=load_fixture("get_account.json"),
        )
        await client.async_get_account()
        request = get_requests(mocked, "GET", f"{API_BASE_URL}/v1/charger-user/get-account")[0]

    assert request.kwargs["headers"]["Authorization"] == "Bearer stored-token"


async def test_expired_token_triggers_single_relogin(hass: HomeAssistant) -> None:
    """A 401 causes exactly one re-login, then the original call is retried once."""
    client = make_client(
        hass, tokens=Tokens(access_token="stale-token", refresh_token="stale-refresh")
    )
    with aioresponses() as mocked:
        mocked.get(f"{API_BASE_URL}/v1/charger-user/get-account", status=401, payload={})
        mocked.post(
            f"{API_BASE_URL}/v1/auth/charger-user/login",
            payload=load_fixture("login.json"),
        )
        mocked.get(
            f"{API_BASE_URL}/v1/charger-user/get-account",
            payload=load_fixture("get_account.json"),
        )
        account = await client.async_get_account()

    assert account.email == "test@example.com"
    assert client.tokens.access_token == "eyJhbGciOiJIUzUxMiJ9.example-access-token.signature"


async def test_repeated_401_raises_auth_error(hass: HomeAssistant) -> None:
    """If the backend rejects the token even after a fresh login, this surfaces as auth error."""
    client = make_client(
        hass, tokens=Tokens(access_token="stale-token", refresh_token="stale-refresh")
    )
    with aioresponses() as mocked:
        mocked.get(f"{API_BASE_URL}/v1/charger-user/get-account", status=401, payload={})
        mocked.post(
            f"{API_BASE_URL}/v1/auth/charger-user/login",
            payload=load_fixture("login.json"),
        )
        mocked.get(f"{API_BASE_URL}/v1/charger-user/get-account", status=401, payload={})
        with pytest.raises(ChargebigAuthError):
            await client.async_get_account()


async def test_invalid_credentials_raise_auth_error(hass: HomeAssistant) -> None:
    """A 401 on the login call itself is an auth error, not a generic API error."""
    client = make_client(hass)
    with aioresponses() as mocked:
        mocked.post(
            f"{API_BASE_URL}/v1/auth/charger-user/login",
            status=401,
            payload=load_fixture("error_invalid_credentials.json"),
        )
        with pytest.raises(ChargebigAuthError):
            await client.async_login()


async def test_api_error_carries_german_message(hass: HomeAssistant) -> None:
    """A structured backend error keeps both the English and German message."""
    client = make_client(hass, tokens=Tokens(access_token="token"))
    with aioresponses() as mocked:
        mocked.post(
            f"{API_BASE_URL}/v1/charge-point/XXYXX/charge",
            status=406,
            payload=load_fixture("error_charge_point_unavailable.json"),
        )
        with pytest.raises(ChargebigApiError) as excinfo:
            await client.async_start(
                "XXYXX", payment_token="tok", payment_method="SEPA", tariff_id=214
            )

    assert excinfo.value.status == 406
    assert excinfo.value.message_de == "Ladepunkt nicht verfügbar"
    assert excinfo.value.localized("de") == "Ladepunkt nicht verfügbar"
    assert excinfo.value.localized("en") == "ChargePoint Unavailable"


async def test_get_charge_point_parses_payload(hass: HomeAssistant) -> None:
    """The charge point endpoint is parsed into a ChargePointInfo with its tariffs."""
    client = make_client(hass, tokens=Tokens(access_token="token"))
    with aioresponses() as mocked:
        mocked.get(
            charge_point_info_pattern(API_BASE_URL, "XXYXX"),
            payload=load_fixture("charge_point_info.json"),
        )
        charge_point = await client.async_get_charge_point("XXYXX")

    assert charge_point.code == "XXYXX"
    assert charge_point.charging_process_id == 100001
    assert charge_point.is_online is True
    assert len(charge_point.tariffs) == 1
    assert charge_point.tariffs[0].cents_per_kwh == 40


async def test_get_process_light_parses_charging_session(hass: HomeAssistant) -> None:
    """The light session endpoint yields a ChargingProcess reflecting live values."""
    client = make_client(hass, tokens=Tokens(access_token="token"))
    with aioresponses() as mocked:
        mocked.get(
            f"{API_BASE_URL}/v1/charging-processes/light/100001",
            payload=load_fixture("process_light_charging.json"),
        )
        process = await client.async_get_process(100001)

    assert process.is_charging is True
    assert process.energy_kwh == 16.508
    assert process.power_kw == 4.442


async def test_get_payment_tokens(hass: HomeAssistant) -> None:
    """Stored payment methods are parsed into PaymentToken entries."""
    client = make_client(hass, tokens=Tokens(access_token="token"))
    with aioresponses() as mocked:
        mocked.get(
            f"{API_BASE_URL}/v1/payment-methods",
            payload=load_fixture("payment_methods.json"),
        )
        tokens = await client.async_get_payment_tokens()

    assert tokens == [PaymentToken(token="TESTTOKEN123456", payment_method="SEPA")]


async def test_pause_and_resume_call_expected_endpoints(hass: HomeAssistant) -> None:
    """Pause and resume hit their respective per-session endpoints."""
    client = make_client(hass, tokens=Tokens(access_token="token"))
    with aioresponses() as mocked:
        mocked.post(f"{API_BASE_URL}/v1/charging-processes/100001/pause", status=200, body="")
        mocked.post(f"{API_BASE_URL}/v1/charging-processes/100001/resume", status=200, body="")
        await client.async_pause(100001)
        await client.async_resume(100001)

    assert request_was_made(mocked, "POST", f"{API_BASE_URL}/v1/charging-processes/100001/pause")
    assert request_was_made(mocked, "POST", f"{API_BASE_URL}/v1/charging-processes/100001/resume")
