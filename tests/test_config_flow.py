"""Tests for the Wahoo Kickr Core config flow."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.wahoo_wftnp import config_flow
from custom_components.wahoo_wftnp.const import (
    CONF_ADDRESS,
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    DOMAIN,
)
from custom_components.wahoo_wftnp.wftnp import DiscoveredDevice

pytestmark = pytest.mark.asyncio


@pytest.mark.usefixtures("hass")
async def test_user_flow_selects_discovered_device(hass) -> None:
    devices = {
        "dev1": DiscoveredDevice(
            name="KICKR CORE",
            host="kickr.local",
            address="192.168.1.10",
            port=36866,
            properties={},
        )
    }

    with patch.object(config_flow.WFTNPClient, "discover", return_value=devices):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"device": "192.168.1.10"}
    )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_HOST] == "192.168.1.10"
    assert result2["data"][CONF_PORT] == 36866
    assert result2["data"][CONF_NAME] == "KICKR CORE"


@pytest.mark.usefixtures("hass")
async def test_user_flow_manual(hass) -> None:
    with patch.object(config_flow.WFTNPClient, "discover", return_value={}):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "manual"

    user_input = {
        CONF_HOST: "10.0.0.5",
        CONF_PORT: 36866,
        CONF_NAME: "My Kickr",
        CONF_ADDRESS: "10.0.0.5",
    }

    result2 = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_HOST] == "10.0.0.5"
    assert result2["data"][CONF_PORT] == 36866
    assert result2["data"][CONF_NAME] == "My Kickr"
