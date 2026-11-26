"""Config flow tests for Wahoo WFTNP."""

from __future__ import annotations

from ipaddress import ip_address
from unittest.mock import patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wahoo_wftnp.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    DOMAIN,
)

pytestmark = pytest.mark.asyncio

SERVICE_NAME = "KICKR CORE 4337._wahoo-fitness-tnp._tcp.local."
HOSTNAME = "KICKR-CORE-4337.local."
IP = "192.168.1.10"


def _discovery(ip: str = IP) -> ZeroconfServiceInfo:
    return ZeroconfServiceInfo(
        ip_address=ip_address(ip),
        ip_addresses=[ip_address(ip)],
        hostname=HOSTNAME,
        name=SERVICE_NAME,
        port=36866,
        type="_wahoo-fitness-tnp._tcp.local.",
        properties={},
    )


@pytest.fixture(autouse=True)
def _no_setup():
    with patch("custom_components.wahoo_wftnp.async_setup_entry", return_value=True):
        yield


async def _start_zeroconf(hass: HomeAssistant, ip: str = IP):
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_discovery(ip),
    )


async def test_zeroconf_asks_for_confirmation_and_name(hass: HomeAssistant) -> None:
    result = await _start_zeroconf(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Büro Trainer"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Büro Trainer"
    assert result["result"].unique_id == SERVICE_NAME
    assert result["data"] == {
        CONF_NAME: "Büro Trainer",
        CONF_HOST: IP,
        CONF_PORT: 36866,
    }


async def test_zeroconf_default_name_strips_service_type(hass: HomeAssistant) -> None:
    result = await _start_zeroconf(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["title"] == "KICKR CORE 4337"


@pytest.mark.parametrize("legacy_host", [IP, "kickr-core-4337.local"])
async def test_zeroconf_adopts_legacy_host_based_entry(
    hass: HomeAssistant, legacy_host: str
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=legacy_host,
        data={CONF_NAME: "Trainer", CONF_HOST: legacy_host, CONF_PORT: 36866},
    )
    entry.add_to_hass(hass)

    result = await _start_zeroconf(hass)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.unique_id == SERVICE_NAME
    assert entry.data[CONF_HOST] == legacy_host


async def test_zeroconf_updates_host_of_configured_entry(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=SERVICE_NAME,
        data={CONF_NAME: "Trainer", CONF_HOST: IP, CONF_PORT: 36866},
    )
    entry.add_to_hass(hass)

    result = await _start_zeroconf(hass, ip="192.168.1.20")

    assert result["type"] is FlowResultType.ABORT
    assert entry.data[CONF_HOST] == "192.168.1.20"


async def test_manual_setup_aborts_when_host_already_configured(
    hass: HomeAssistant,
) -> None:
    MockConfigEntry(
        domain=DOMAIN,
        unique_id=SERVICE_NAME,
        data={CONF_NAME: "Trainer", CONF_HOST: "KICKR-CORE-4337.local", CONF_PORT: 1},
    ).add_to_hass(hass)

    with patch(
        "custom_components.wahoo_wftnp.config_flow.WFTNPClient.discover",
        return_value={},
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["step_id"] == "manual"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "kickr-core-4337.local", CONF_PORT: 36866}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
