"""Config flow tests for Wahoo WFTNP."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.wahoo_wftnp.config_flow import (
    WahooKickrConfigFlow,
)
from custom_components.wahoo_wftnp.const import (
    CONF_ADDRESS,
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
)

pytestmark = pytest.mark.asyncio


async def test_zeroconf_step_uses_current_host_and_addresses_fields() -> None:
    flow = WahooKickrConfigFlow()
    flow.context = {}
    flow.async_set_unique_id = AsyncMock()  # type: ignore[method-assign]
    flow._abort_if_unique_id_configured = Mock()  # type: ignore[method-assign]

    result = await flow.async_step_zeroconf(
        SimpleNamespace(
            host="192.168.1.10",
            addresses=["192.168.1.10"],
            port=36866,
            name="KICKR CORE",
        )
    )

    flow.async_set_unique_id.assert_awaited_once_with("192.168.1.10")
    flow._abort_if_unique_id_configured.assert_called_once()

    assert result["type"] == "create_entry"
    assert result["title"] == "KICKR CORE"
    assert result["data"] == {
        CONF_NAME: "KICKR CORE",
        CONF_HOST: "192.168.1.10",
        CONF_ADDRESS: "192.168.1.10",
        CONF_PORT: 36866,
    }


async def test_zeroconf_unique_id_falls_back_to_name_when_host_missing() -> None:
    flow = WahooKickrConfigFlow()
    flow.context = {}
    flow.async_set_unique_id = AsyncMock()  # type: ignore[method-assign]
    flow._abort_if_unique_id_configured = Mock()  # type: ignore[method-assign]

    result = await flow.async_step_zeroconf(
        SimpleNamespace(
            host="",
            addresses=[],
            port=36866,
            name="KICKR CORE",
        )
    )

    flow.async_set_unique_id.assert_awaited_once_with("KICKR CORE")
    assert result["data"][CONF_HOST] == ""
