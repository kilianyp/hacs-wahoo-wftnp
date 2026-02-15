"""Coordinator tests for Wahoo WFTNP."""

from __future__ import annotations

from unittest.mock import patch

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
