"""Sensors for Wahoo Kickr Core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import UnitOfPower, UnitOfSpeed

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
    KickrSensorDescription(
        key="last_seen",
        name="Last Seen",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
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
    def native_value(self) -> Optional[float | datetime]:
        data = self.coordinator.data or {}
        value = data.get(self.entity_description.key)
        if value is None:
            return None
        if self.entity_description.key == "last_seen":
            if isinstance(value, datetime):
                return value
            return None
        return float(value)
