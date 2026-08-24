"""Tests for the pure parsing helpers in custom_components.chargebig.models."""

from __future__ import annotations

from datetime import UTC, timedelta

import pytest

from custom_components.chargebig.models import (
    ChargePointInfo,
    ChargingProcess,
    parse_api_datetime,
    parse_iso_duration,
)

from .conftest import load_fixture


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("PT3H47M23.455350362S", timedelta(hours=3, minutes=47, seconds=23.455350362)),
        ("PT48M", timedelta(minutes=48)),
        ("PT0S", timedelta(0)),
        ("P1DT2H3M4S", timedelta(days=1, hours=2, minutes=3, seconds=4)),
        (120, timedelta(seconds=120)),
        ("garbage", None),
        (None, None),
    ],
)
def test_parse_iso_duration(value, expected) -> None:
    """The duration parser covers the formats the backend has been seen to emit."""
    assert parse_iso_duration(value) == expected


def test_parse_api_datetime_assumes_utc_when_no_offset() -> None:
    """A bare backend timestamp is treated as UTC (see docs/api.md for why)."""
    parsed = parse_api_datetime("2026-08-24T17:52:31.938545")
    assert parsed.tzinfo == UTC
    assert parsed.hour == 17


def test_parse_api_datetime_keeps_explicit_offset() -> None:
    """A timestamp that does carry an offset is left untouched."""
    parsed = parse_api_datetime("2026-08-24T17:52:31.938545+02:00")
    assert parsed.utcoffset() == timedelta(hours=2)


def test_parse_api_datetime_rejects_garbage() -> None:
    """Unparseable or missing values become None instead of raising."""
    assert parse_api_datetime(None) is None
    assert parse_api_datetime("not a date") is None


def test_charge_point_info_from_real_payload() -> None:
    """The fixture modelled on the real backend response parses into expected fields."""
    info = ChargePointInfo.from_dict(load_fixture("charge_point_info.json"))

    assert info.code == "XXYXX"
    assert info.charging_process_id == 100001
    assert info.location_name == "Test Location"
    assert info.is_online is True
    assert info.preferred_tariff().id == 214


def test_charge_point_info_zero_process_id_means_idle() -> None:
    """A chargingProcessId of 0 is treated the same as "no session", not id 0."""
    info = ChargePointInfo.from_dict(load_fixture("charge_point_info_idle.json"))
    assert info.charging_process_id is None


def test_charging_process_charging_state() -> None:
    """A CHARGING payload reports is_charging True and is_paused False."""
    process = ChargingProcess.from_dict(load_fixture("process_light_charging.json"))
    assert process.is_charging is True
    assert process.is_paused is False
    assert process.energy_kwh == 16.508
    assert process.tariff.cents_per_kwh == 40


def test_charging_process_paused_state() -> None:
    """A PAUSED_EVSE payload reports is_paused True and is_charging False."""
    process = ChargingProcess.from_dict(load_fixture("process_light_paused.json"))
    assert process.is_charging is False
    assert process.is_paused is True


def test_charging_process_handles_empty_payload() -> None:
    """An empty/unexpected payload degrades to a mostly-None process, not a crash."""
    process = ChargingProcess.from_dict({})
    assert process.id is None
    assert process.is_charging is False
    assert process.is_paused is False
