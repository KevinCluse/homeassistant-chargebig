"""Shared fixtures for the chargeBIG test suite."""

from __future__ import annotations

import json
import re
from collections.abc import Generator
from pathlib import Path

import pytest
from yarl import URL

pytest_plugins = "pytest_homeassistant_custom_component"

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    """Load and parse a JSON fixture file by name."""
    return json.loads((FIXTURES_DIR / name).read_text())


def get_requests(mocked, method: str, url: str) -> list:
    """Return the aioresponses call log for one (method, url) pair.

    aioresponses keys its call log by ``(method, yarl.URL)``, which does not compare
    equal to a plain string -- this wraps the lookup so tests can pass plain strings.
    """
    return mocked.requests[(method, URL(url))]


def request_was_made(mocked, method: str, url: str) -> bool:
    """Return whether at least one request matching (method, url) was recorded."""
    return (method, URL(url)) in mocked.requests


def charge_point_info_pattern(base_url: str, code: str):
    """Match a charge-point/info call regardless of its ?language=&includeRFIDs= query.

    api.py always sends those two query parameters; matching them exactly would make
    every test brittle against harmless changes to that query string.
    """
    return re.compile(rf"^{re.escape(base_url)}/v1/charge-point/info/{code}(\?.*)?$")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> Generator[None]:
    """Make custom_components/chargebig visible to Home Assistant during tests."""
    yield
