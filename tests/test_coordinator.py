"""Coordinator tests for Wahoo WFTNP."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wahoo_wftnp.const import (
    CONF_ADDRESS,
    CONF_HOST,
    CONF_LAST_SEEN_INTERVAL,
    CONF_NAME,
    CONF_PORT,
    CONF_SLEEP_TIMEOUT,
    CONF_UPDATE_THROTTLE,
    DOMAIN,
)
from custom_components.wahoo_wftnp.coordinator import WahooKickrCoordinator

pytestmark = pytest.mark.asyncio


async def test_idle_packets_do_not_reset_activity_timer(hass: HomeAssistant) -> None:
    """Idle packets should eventually trigger sleep mode."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="KICKR CORE",
        data={
            CONF_HOST: "host.docker.internal",
            CONF_PORT: 36866,
            CONF_ADDRESS: "192.168.1.10",
            CONF_NAME: "KICKR CORE",
        },
        options={
            CONF_SLEEP_TIMEOUT: 10,
            CONF_LAST_SEEN_INTERVAL: 1,
            CONF_UPDATE_THROTTLE: 0,
        },
    )
    coordinator = WahooKickrCoordinator(hass, entry)
    coordinator._last_activity_monotonic = 0.0
    coordinator.async_set_updated_data(
        {
            "speed_kmh": 1.0,
            "cadence_rpm": 85.0,
            "power_w": 220.0,
        }
    )

    idle_packet = {"speed_kmh": 0.0, "cadence_rpm": 0.0, "power_w": 0.0}
    with patch(
        "custom_components.wahoo_wftnp.coordinator.time.monotonic",
        side_effect=[5.0, 9.0, 12.0],
    ):
        await coordinator._handle_indoor_bike_data(idle_packet)
        await coordinator._handle_indoor_bike_data(idle_packet)
        await coordinator._handle_indoor_bike_data(idle_packet)

    assert coordinator._last_activity_monotonic == 0.0
    assert coordinator._last_publish_monotonic == 9.0
    assert coordinator._last_seen_publish_monotonic == 12.0


async def test_manual_disconnect_sets_state_and_closes_client(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="KICKR CORE",
        data={
            CONF_HOST: "host.docker.internal",
            CONF_PORT: 36866,
            CONF_ADDRESS: "192.168.1.10",
            CONF_NAME: "KICKR CORE",
        },
        options={},
    )
    coordinator = WahooKickrCoordinator(hass, entry)
    coordinator._connected = True
    coordinator._client.close = AsyncMock()

    await coordinator.async_disconnect()

    coordinator._client.close.assert_awaited_once()
    assert coordinator.is_connected is False
    assert coordinator.is_manually_disconnected is True


async def test_manual_disconnect_skips_background_reconnect(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="KICKR CORE",
        data={
            CONF_HOST: "host.docker.internal",
            CONF_PORT: 36866,
            CONF_ADDRESS: "192.168.1.10",
            CONF_NAME: "KICKR CORE",
        },
        options={},
    )
    coordinator = WahooKickrCoordinator(hass, entry)
    coordinator._connected = False
    coordinator._manual_disconnect = True

    with patch.object(coordinator, "_attempt_reconnect", new=AsyncMock()) as reconnect:
        result = await coordinator._async_update_data()

    reconnect.assert_not_awaited()
    assert result == {}


async def test_manual_connect_reconnects_when_disconnected(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="KICKR CORE",
        data={
            CONF_HOST: "host.docker.internal",
            CONF_PORT: 36866,
            CONF_ADDRESS: "192.168.1.10",
            CONF_NAME: "KICKR CORE",
        },
        options={},
    )
    coordinator = WahooKickrCoordinator(hass, entry)
    coordinator._connected = False
    coordinator._manual_disconnect = True

    with patch.object(coordinator, "_connect_and_init", new=AsyncMock()) as connect_init:
        await coordinator.async_connect()

    connect_init.assert_awaited_once()
    assert coordinator.is_manually_disconnected is False


async def test_control_request_fails_when_manually_disconnected(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="KICKR CORE",
        data={
            CONF_HOST: "host.docker.internal",
            CONF_PORT: 36866,
            CONF_ADDRESS: "192.168.1.10",
            CONF_NAME: "KICKR CORE",
        },
        options={},
    )
    coordinator = WahooKickrCoordinator(hass, entry)
    coordinator._manual_disconnect = True
    coordinator._connected = False

    with pytest.raises(RuntimeError, match="manually disconnected"):
        await coordinator.async_request_control()
