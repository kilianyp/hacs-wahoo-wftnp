"""Switches for Wahoo Kickr Core."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import CONF_NAME, DOMAIN
from .coordinator import WahooKickrCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    coordinator: WahooKickrCoordinator = hass.data[DOMAIN]["entries"][entry.entry_id]
    async_add_entities([KickrConnectionSwitch(coordinator, entry)])


class KickrConnectionSwitch(CoordinatorEntity[WahooKickrCoordinator], SwitchEntity):
    """Switch to connect/disconnect from the trainer."""

    def __init__(self, coordinator: WahooKickrCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        device_name = entry.title or entry.data.get(CONF_NAME) or "Wahoo"
        self._device_name = device_name
        self._entry_id = entry.entry_id
        self._attr_has_entity_name = True
        self._attr_name = "Connection"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_unique_id = f"{entry.entry_id}_connection"
        self._attr_suggested_object_id = f"{slugify(device_name)}_connection"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=self._device_name,
            manufacturer=self.coordinator.manufacturer,
            model=self.coordinator.model,
        )

    @property
    def is_on(self) -> bool:
        return not self.coordinator.is_manually_disconnected

    @property
    def available(self) -> bool:
        return True

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_connect()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_disconnect()
