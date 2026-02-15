"""Integration tests for Wahoo WFTNP."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wahoo_wftnp.const import DOMAIN

pytestmark = pytest.mark.asyncio


async def _setup_entry(
    hass: HomeAssistant,
    *,
    title: str = "KICKR CORE",
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=title,
        data={
            "host": "host.docker.internal",
            "port": 36866,
            "address": "192.168.1.10",
            "name": title,
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.connect",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.ftms_init",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.request_control",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.start_training",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.discover_services",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.read_device_information",
            new=AsyncMock(return_value=(None, None)),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


async def test_setup_creates_entities_and_device(hass: HomeAssistant) -> None:
    entry = await _setup_entry(hass)

    device_reg = dr.async_get(hass)
    device = device_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None
    assert device.name == "KICKR CORE"

    entity_reg = er.async_get(hass)
    speed_entity_id = entity_reg.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_speed_kmh"
    )
    cadence_entity_id = entity_reg.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_cadence_rpm"
    )
    power_entity_id = entity_reg.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_power_w"
    )
    last_seen_entity_id = entity_reg.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_last_seen"
    )

    assert speed_entity_id is not None
    assert cadence_entity_id is not None
    assert power_entity_id is not None
    assert last_seen_entity_id is not None

    state = hass.states.get(speed_entity_id)
    assert state is not None
    assert state.state in (STATE_UNAVAILABLE, "unknown")
    assert state.attributes.get("friendly_name") == "KICKR CORE Speed"


async def test_device_registry_uses_hardware_metadata(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="KICKR CORE",
        data={
            "host": "host.docker.internal",
            "port": 36866,
            "address": "192.168.1.10",
            "name": "KICKR CORE",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.connect",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.ftms_init",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.request_control",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.start_training",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.discover_services",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.read_device_information",
            new=AsyncMock(return_value=("Wahoo Fitness", "KICKR CORE v2")),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    device_reg = dr.async_get(hass)
    device = device_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None
    assert device.manufacturer == "Wahoo Fitness"
    assert device.model == "KICKR CORE v2"


async def test_entity_ids_use_device_name_and_metric_suffix(
    hass: HomeAssistant,
) -> None:
    entry = await _setup_entry(hass)

    entity_reg = er.async_get(hass)
    speed_entity_id = entity_reg.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_speed_kmh"
    )
    cadence_entity_id = entity_reg.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_cadence_rpm"
    )
    power_entity_id = entity_reg.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_power_w"
    )

    assert speed_entity_id == "sensor.kickr_core_speed"
    assert cadence_entity_id == "sensor.kickr_core_cadence"
    assert power_entity_id == "sensor.kickr_core_power"


async def test_entity_name_uses_metric_and_friendly_name_uses_device(
    hass: HomeAssistant,
) -> None:
    entry = await _setup_entry(hass, title="My Trainer")

    entity_reg = er.async_get(hass)
    cadence_entity_id = entity_reg.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_cadence_rpm"
    )
    assert cadence_entity_id == "sensor.my_trainer_cadence"

    entity_entry = entity_reg.async_get(cadence_entity_id)
    assert entity_entry is not None
    assert entity_entry.original_name == "Cadence"

    state = hass.states.get(cadence_entity_id)
    assert state is not None
    assert state.attributes.get("friendly_name") == "My Trainer Cadence"


async def test_existing_short_entity_id_is_migrated_to_device_prefixed_id(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="KICKR CORE",
        data={
            "host": "host.docker.internal",
            "port": 36866,
            "address": "192.168.1.10",
            "name": "KICKR CORE",
        },
    )
    entry.add_to_hass(hass)

    entity_reg = er.async_get(hass)
    entity_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_cadence_rpm",
        suggested_object_id="cadence",
        config_entry=entry,
    )

    with (
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.connect",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.ftms_init",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.request_control",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.start_training",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.discover_services",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.read_device_information",
            new=AsyncMock(return_value=(None, None)),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    migrated_entity_id = entity_reg.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_cadence_rpm"
    )
    assert migrated_entity_id == "sensor.kickr_core_cadence"


async def test_services_call_client_methods(hass: HomeAssistant) -> None:
    entry = await _setup_entry(hass)

    with (
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.request_control",
            new=AsyncMock(),
        ) as request_control,
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.start_training",
            new=AsyncMock(),
        ) as start_training,
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.set_erg_watts",
            new=AsyncMock(),
        ) as set_erg,
        patch(
            "custom_components.wahoo_wftnp.coordinator.WFTNPClient.set_grade",
            new=AsyncMock(),
        ) as set_grade,
    ):
        await hass.services.async_call(
            DOMAIN,
            "set_erg_watts",
            {"entry_id": entry.entry_id, "watts": 200},
            blocking=True,
        )
        set_erg.assert_awaited_once()

        await hass.services.async_call(
            DOMAIN,
            "set_grade",
            {"entry_id": entry.entry_id, "grade_percent": 3.5},
            blocking=True,
        )
        set_grade.assert_awaited_once()
        request_control.assert_awaited_once()
        start_training.assert_awaited_once()


async def test_config_entry_state(hass: HomeAssistant) -> None:
    entry = await _setup_entry(hass)
    assert entry.state == ConfigEntryState.LOADED

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state == ConfigEntryState.NOT_LOADED
