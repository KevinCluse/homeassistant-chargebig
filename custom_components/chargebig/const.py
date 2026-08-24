"""Constants for the chargeBIG integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "chargebig"

#: Backend of the carica web app. The app itself is served from
#: ``https://app.carica.chargebig.com`` (``…\.de`` redirects there), but every API
#: call goes to the bare host.
API_BASE_URL: Final = "https://carica.chargebig.com"
APP_BASE_URL: Final = "https://app.carica.chargebig.com"

#: Sent as ``Origin``/``Referer`` so the backend sees the same values as from the web app.
APP_ORIGIN: Final = APP_BASE_URL

DEFAULT_LANGUAGE: Final = "de"
API_TIMEOUT: Final = 30

CONF_CHARGE_POINT_CODE: Final = "charge_point_code"
CONF_TARIFF_ID: Final = "tariff_id"
CONF_PAYMENT_METHOD: Final = "payment_method"
CONF_SCAN_INTERVAL_CHARGING: Final = "scan_interval_charging"
CONF_SCAN_INTERVAL_IDLE: Final = "scan_interval_idle"

CONF_ACCESS_TOKEN: Final = "access_token"
CONF_REFRESH_TOKEN: Final = "refresh_token"

DEFAULT_SCAN_INTERVAL_CHARGING: Final = 30
DEFAULT_SCAN_INTERVAL_IDLE: Final = 300
MIN_SCAN_INTERVAL: Final = 10

ATTR_CHARGE_POINT_CODE: Final = CONF_CHARGE_POINT_CODE
ATTR_TARIFF_ID: Final = CONF_TARIFF_ID
ATTR_PAYMENT_METHOD: Final = CONF_PAYMENT_METHOD

SERVICE_START_CHARGING: Final = "start_charging"
SERVICE_PAUSE_CHARGING: Final = "pause_charging"
SERVICE_RESUME_CHARGING: Final = "resume_charging"
SERVICE_REFRESH: Final = "refresh"

#: Value of ``chargingStatus`` while energy is actually flowing.
STATUS_CHARGING: Final = "CHARGING"

#: Prefixes of ``chargingStatus`` values that mean "session exists but is halted".
#: The backend is not documented, so this is matched by prefix rather than against a
#: closed list -- an unknown status must never break the integration.
PAUSED_STATUS_PREFIXES: Final = ("PAUSED", "SUSPENDED")
