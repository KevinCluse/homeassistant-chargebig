"""Config flow for the chargeBIG integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
)

from .api import ChargebigApiError, ChargebigAuthError, ChargebigClient, ChargebigConnectionError
from .const import (
    CONF_CHARGE_POINT_CODE,
    CONF_PAYMENT_METHOD,
    CONF_SCAN_INTERVAL_CHARGING,
    CONF_SCAN_INTERVAL_IDLE,
    CONF_TARIFF_ID,
    DEFAULT_LANGUAGE,
    DEFAULT_SCAN_INTERVAL_CHARGING,
    DEFAULT_SCAN_INTERVAL_IDLE,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)
STEP_REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})


class ChargebigConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle account login, then a charge point code, one entry per charge point."""

    VERSION = 1

    def __init__(self) -> None:
        """Track the account credentials while the flow walks its steps."""
        self._email: str | None = None
        self._password: str | None = None

    async def _async_try_login(self, email: str, password: str) -> ChargebigClient | None:
        """Log in with the given credentials, returning the client on success."""
        client = ChargebigClient(
            async_get_clientsession(self.hass), email, password, language=DEFAULT_LANGUAGE
        )
        await client.async_login()
        return client

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for chargeBIG account credentials and verify them."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self._async_try_login(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
            except ChargebigAuthError:
                errors["base"] = "invalid_auth"
            except ChargebigConnectionError:
                errors["base"] = "cannot_connect"
            except ChargebigApiError:
                _LOGGER.exception("Unexpected error logging in to chargeBIG")
                errors["base"] = "unknown"
            else:
                self._email = user_input[CONF_EMAIL]
                self._password = user_input[CONF_PASSWORD]
                return await self.async_step_charge_point()

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors)

    async def async_step_charge_point(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the charge point code and validate it against the account."""
        errors: dict[str, str] = {}
        if user_input is not None:
            code = user_input[CONF_CHARGE_POINT_CODE].strip().upper()
            await self.async_set_unique_id(f"{self._email}:{code}")
            self._abort_if_unique_id_configured()
            client = ChargebigClient(
                async_get_clientsession(self.hass),
                self._email,
                self._password,
                language=DEFAULT_LANGUAGE,
            )
            try:
                await client.async_login()
                charge_point = await client.async_get_charge_point(code)
            except ChargebigAuthError:
                errors["base"] = "invalid_auth"
            except ChargebigConnectionError:
                errors["base"] = "cannot_connect"
            except ChargebigApiError:
                errors["base"] = "charge_point_not_found"
            else:
                title = charge_point.location_name or f"chargeBIG {code}"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_EMAIL: self._email,
                        CONF_PASSWORD: self._password,
                        CONF_CHARGE_POINT_CODE: code,
                    },
                )

        return self.async_show_form(
            step_id="charge_point",
            data_schema=vol.Schema({vol.Required(CONF_CHARGE_POINT_CODE): str}),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start reauth after the stored password stopped working."""
        self._email = entry_data[CONF_EMAIL]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the new password and verify it before updating the entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self._async_try_login(self._email, user_input[CONF_PASSWORD])
            except ChargebigAuthError:
                errors["base"] = "invalid_auth"
            except ChargebigConnectionError:
                errors["base"] = "cannot_connect"
            else:
                reauth_entry = self._get_reauth_entry()
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={**reauth_entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={"email": self._email or ""},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        """Return the options flow for this entry."""
        return ChargebigOptionsFlow()


class ChargebigOptionsFlow(OptionsFlow):
    """Let the user tune poll intervals and the default tariff/payment method."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show and store the options form."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL_CHARGING,
                    default=current.get(
                        CONF_SCAN_INTERVAL_CHARGING, DEFAULT_SCAN_INTERVAL_CHARGING
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL, mode=NumberSelectorMode.BOX, unit_of_measurement="s"
                    )
                ),
                vol.Optional(
                    CONF_SCAN_INTERVAL_IDLE,
                    default=current.get(CONF_SCAN_INTERVAL_IDLE, DEFAULT_SCAN_INTERVAL_IDLE),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL, mode=NumberSelectorMode.BOX, unit_of_measurement="s"
                    )
                ),
                vol.Optional(CONF_TARIFF_ID): NumberSelector(
                    NumberSelectorConfig(min=0, mode=NumberSelectorMode.BOX)
                ),
                vol.Optional(CONF_PAYMENT_METHOD): SelectSelector(
                    SelectSelectorConfig(
                        options=["SEPA", "VISA", "MASTER_CARD", "PAYPAL", "VOUCHER"]
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
