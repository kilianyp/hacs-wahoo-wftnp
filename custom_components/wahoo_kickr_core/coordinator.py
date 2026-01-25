"""Coordinator for Wahoo Kickr Core integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_ADDRESS, CONF_HOST, CONF_NAME, CONF_PORT
from .wftnp import (
    FTMSControlPointError,
    INDOOR_BIKE_DATA_UUID,
    WFTNPClient,
    WFTNPError,
    parse_indoor_bike_data,
)

_LOGGER = logging.getLogger(__name__)


class WahooKickrCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Handle connection and data for a single Kickr Core."""

    def __init__(self, hass: HomeAssistant, entry_data: Dict[str, Any]) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=entry_data.get(CONF_NAME),
            update_interval=timedelta(seconds=30),
        )
        self._host: str = entry_data[CONF_HOST]
        self._port: int = entry_data[CONF_PORT]
        self._address: str = entry_data.get(CONF_ADDRESS, "")

        self._client = WFTNPClient()
        self._lock = asyncio.Lock()
        self._connected = False
        self._unsub_poll = None
        self._reconnect_notice_sent = False
        self._last_reconnect_error = None

    @property
    def address(self) -> str:
        return self._address

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def async_setup(self) -> None:
        async def on_notify(char_uuid, value: bytes) -> None:
            if char_uuid == INDOOR_BIKE_DATA_UUID:
                data = parse_indoor_bike_data(value)
                if data:
                    updated = dict(self.data or {})
                    updated.update(data)
                    updated["last_seen"] = dt_util.utcnow().isoformat()
                    self.async_set_updated_data(updated)

        self._client.set_notification_callback(on_notify)
        try:
            await self._connect_and_init()
        except Exception as err:
            _LOGGER.warning("Initial connect failed; will retry in background: %s", err)
        if self._unsub_poll is None:
            self._unsub_poll = async_track_time_interval(
                self.hass, self._async_periodic_check, timedelta(seconds=10)
            )

    async def _async_periodic_check(self, _now) -> None:
        await self.async_request_refresh()

    async def _async_update_data(self) -> Dict[str, Any]:
        _LOGGER.debug(
            "Periodic check tick (connected=%s host=%s port=%s)",
            self._connected,
            self._host,
            self._port,
        )
        async with self._lock:
            if not self._connected:
                try:
                    if not self._reconnect_notice_sent:
                        _LOGGER.info("Kickr Core disconnected; attempting reconnect")
                        self._reconnect_notice_sent = True
                    await self._connect_and_init()
                except Exception as err:
                    if self._last_reconnect_error != str(err):
                        _LOGGER.warning("Kickr Core reconnect failed: %s", err)
                        self._last_reconnect_error = str(err)
                    raise UpdateFailed(f"Reconnect failed: {err}") from err
            else:
                try:
                    await asyncio.wait_for(self._client.discover_services(), timeout=3.0)
                except asyncio.TimeoutError:
                    if not self._reconnect_notice_sent:
                        _LOGGER.warning("Connection check timed out; reconnecting")
                        self._reconnect_notice_sent = True
                    self._connected = False
                    await self._client.close()
                    try:
                        if self._last_reconnect_error is None:
                            _LOGGER.info("Kickr Core reconnecting after timeout")
                        await self._connect_and_init()
                    except Exception as err2:
                        if self._last_reconnect_error != str(err2):
                            _LOGGER.warning("Kickr Core reconnect failed: %s", err2)
                            self._last_reconnect_error = str(err2)
                        raise UpdateFailed(f"Reconnect failed: {err2}") from err2
                except Exception as err:
                    if not self._reconnect_notice_sent:
                        _LOGGER.warning("Connection check failed; reconnecting: %s", err)
                        self._reconnect_notice_sent = True
                    self._connected = False
                    await self._client.close()
                    try:
                        if self._last_reconnect_error is None:
                            _LOGGER.info("Kickr Core reconnecting after failed check")
                        await self._connect_and_init()
                    except Exception as err2:
                        if self._last_reconnect_error != str(err2):
                            _LOGGER.warning("Kickr Core reconnect failed: %s", err2)
                            self._last_reconnect_error = str(err2)
                        raise UpdateFailed(f"Reconnect failed: {err2}") from err2

        return self.data or {}

    async def async_shutdown(self) -> None:
        if self._unsub_poll:
            self._unsub_poll()
            self._unsub_poll = None
        await self._client.close()
        self._connected = False

    async def _connect_and_init(self) -> None:
        try:
            if self._connected:
                await self._client.close()
                self._connected = False
            await self._client.connect(self._host, self._port)
            await self._client.ftms_init(subscribe_indoor_bike_data=True, subscribe_status=False)
            self._connected = True
            self._reconnect_notice_sent = False
            self._last_reconnect_error = None
        except Exception as err:  # broad to surface in config flow
            _LOGGER.error("Failed to connect to Kickr Core at %s:%s: %s", self._host, self._port, err)
            await self._client.close()
            self._connected = False
            raise

        try:
            await self._client.request_control()
            await self._client.start_training()
        except FTMSControlPointError as err:
            _LOGGER.warning("Control point refused training control: %s", err)
        except WFTNPError as err:
            _LOGGER.warning("Control point handshake failed: %s", err)

    async def async_set_erg_watts(self, watts: int) -> None:
        async with self._lock:
            await self._client.set_erg_watts(watts)

    async def async_set_grade(
        self,
        grade_percent: float,
        wind_mps: float = 0.0,
        crr: float = 0.0040,
        cw: float = 0.510,
    ) -> None:
        async with self._lock:
            await self._client.set_grade(
                grade_percent,
                wind_mps=wind_mps,
                crr=crr,
                cw=cw,
            )

    async def async_request_control(self) -> None:
        async with self._lock:
            await self._client.request_control()

    async def async_reset(self) -> None:
        async with self._lock:
            await self._client.reset()

    async def async_start_training(self) -> None:
        async with self._lock:
            await self._client.start_training()

    async def async_stop_training(self) -> None:
        async with self._lock:
            await self._client.stop_training()
