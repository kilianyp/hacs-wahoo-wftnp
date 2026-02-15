"""Coordinator for Wahoo Kickr Core integration."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ADDRESS,
    CONF_HOST,
    CONF_LAST_SEEN_INTERVAL,
    CONF_NAME,
    CONF_PORT,
    CONF_SLEEP_TIMEOUT,
    CONF_UPDATE_THROTTLE,
    DEFAULT_LAST_SEEN_INTERVAL,
    DEFAULT_SLEEP_TIMEOUT,
    DEFAULT_UPDATE_THROTTLE,
)
from .wftnp import (
    FTMSControlPointError,
    INDOOR_BIKE_DATA_UUID,
    WFTNPClient,
    WFTNPError,
    parse_indoor_bike_data,
)

_LOGGER = logging.getLogger(__name__)


def _has_activity(data: Dict[str, Any]) -> bool:
    for key in ("speed_kmh", "cadence_rpm", "power_w"):
        value = data.get(key)
        if value is None:
            continue
        try:
            if float(value) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


class WahooKickrCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Handle connection and data for a single Kickr Core."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        entry_data = entry.data
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
        self._sleep_timeout = float(
            entry.options.get(CONF_SLEEP_TIMEOUT, DEFAULT_SLEEP_TIMEOUT)
        )
        self._last_seen_interval = float(
            entry.options.get(CONF_LAST_SEEN_INTERVAL, DEFAULT_LAST_SEEN_INTERVAL)
        )
        self._update_throttle = float(
            entry.options.get(CONF_UPDATE_THROTTLE, DEFAULT_UPDATE_THROTTLE)
        )
        self._last_activity_monotonic = time.monotonic()
        self._last_publish_monotonic = 0.0
        self._last_seen_publish_monotonic = 0.0

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
                    await self._handle_indoor_bike_data(data)

        self._client.set_notification_callback(on_notify)
        try:
            await self._connect_and_init()
        except Exception as err:
            _LOGGER.warning("Initial connect failed; will retry in background: %s", err)
        if self._unsub_poll is None:
            self._unsub_poll = async_track_time_interval(
                self.hass, self._async_periodic_check, timedelta(seconds=10)
            )

    async def _handle_indoor_bike_data(self, data: Dict[str, Any]) -> None:
        now = time.monotonic()
        has_activity = _has_activity(data)

        if not has_activity and self._is_sleeping(now, self._last_activity_monotonic):
            self._maybe_publish_last_seen(now)
            return

        if has_activity:
            self._last_activity_monotonic = now

        self._publish_active(data, now)

    def _is_sleeping(self, now: float, last_activity_monotonic: float) -> bool:
        if self._sleep_timeout <= 0:
            return False
        return (now - last_activity_monotonic) >= self._sleep_timeout

    def _maybe_publish_last_seen(self, now: float) -> None:
        if (now - self._last_seen_publish_monotonic) < self._last_seen_interval:
            return
        self._last_seen_publish_monotonic = now
        updated = dict(self.data or {})
        updated["last_seen"] = dt_util.utcnow()
        self.async_set_updated_data(updated)

    def _publish_active(self, data: Dict[str, Any], now: float) -> None:
        updated = dict(self.data or {})
        updated.update(data)
        updated["last_seen"] = dt_util.utcnow()

        if self._update_throttle and (
            now - self._last_publish_monotonic
        ) < self._update_throttle:
            return

        self._last_publish_monotonic = now
        self._last_seen_publish_monotonic = now
        self.async_set_updated_data(updated)

    async def _async_periodic_check(self, _now) -> None:
        await self.async_request_refresh()

    async def _async_update_data(self) -> Dict[str, Any]:
        """Update data and maintain connection health."""
        _LOGGER.debug(
            "Periodic check tick (connected=%s host=%s port=%s)",
            self._connected,
            self._host,
            self._port,
        )
        async with self._lock:
            if not self._connected:
                await self._attempt_reconnect("Kickr Core disconnected; attempting reconnect")
            else:
                await self._verify_connection()

        return self.data or {}

    async def _verify_connection(self) -> None:
        """Verify connection is alive and reconnect if needed."""
        try:
            await asyncio.wait_for(self._client.discover_services(), timeout=3.0)
        except asyncio.TimeoutError:
            _LOGGER.warning("Connection check timed out; reconnecting")
            self._connected = False
            await self._client.close()
            await self._attempt_reconnect()
        except Exception as err:
            _LOGGER.warning("Connection check failed; reconnecting: %s", err)
            self._connected = False
            await self._client.close()
            await self._attempt_reconnect()

    async def _attempt_reconnect(self, info_message: str = None) -> None:
        """Attempt to reconnect and raise UpdateFailed on error."""
        if info_message and not self._reconnect_notice_sent:
            _LOGGER.info(info_message)
            self._reconnect_notice_sent = True
        
        try:
            await self._connect_and_init()
        except Exception as err:
            _LOGGER.warning("Kickr Core reconnect failed: %s", err)
            raise UpdateFailed(f"Reconnect failed: {err}") from err

    async def _ensure_control(self) -> None:
        """Ensure we have control of the trainer. Request it if needed."""
        if self._has_control:
            return
        
        _LOGGER.info("Requesting control of trainer")
        try:
            await self._client.request_control()
            await self._client.start_training()
            self._has_control = True
            _LOGGER.info("Successfully acquired control of trainer")
        except FTMSControlPointError as err:
            _LOGGER.error("Control point refused training control: %s", err)
            raise RuntimeError(f"Failed to acquire control: {err}") from err
        except WFTNPError as err:
            _LOGGER.error("Control point handshake failed: %s", err)
            raise RuntimeError(f"Failed to acquire control: {err}") from err

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
            _LOGGER.info("Connected in monitoring mode - control will be requested when needed")
            self._has_control = False
        except Exception as err:  # broad to surface in config flow
            _LOGGER.warning(
                "Failed to connect to Kickr Core at %s:%s: %s",
                self._host,
                self._port,
                err,
            )
            await self._client.close()
            self._connected = False
            raise

    async def async_set_erg_watts(self, watts: int) -> None:
        async with self._lock:
            await self._ensure_control()
            await self._client.set_erg_watts(watts)

    async def async_set_grade(
        self,
        grade_percent: float,
        wind_mps: float = 0.0,
        crr: float = 0.0040,
        cw: float = 0.510,
    ) -> None:
        async with self._lock:
            await self._ensure_control()
            await self._client.set_grade(
                grade_percent,
                wind_mps=wind_mps,
                crr=crr,
                cw=cw,
            )

    async def async_request_control(self) -> None:
        async with self._lock:
            await self._ensure_control()

    async def async_reset(self) -> None:
        async with self._lock:
            await self._ensure_control()
            await self._client.reset()

    async def async_start_training(self) -> None:
        async with self._lock:
            await self._ensure_control()

    async def async_stop_training(self) -> None:
        async with self._lock:
            await self._ensure_control()
            await self._client.stop_training()
