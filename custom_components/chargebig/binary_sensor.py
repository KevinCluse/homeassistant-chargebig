"""Binary sensor entities for the chargeBIG integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ChargebigConfigEntry, ChargebigCoordinator, ChargebigData
from .entity import ChargebigEntity


@dataclass(frozen=True, kw_only=True)
class ChargebigBinarySensorDescription(BinarySensorEntityDescription):
    """Describe one binary sensor and how to read it out of the coordinator's data."""

    value_fn: Callable[[ChargebigData], bool | None]


BINARY_SENSOR_DESCRIPTIONS: tuple[ChargebigBinarySensorDescription, ...] = (
    ChargebigBinarySensorDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.charge_point.is_online,
    ),
    ChargebigBinarySensorDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda data: data.is_charging,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChargebigConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the chargeBIG binary sensors for one charge point."""
    coordinator = entry.runtime_data
    async_add_entities(
        ChargebigBinarySensor(coordinator, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class ChargebigBinarySensor(ChargebigEntity, BinarySensorEntity):
    """A single on/off value derived from the coordinator's data."""

    entity_description: ChargebigBinarySensorDescription

    def __init__(
        self,
        coordinator: ChargebigCoordinator,
        description: ChargebigBinarySensorDescription,
    ) -> None:
        """Bind this binary sensor to its description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the current on/off state."""
        if self._data is None:
            return None
        return self.entity_description.value_fn(self._data)
