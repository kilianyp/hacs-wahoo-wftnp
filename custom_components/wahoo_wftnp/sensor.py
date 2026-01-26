"""Sensors for Wahoo Kickr Core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import UnitOfLength, UnitOfPower, UnitOfSpeed

from .const import DOMAIN
from .coordinator import WahooKickrCoordinator


@dataclass(frozen=True, kw_only=True)
class KickrSensorDescription(SensorEntityDescription):
    """Describe a Kickr sensor."""


SENSORS: tuple[KickrSensorDescription, ...] = (
    KickrSensorDescription(
        key="speed_kmh",
        name="Speed",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    KickrSensorDescription(
        key="cadence_rpm",
        name="Cadence",
        native_unit_of_measurement="rpm",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    KickrSensorDescription(
        key="power_w",
        name="Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    coordinator: WahooKickrCoordinator = hass.data[DOMAIN]["entries"][entry.entry_id]

    async_add_entities(
        KickrSensor(coordinator, entry, description) for description in SENSORS
    )


class KickrSensor(CoordinatorEntity[WahooKickrCoordinator], SensorEntity):
    """Representation of a Kickr sensor."""

    def __init__(
        self,
        coordinator: WahooKickrCoordinator,
        entry: ConfigEntry,
        description: KickrSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_name = f"{entry.title} {description.name}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Wahoo",
            model="KICKR CORE",
        )

    @property
    def native_value(self) -> Optional[float]:
        data = self.coordinator.data or {}
        value = data.get(self.entity_description.key)
        if value is None:
            return None
        return float(value)

    @property
    def extra_state_attributes(self) -> Dict[str, Any] | None:
        if not self.coordinator.data:
            return None
        last_seen = self.coordinator.data.get("last_seen")
        if not last_seen:
            return None
        return {"last_seen": last_seen}
