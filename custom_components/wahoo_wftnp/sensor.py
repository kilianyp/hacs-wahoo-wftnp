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
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import UnitOfPower, UnitOfSpeed
from homeassistant.util import slugify

from .const import CONF_NAME, DOMAIN
from .coordinator import WahooKickrCoordinator


@dataclass(frozen=True, kw_only=True)
class KickrSensorDescription(SensorEntityDescription):
    """Describe a Kickr sensor."""

    object_id_suffix: str


SENSORS: tuple[KickrSensorDescription, ...] = (
    KickrSensorDescription(
        key="speed_kmh",
        name="Speed",
        object_id_suffix="speed",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    KickrSensorDescription(
        key="cadence_rpm",
        name="Cadence",
        object_id_suffix="cadence",
        native_unit_of_measurement="rpm",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    KickrSensorDescription(
        key="power_w",
        name="Power",
        object_id_suffix="power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    KickrSensorDescription(
        key="last_seen",
        name="Last Seen",
        object_id_suffix="last_seen",
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
    entity_registry = er.async_get(hass)
    device_slug = slugify(entry.title or entry.data.get(CONF_NAME) or "wahoo")

    for description in SENSORS:
        unique_id = f"{entry.entry_id}_{description.key}"
        entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        if entity_id is None:
            continue

        desired_entity_id = f"sensor.{device_slug}_{description.object_id_suffix}"
        if entity_id == desired_entity_id:
            continue

        try:
            entity_registry.async_update_entity(
                entity_id, new_entity_id=desired_entity_id
            )
        except ValueError:
            # Leave the existing entity id unchanged if the target is taken.
            continue

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
        device_name = entry.title or entry.data.get(CONF_NAME) or "Wahoo"
        self._device_name = device_name
        self._entry_id = entry.entry_id
        self._attr_name = f"{device_name} {description.name}"
        device_slug = slugify(device_name)
        self._attr_suggested_object_id = f"{device_slug}_{description.object_id_suffix}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=self._device_name,
            manufacturer=self.coordinator.manufacturer,
            model=self.coordinator.model,
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
