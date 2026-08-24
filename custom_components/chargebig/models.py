"""Typed models for the chargeBIG API responses.

The API is undocumented, so every model is deliberately tolerant: unknown fields are
ignored and missing fields fall back to ``None`` instead of raising. Only the handful of
fields the integration actually renders are promoted to attributes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .const import PAUSED_STATUS_PREFIXES, STATUS_CHARGING

#: ``PT3H47M23.455350362S`` and friends. The backend emits java.time.Duration.toString().
_ISO_DURATION = re.compile(
    r"^(?P<sign>-)?P"
    r"(?:(?P<days>\d+(?:\.\d+)?)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?"
    r")?$"
)


def parse_iso_duration(value: Any) -> timedelta | None:
    """Parse an ISO-8601 duration such as ``PT3H47M23.455S`` into a timedelta."""
    if isinstance(value, (int, float)):
        return timedelta(seconds=float(value))
    if not isinstance(value, str) or not (match := _ISO_DURATION.match(value.strip())):
        return None
    parts = match.groupdict()
    if not any(parts[key] for key in ("days", "hours", "minutes", "seconds")):
        return timedelta(0)
    delta = timedelta(
        days=float(parts["days"] or 0),
        hours=float(parts["hours"] or 0),
        minutes=float(parts["minutes"] or 0),
        seconds=float(parts["seconds"] or 0),
    )
    return -delta if parts["sign"] else delta


def parse_api_datetime(value: Any) -> datetime | None:
    """Parse a backend timestamp.

    The backend emits timestamps without an offset (``2026-08-24T17:52:31.938545``).
    They are UTC: a server-generated error payload carried exactly the same wall clock
    time as the ``Date`` header of the very same response, which is GMT by definition.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _as_float(value: Any) -> float | None:
    """Return ``value`` as float, or ``None`` if it is not numeric."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    """Return ``value`` as int, or ``None`` if it is not numeric."""
    number = _as_float(value)
    return None if number is None else int(number)


@dataclass(frozen=True, slots=True)
class Tokens:
    """A pair of JWTs as handed out by the login endpoint."""

    access_token: str
    refresh_token: str | None = None


@dataclass(frozen=True, slots=True)
class Account:
    """The logged-in charger user."""

    id: int | None
    name: str | None
    email: str | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Account:
        """Build an account from a ``/v1/charger-user/get-account`` payload."""
        return cls(
            id=_as_int(data.get("id")),
            name=data.get("name"),
            email=data.get("email"),
        )


@dataclass(frozen=True, slots=True)
class Tariff:
    """One tariff offered at a charge point."""

    id: int | None
    name: str | None
    cents_per_kwh: float | None
    base_fee_cents: float | None
    priority: int | None
    payment_methods: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Tariff:
        """Build a tariff from a nested ``tariff``/``tariffs[]`` payload."""
        methods = data.get("paymentMethods")
        return cls(
            id=_as_int(data.get("id")),
            name=data.get("name"),
            cents_per_kwh=_as_float(data.get("centsPerKwh")),
            base_fee_cents=_as_float(data.get("baseFeeCents")),
            priority=_as_int(data.get("priority")),
            payment_methods=tuple(methods) if isinstance(methods, list) else (),
        )


@dataclass(frozen=True, slots=True)
class PaymentToken:
    """A stored payment method of the account."""

    token: str
    payment_method: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PaymentToken | None:
        """Build a payment token, or ``None`` if the entry is unusable."""
        token = data.get("token")
        method = data.get("paymentMethod")
        if not token or not method:
            return None
        return cls(token=str(token), payment_method=str(method))


@dataclass(frozen=True, slots=True)
class ChargePointInfo:
    """A charge point as returned by ``/v1/charge-point/info/{code}``."""

    code: str
    hardware_id: str | None = None
    charging_process_id: int | None = None
    plug_type: str | None = None
    max_charging_power_watt: float | None = None
    charge_point_status: str | None = None
    cabinet_status: str | None = None
    is_online: bool = False
    emergency_error: bool = False
    location_name: str | None = None
    location_id: int | None = None
    region: str | None = None
    currency: str | None = None
    blocked_amount: float | None = None
    payment_methods: tuple[str, ...] = ()
    tariffs: tuple[Tariff, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChargePointInfo:
        """Build a charge point from a ``/v1/charge-point/info/{code}`` payload."""
        location = data.get("location") or {}
        tariffs = data.get("tariffs")
        methods = data.get("paymentMethods")
        # The backend uses 0 as well as null to mean "no session running".
        process_id = _as_int(data.get("chargingProcessId")) or None
        return cls(
            code=str(data.get("code") or ""),
            hardware_id=data.get("hardwareId") or None,
            charging_process_id=process_id,
            plug_type=data.get("plugType"),
            max_charging_power_watt=_as_float(data.get("maxChargingPowerWatt")),
            charge_point_status=data.get("chargePointStatus"),
            cabinet_status=data.get("cabinetStatus"),
            is_online=bool(data.get("isOnline")),
            emergency_error=bool(data.get("emergencyError")),
            location_name=location.get("name"),
            location_id=_as_int(location.get("id")),
            region=data.get("region"),
            currency=location.get("currency"),
            blocked_amount=_as_float(data.get("blockedAmount")),
            payment_methods=tuple(methods) if isinstance(methods, list) else (),
            tariffs=tuple(Tariff.from_dict(item) for item in tariffs)
            if isinstance(tariffs, list)
            else (),
            raw=data,
        )

    def preferred_tariff(self, tariff_id: int | None = None) -> Tariff | None:
        """Return the tariff to charge on.

        ``tariff_id`` wins if it exists at this charge point; otherwise the tariff with
        the lowest ``priority`` is used, which is the order the web app displays them in.
        """
        if not self.tariffs:
            return None
        if tariff_id is not None:
            for tariff in self.tariffs:
                if tariff.id == tariff_id:
                    return tariff
        return min(self.tariffs, key=lambda t: (t.priority is None, t.priority or 0))


@dataclass(frozen=True, slots=True)
class ChargingProcess:
    """A charging session as returned by ``/v1/charging-processes/[light/]{id}``."""

    id: int | None
    charge_point_code: str | None = None
    status: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    duration: timedelta | None = None
    energy_kwh: float | None = None
    power_kw: float | None = None
    amount_cent: float | None = None
    power_limit_kw: float | None = None
    energy_limit_wh: float | None = None
    derating_index: float | None = None
    error_code: int | None = None
    payment_method: str | None = None
    tariff: Tariff | None = None
    invoice_available: bool = False
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChargingProcess:
        """Build a session from a charging-process payload (light or full)."""
        process = data.get("chargingProcessDto") or {}
        tariff = process.get("tariff")
        return cls(
            id=_as_int(process.get("id")),
            charge_point_code=data.get("chargePointCode"),
            status=process.get("chargingStatus"),
            start_date=parse_api_datetime(process.get("startDate")),
            end_date=parse_api_datetime(process.get("endDate")),
            duration=parse_iso_duration(process.get("duration")),
            energy_kwh=_as_float(process.get("chargedAmountCorrectedKWh")),
            power_kw=_as_float(process.get("chargingActivePowerKW")),
            amount_cent=_as_float(process.get("amountCent")),
            power_limit_kw=_as_float(data.get("powerLimitKW")),
            energy_limit_wh=_as_float(data.get("energyLimitWh")),
            derating_index=_as_float(data.get("deratingIndex")),
            error_code=_as_int(process.get("errorCode")),
            payment_method=process.get("paymentMethod"),
            tariff=Tariff.from_dict(tariff) if isinstance(tariff, dict) else None,
            invoice_available=bool(process.get("invoiceAvailable")),
            raw=data,
        )

    @property
    def is_charging(self) -> bool:
        """Return True while energy is flowing."""
        return self.status == STATUS_CHARGING

    @property
    def is_paused(self) -> bool:
        """Return True for a session that exists but is halted."""
        return bool(self.status) and self.status.upper().startswith(PAUSED_STATUS_PREFIXES)

    @property
    def is_finished(self) -> bool:
        """Return True once the backend has closed the session."""
        return self.end_date is not None
