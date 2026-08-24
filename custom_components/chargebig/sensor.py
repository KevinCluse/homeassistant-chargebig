"""Sensor entities for the chargeBIG integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import ChargebigConfigEntry, ChargebigCoordinator, ChargebigData
from .entity import ChargebigEntity

# Every status the app has been observed to send, plus every value hassfest's
# "unknown states must be declared" check for enum sensors accepts as a fallback.
_STATUS_OPTIONS = ["charging", "paused_evse", "unknown"]


@dataclass(frozen=True, kw_only=True)
class ChargebigSensorDescription(SensorEntityDescription):
    """Describe one sensor and how to read it out of the coordinator's data."""

    value_fn: Callable[[ChargebigData], StateType | datetime]


def _status(data: ChargebigData) -> str:
    """Return the lower-cased session status, or the charge point status idle."""
    if data.process and data.process.status:
        return data.process.status.lower()
    return "unknown"


SENSOR_DESCRIPTIONS: tuple[ChargebigSensorDescription, ...] = (
    ChargebigSensorDescription(
        key="session_energy",
        translation_key="session_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda data: data.process.energy_kwh if data.process else None,
    ),
    ChargebigSensorDescription(
        key="power",
        translation_key="power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=lambda data: (
            round(data.process.power_kw * 1000)
            if data.process and data.process.power_kw is not None
            else None
        ),
    ),
    ChargebigSensorDescription(
        key="session_duration",
        translation_key="session_duration",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_registry_enabled_default=False,
        value_fn=lambda data: (
            data.process.duration.total_seconds()
            if data.process and data.process.duration
            else None
        ),
    ),
    ChargebigSensorDescription(
        key="session_start",
        translation_key="session_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.process.start_date if data.process else None,
    ),
    ChargebigSensorDescription(
        key="session_cost",
        translation_key="session_cost",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda data: (
            data.process.amount_cent / 100
            if data.process and data.process.amount_cent is not None
            else None
        ),
    ),
    ChargebigSensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=_STATUS_OPTIONS,
        value_fn=lambda data: _status(data) if _status(data) in _STATUS_OPTIONS else "unknown",
    ),
    ChargebigSensorDescription(
        key="charge_point_status",
        translation_key="charge_point_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.charge_point.charge_point_status,
    ),
    ChargebigSensorDescription(
        key="power_limit",
        translation_key="power_limit",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        value_fn=lambda data: data.process.power_limit_kw if data.process else None,
    ),
    ChargebigSensorDescription(
        key="price_per_kwh",
        translation_key="price_per_kwh",
        native_unit_of_measurement="ct/kWh",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        value_fn=lambda data: (
            (data.process.tariff.cents_per_kwh if data.process and data.process.tariff else None)
            or (
                data.charge_point.preferred_tariff().cents_per_kwh
                if data.charge_point.tariffs
                else None
            )
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChargebigConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the chargeBIG sensors for one charge point."""
    coordinator = entry.runtime_data
    async_add_entities(
        ChargebigSensor(coordinator, description) for description in SENSOR_DESCRIPTIONS
    )


class ChargebigSensor(ChargebigEntity, SensorEntity):
    """A single read-only value derived from the coordinator's data."""

    entity_description: ChargebigSensorDescription

    def __init__(
        self, coordinator: ChargebigCoordinator, description: ChargebigSensorDescription
    ) -> None:
        """Bind this sensor to its description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        """Return the sensor's current value."""
        if self._data is None:
            return None
        return self.entity_description.value_fn(self._data)
