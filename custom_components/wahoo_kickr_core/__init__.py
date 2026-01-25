"""Wahoo Kickr Core integration."""

from __future__ import annotations

import logging
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    SERVICE_REQUEST_CONTROL,
    SERVICE_RESET,
    SERVICE_SET_ERG_WATTS,
    SERVICE_SET_GRADE,
    SERVICE_START_TRAINING,
    SERVICE_STOP_TRAINING,
)
from .coordinator import WahooKickrCoordinator

PLATFORMS: list[str] = ["sensor"]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: Dict[str, Any]) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("entries", {})
    hass.data[DOMAIN].setdefault("services_registered", False)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = WahooKickrCoordinator(hass, entry.data)
    await coordinator.async_setup()
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.warning("Initial refresh failed; will retry in background: %s", err)

    hass.data[DOMAIN]["entries"][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not hass.data[DOMAIN]["services_registered"]:
        _register_services(hass)
        hass.data[DOMAIN]["services_registered"] = True

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    coordinator = hass.data[DOMAIN]["entries"].pop(entry.entry_id, None)
    if coordinator:
        await coordinator.async_shutdown()

    return unload_ok


def _register_services(hass: HomeAssistant) -> None:
    async def _get_coordinator(call: ServiceCall) -> WahooKickrCoordinator:
        entry_id = call.data.get("entry_id")
        entries = hass.data[DOMAIN]["entries"]
        if entry_id:
            coord = entries.get(entry_id)
            if not coord:
                raise HomeAssistantError(f"Unknown entry_id {entry_id}")
            return coord
        if len(entries) == 1:
            return next(iter(entries.values()))
        raise HomeAssistantError("Multiple Kickr Core entries loaded; pass entry_id")

    async def handle_set_erg(call: ServiceCall) -> None:
        coord = await _get_coordinator(call)
        watts = int(call.data["watts"])
        await coord.async_set_erg_watts(watts)

    async def handle_set_grade(call: ServiceCall) -> None:
        coord = await _get_coordinator(call)
        await coord.async_set_grade(
            grade_percent=float(call.data["grade_percent"]),
            wind_mps=float(call.data.get("wind_mps", 0.0)),
            crr=float(call.data.get("crr", 0.0040)),
            cw=float(call.data.get("cw", 0.510)),
        )

    async def handle_request_control(call: ServiceCall) -> None:
        coord = await _get_coordinator(call)
        await coord.async_request_control()

    async def handle_reset(call: ServiceCall) -> None:
        coord = await _get_coordinator(call)
        await coord.async_reset()

    async def handle_start_training(call: ServiceCall) -> None:
        coord = await _get_coordinator(call)
        await coord.async_start_training()

    async def handle_stop_training(call: ServiceCall) -> None:
        coord = await _get_coordinator(call)
        await coord.async_stop_training()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_ERG_WATTS,
        handle_set_erg,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_GRADE,
        handle_set_grade,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REQUEST_CONTROL,
        handle_request_control,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET,
        handle_reset,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_START_TRAINING,
        handle_start_training,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_TRAINING,
        handle_stop_training,
    )
