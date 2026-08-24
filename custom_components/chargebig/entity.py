"""Common base entity for the chargeBIG integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ChargebigCoordinator, ChargebigData


class ChargebigEntity(CoordinatorEntity[ChargebigCoordinator]):
    """Base entity bound to one charge point's coordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ChargebigCoordinator, key: str) -> None:
        """Register the entity under a stable per-charge-point unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = self._build_device_info()

    def _build_device_info(self) -> DeviceInfo:
        """Describe the charge point as one Home Assistant device."""
        code = self.coordinator.code
        info = self.coordinator.data.charge_point if self.coordinator.data else None
        model = None
        if info and (info.plug_type or info.max_charging_power_watt):
            watt = f"{info.max_charging_power_watt:.0f} W" if info.max_charging_power_watt else None
            model = " / ".join(part for part in (info.plug_type, watt) if part)
        return DeviceInfo(
            identifiers={(DOMAIN, code)},
            name=(info.location_name if info and info.location_name else f"chargeBIG {code}"),
            manufacturer="chargeBIG",
            model=model,
            serial_number=info.hardware_id if info else None,
            configuration_url="https://app.carica.chargebig.com/",
        )

    @property
    def _data(self) -> ChargebigData | None:
        """Return the coordinator's latest poll result, if any."""
        return self.coordinator.data

    @property
    def available(self) -> bool:
        """An entity is unavailable once the last poll failed or returned nothing."""
        return super().available and self._data is not None
