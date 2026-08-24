"""Minimal async client for the undocumented chargeBIG (carica) backend.

This module deliberately knows nothing about Home Assistant so that it can be exercised
on its own. The protocol was reconstructed from a HAR capture of the official web app;
see ``docs/api.md`` for the endpoint reference.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession

from .const import (
    API_BASE_URL,
    API_TIMEOUT,
    APP_ORIGIN,
    DEFAULT_LANGUAGE,
)
from .models import Account, ChargePointInfo, ChargingProcess, PaymentToken, Tokens

_LOGGER = logging.getLogger(__name__)

#: The backend exposes rotated tokens through these response headers (advertised via
#: ``Access-Control-Expose-Headers``). They are optional -- most responses omit them.
_ACCESS_TOKEN_HEADER = "accessToken"
_REFRESH_TOKEN_HEADER = "refreshToken"


class ChargebigError(Exception):
    """Base class for every error raised by the client."""


class ChargebigConnectionError(ChargebigError):
    """The backend could not be reached."""


class ChargebigAuthError(ChargebigError):
    """The credentials were rejected."""


class ChargebigApiError(ChargebigError):
    """The backend answered with a structured error payload."""

    def __init__(
        self,
        status: int,
        message: str | None = None,
        message_de: str | None = None,
    ) -> None:
        """Store the backend's status code and both message variants."""
        self.status = status
        self.message = message
        self.message_de = message_de
        super().__init__(message_de or message or f"HTTP {status}")

    def localized(self, language: str = DEFAULT_LANGUAGE) -> str:
        """Return the message in ``language`` where the backend offers a translation."""
        if language.lower().startswith("de") and self.message_de:
            return self.message_de
        return self.message or self.message_de or f"HTTP {self.status}"


class ChargebigClient:
    """Talks to ``carica.chargebig.com`` on behalf of one charger user."""

    def __init__(
        self,
        session: ClientSession,
        email: str,
        password: str,
        *,
        language: str = DEFAULT_LANGUAGE,
        tokens: Tokens | None = None,
        on_tokens_updated: Callable[[Tokens], None] | None = None,
    ) -> None:
        """Initialise the client, optionally resuming a previously stored session."""
        self._session = session
        self._email = email
        self._password = password
        self._language = language
        self._tokens = tokens
        self._on_tokens_updated = on_tokens_updated
        self._login_lock = asyncio.Lock()

    @property
    def tokens(self) -> Tokens | None:
        """Return the tokens currently held, if any."""
        return self._tokens

    def update_password(self, password: str) -> None:
        """Replace the stored password, e.g. after a reauth flow."""
        self._password = password

    # ------------------------------------------------------------------ transport

    def _headers(self, *, authenticated: bool) -> dict[str, str]:
        """Build the request headers, mirroring what the web app sends."""
        headers = {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Origin": APP_ORIGIN,
            "Referer": f"{APP_ORIGIN}/",
        }
        if authenticated and self._tokens:
            headers["Authorization"] = f"Bearer {self._tokens.access_token}"
        return headers

    def _capture_rotated_tokens(self, response: ClientResponse) -> None:
        """Adopt tokens the backend rotated into the response headers."""
        access = response.headers.get(_ACCESS_TOKEN_HEADER)
        if not access or (self._tokens and access == self._tokens.access_token):
            return
        refresh = response.headers.get(_REFRESH_TOKEN_HEADER) or (
            self._tokens.refresh_token if self._tokens else None
        )
        self._set_tokens(Tokens(access_token=access, refresh_token=refresh))

    def _set_tokens(self, tokens: Tokens) -> None:
        """Store new tokens and notify the owner so they can be persisted."""
        self._tokens = tokens
        if self._on_tokens_updated:
            self._on_tokens_updated(tokens)

    async def _raise_for_status(self, response: ClientResponse) -> None:
        """Convert a non-2xx response into the matching exception."""
        if response.status < 400:
            return
        message: str | None = None
        message_de: str | None = None
        try:
            payload = await response.json(content_type=None)
        except (ValueError, ClientError):
            payload = None
        if isinstance(payload, dict):
            message = payload.get("message") or payload.get("error")
            message_de = payload.get("messageDe")
        if response.status in (401, 403):
            raise ChargebigAuthError(message_de or message or f"HTTP {response.status}")
        raise ChargebigApiError(response.status, message, message_de)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        authenticated: bool = True,
        _retry: bool = True,
    ) -> Any:
        """Perform one API call, refreshing the session once on a 401."""
        if authenticated and self._tokens is None:
            await self.async_login()

        url = f"{API_BASE_URL}{path}"
        try:
            async with asyncio.timeout(API_TIMEOUT):
                response = await self._session.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    headers=self._headers(authenticated=authenticated),
                )
                async with response:
                    self._capture_rotated_tokens(response)
                    if response.status in (401, 403) and authenticated and _retry:
                        _LOGGER.debug(
                            "%s %s rejected the stored token, logging in again",
                            method,
                            path,
                        )
                        await self.async_login(force=True)
                        return await self._request(
                            method,
                            path,
                            params=params,
                            json=json,
                            authenticated=authenticated,
                            _retry=False,
                        )
                    await self._raise_for_status(response)
                    if response.status == 204 or not await response.read():
                        return None
                    return await response.json(content_type=None)
        except TimeoutError as err:
            raise ChargebigConnectionError(f"Timeout calling {path}") from err
        except ClientError as err:
            raise ChargebigConnectionError(f"Error calling {path}: {err}") from err

    # ---------------------------------------------------------------------- auth

    async def async_login(self, *, force: bool = False) -> Tokens:
        """Log in with the stored credentials and remember the returned tokens."""
        async with self._login_lock:
            if self._tokens is not None and not force:
                # Another coroutine logged in while this one waited for the lock.
                return self._tokens
            if force:
                self._tokens = None
            payload = await self._request(
                "POST",
                "/v1/auth/charger-user/login",
                json={
                    "email": self._email,
                    "password": self._password,
                    "fireBaseId": "",
                    "language": self._language,
                },
                authenticated=False,
            )
            if not isinstance(payload, dict) or not payload.get("accessToken"):
                raise ChargebigAuthError("Login response did not contain an access token")
            tokens = Tokens(
                access_token=str(payload["accessToken"]),
                refresh_token=payload.get("refreshToken"),
            )
            self._set_tokens(tokens)
            return tokens

    async def async_get_account(self) -> Account:
        """Return the profile of the logged-in charger user."""
        payload = await self._request("GET", "/v1/charger-user/get-account")
        return Account.from_dict(payload if isinstance(payload, dict) else {})

    # -------------------------------------------------------------- charge point

    async def async_get_charge_point(self, code: str) -> ChargePointInfo:
        """Return live information about the charge point with the given code."""
        payload = await self._request(
            "GET",
            f"/v1/charge-point/info/{code}",
            params={"language": self._language.upper(), "includeRFIDs": "false"},
        )
        if not isinstance(payload, dict) or not payload.get("code"):
            raise ChargebigApiError(404, f"Unknown charge point {code}")
        return ChargePointInfo.from_dict(payload)

    async def async_get_payment_tokens(self) -> list[PaymentToken]:
        """Return the payment methods stored on the account."""
        payload = await self._request("GET", "/v1/payment-methods")
        if not isinstance(payload, dict):
            return []
        entries = payload.get("userPaymentTokenDto") or []
        tokens = (PaymentToken.from_dict(entry) for entry in entries if isinstance(entry, dict))
        return [token for token in tokens if token is not None]

    # ----------------------------------------------------------- charging process

    async def async_get_process(self, process_id: int, *, light: bool = True) -> ChargingProcess:
        """Return one charging session.

        The ``light`` variant is used for polling: the full endpoint repeats the
        client's complete terms of service on every call, which is ~17 kB per poll.
        """
        path = (
            f"/v1/charging-processes/light/{process_id}"
            if light
            else f"/v1/charging-processes/{process_id}"
        )
        payload = await self._request("GET", path)
        return ChargingProcess.from_dict(payload if isinstance(payload, dict) else {})

    async def async_get_active_processes(self) -> list[ChargingProcess]:
        """Return every charging session currently running on the account."""
        payload = await self._request("GET", "/v1/charging-processes/active")
        if not isinstance(payload, list):
            return []
        return [ChargingProcess.from_dict(item) for item in payload if isinstance(item, dict)]

    async def async_get_power_history(self, process_id: int) -> list[float]:
        """Return the watt samples the app plots for a running session."""
        payload = await self._request("GET", f"/v1/charging-processes/{process_id}/history")
        if not isinstance(payload, list):
            return []
        return [float(value) for value in payload if isinstance(value, (int, float))]

    # ------------------------------------------------------------------- actions

    async def async_start(
        self,
        code: str,
        *,
        payment_token: str,
        payment_method: str,
        tariff_id: int,
    ) -> None:
        """Start a charging session at the given charge point."""
        await self._request(
            "POST",
            f"/v1/charge-point/{code}/charge",
            json={
                "paymentMethod": payment_method,
                "paymentToken": payment_token,
                "voucherCode": None,
                "sessionId": None,
                "tariffId": tariff_id,
                "isGuest": False,
                "chargePointCode": code,
                "language": self._language,
            },
        )

    async def async_pause(self, process_id: int) -> None:
        """Pause a running charging session."""
        await self._request("POST", f"/v1/charging-processes/{process_id}/pause")

    async def async_resume(self, process_id: int) -> None:
        """Resume a paused charging session."""
        await self._request("POST", f"/v1/charging-processes/{process_id}/resume")
