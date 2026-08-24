"""Polling coordinator for the chargeBIG integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    ChargebigApiError,
    ChargebigAuthError,
    ChargebigClient,
    ChargebigConnectionError,
)
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CHARGE_POINT_CODE,
    CONF_PAYMENT_METHOD,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL_CHARGING,
    CONF_SCAN_INTERVAL_IDLE,
    CONF_TARIFF_ID,
    DEFAULT_SCAN_INTERVAL_CHARGING,
    DEFAULT_SCAN_INTERVAL_IDLE,
    DOMAIN,
)
from .models import ChargePointInfo, ChargingProcess, PaymentToken, Tokens

_LOGGER = logging.getLogger(__name__)

type ChargebigConfigEntry = ConfigEntry["ChargebigCoordinator"]


@dataclass(slots=True)
class ChargebigData:
    """Everything one polling cycle collects for a single charge point."""

    charge_point: ChargePointInfo
    process: ChargingProcess | None

    @property
    def is_charging(self) -> bool:
        """Return True while the charge point is actually delivering energy."""
        return self.process is not None and self.process.is_charging


class ChargebigCoordinator(DataUpdateCoordinator[ChargebigData]):
    """Polls one charge point and exposes the actions the entities trigger."""

    config_entry: ChargebigConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ChargebigConfigEntry) -> None:
        """Set up the coordinator for the charge point of ``entry``."""
        self.code: str = entry.data[CONF_CHARGE_POINT_CODE]
        tokens: Tokens | None = None
        if access_token := entry.data.get(CONF_ACCESS_TOKEN):
            tokens = Tokens(
                access_token=access_token,
                refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
            )
        self.client = ChargebigClient(
            async_get_clientsession(hass),
            entry.data[CONF_EMAIL],
            entry.data[CONF_PASSWORD],
            tokens=tokens,
            on_tokens_updated=self._persist_tokens,
        )
        self._payment_tokens: list[PaymentToken] | None = None
        # `self.config_entry` (used by `_interval_idle`) does not exist until after
        # `super().__init__()` runs, so the initial interval must be the plain default;
        # `_apply_interval()` corrects it for the entry's options after the first poll.
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {self.code}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_IDLE),
        )

    # ------------------------------------------------------------------ options

    @property
    def _interval_charging(self) -> int:
        """Return the poll interval to use while charging, in seconds."""
        return self.config_entry.options.get(
            CONF_SCAN_INTERVAL_CHARGING, DEFAULT_SCAN_INTERVAL_CHARGING
        )

    @property
    def _interval_idle(self) -> int:
        """Return the poll interval to use while idle, in seconds."""
        return self.config_entry.options.get(CONF_SCAN_INTERVAL_IDLE, DEFAULT_SCAN_INTERVAL_IDLE)

    def _persist_tokens(self, tokens: Tokens) -> None:
        """Write freshly issued tokens back into the config entry."""
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={
                **self.config_entry.data,
                CONF_ACCESS_TOKEN: tokens.access_token,
                CONF_REFRESH_TOKEN: tokens.refresh_token,
            },
        )

    # ------------------------------------------------------------------- polling

    async def _async_update_data(self) -> ChargebigData:
        """Fetch the charge point and, if a session is running, its live values."""
        try:
            charge_point = await self.client.async_get_charge_point(self.code)
            process: ChargingProcess | None = None
            if charge_point.charging_process_id is not None:
                process = await self.client.async_get_process(charge_point.charging_process_id)
        except ChargebigAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (ChargebigConnectionError, ChargebigApiError) as err:
            raise UpdateFailed(str(err)) from err

        data = ChargebigData(charge_point=charge_point, process=process)
        self._apply_interval(data)
        return data

    def _apply_interval(self, data: ChargebigData) -> None:
        """Poll fast while charging and slowly the rest of the time."""
        seconds = self._interval_charging if data.is_charging else self._interval_idle
        interval = timedelta(seconds=seconds)
        if self.update_interval != interval:
            _LOGGER.debug("%s: switching poll interval to %s", self.code, interval)
            self.update_interval = interval

    # ------------------------------------------------------------------- actions

    @property
    def process_id(self) -> int | None:
        """Return the id of the running session, if there is one."""
        if self.data is None:
            return None
        if self.data.process is not None and self.data.process.id is not None:
            return self.data.process.id
        return self.data.charge_point.charging_process_id

    async def _async_pick_payment(self) -> PaymentToken:
        """Return the payment method to charge with.

        The configured method wins; otherwise the first stored token the charge point
        also accepts is used, falling back to the first token on the account.
        """
        if self._payment_tokens is None:
            self._payment_tokens = await self.client.async_get_payment_tokens()
        if not self._payment_tokens:
            raise ChargebigApiError(400, "No payment method stored on the chargeBIG account")
        configured = self.config_entry.options.get(CONF_PAYMENT_METHOD)
        if configured:
            for token in self._payment_tokens:
                if token.payment_method == configured:
                    return token
        accepted = set(self.data.charge_point.payment_methods) if self.data else set()
        for token in self._payment_tokens:
            if not accepted or token.payment_method in accepted:
                return token
        return self._payment_tokens[0]

    async def async_start_charging(self, tariff_id: int | None = None) -> None:
        """Start a new charging session at this charge point."""
        if self.data is None:
            await self.async_request_refresh()
        charge_point = self.data.charge_point if self.data else None
        if charge_point is None:
            raise ChargebigApiError(503, "Charge point state is not known yet")
        tariff = charge_point.preferred_tariff(
            tariff_id if tariff_id is not None else self.config_entry.options.get(CONF_TARIFF_ID)
        )
        if tariff is None or tariff.id is None:
            raise ChargebigApiError(400, f"No tariff available at {self.code}")
        payment = await self._async_pick_payment()
        _LOGGER.debug(
            "%s: starting charge on tariff %s via %s",
            self.code,
            tariff.id,
            payment.payment_method,
        )
        await self.client.async_start(
            self.code,
            payment_token=payment.token,
            payment_method=payment.payment_method,
            tariff_id=tariff.id,
        )
        await self.async_request_refresh()

    async def async_pause_charging(self) -> None:
        """Pause the running charging session."""
        process_id = self.process_id
        if process_id is None:
            raise ChargebigApiError(409, f"No charging session running at {self.code}")
        await self.client.async_pause(process_id)
        await self.async_request_refresh()

    async def async_resume_charging(self) -> None:
        """Resume the paused charging session."""
        process_id = self.process_id
        if process_id is None:
            raise ChargebigApiError(409, f"No charging session running at {self.code}")
        await self.client.async_resume(process_id)
        await self.async_request_refresh()

    async def async_set_charging(self, charging: bool) -> None:
        """Bring the charge point into the requested state.

        Turning on resumes an existing session and starts a new one otherwise, which is
        what the single switch entity needs.
        """
        if not charging:
            await self.async_pause_charging()
        elif self.process_id is not None:
            await self.async_resume_charging()
        else:
            await self.async_start_charging()
