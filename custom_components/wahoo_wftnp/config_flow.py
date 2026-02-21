"""Config flow for Wahoo Kickr Core."""

from __future__ import annotations

import logging
from typing import Any, Dict

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_HOST,
    CONF_LAST_SEEN_INTERVAL,
    CONF_NAME,
    CONF_PORT,
    CONF_SLEEP_TIMEOUT,
    CONF_UPDATE_THROTTLE,
    DEFAULT_LAST_SEEN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SLEEP_TIMEOUT,
    DEFAULT_UPDATE_THROTTLE,
    DOMAIN,
)
from .wftnp import WFTNPClient

_LOGGER = logging.getLogger(__name__)


class WahooKickrConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Wahoo Kickr Core."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: Dict[str, Dict[str, Any]] = {}

    async def async_step_user(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            if user_input["device"] == "manual":
                return await self.async_step_manual()

            dev = self._discovered.get(user_input["device"])
            if not dev:
                return self.async_abort(reason="not_found")

            await self.async_set_unique_id(dev.get(CONF_HOST))
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=dev[CONF_NAME],
                data={
                    CONF_NAME: dev[CONF_NAME],
                    CONF_HOST: dev[CONF_HOST],
                    CONF_PORT: dev[CONF_PORT],
                },
            )

        await self._async_discover()

        if not self._discovered:
            return await self.async_step_manual()

        choices = {key: data[CONF_NAME] for key, data in self._discovered.items()}
        choices["manual"] = "Manual setup"

        schema = vol.Schema({vol.Required("device"): vol.In(choices)})
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return WahooKickrOptionsFlow(config_entry)

    async def async_step_manual(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        errors = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input.get(CONF_NAME) or user_input[CONF_HOST],
                data={
                    CONF_NAME: user_input.get(CONF_NAME) or user_input[CONF_HOST],
                    CONF_HOST: user_input[CONF_HOST],
                    CONF_PORT: user_input[CONF_PORT],
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_NAME): str,
            }
        )
        return self.async_show_form(step_id="manual", data_schema=schema, errors=errors)

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> FlowResult:
        host = discovery_info.host
        port = discovery_info.port or DEFAULT_PORT
        name = discovery_info.name or "Wahoo Kickr Core"

        await self.async_set_unique_id(host or name)
        self._abort_if_unique_id_configured()

        self.context["title_placeholders"] = {"name": name}

        return self.async_create_entry(
            title=name,
            data={
                CONF_NAME: name,
                CONF_HOST: host,
                CONF_PORT: port,
            },
        )

    async def _async_discover(self) -> None:
        self._discovered = {}
        try:
            devices = await WFTNPClient.discover(timeout=2.0)
        except Exception as err:
            _LOGGER.warning("Discovery failed: %s", err)
            return

        for dev in devices.values():
            key = dev.host or dev.name
            self._discovered[key] = {
                CONF_NAME: dev.name,
                CONF_HOST: dev.host,
                CONF_PORT: dev.port,
            }


class WahooKickrOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Wahoo Kickr Core."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SLEEP_TIMEOUT,
                    default=options.get(CONF_SLEEP_TIMEOUT, DEFAULT_SLEEP_TIMEOUT),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_LAST_SEEN_INTERVAL,
                    default=options.get(
                        CONF_LAST_SEEN_INTERVAL, DEFAULT_LAST_SEEN_INTERVAL
                    ),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_UPDATE_THROTTLE,
                    default=options.get(CONF_UPDATE_THROTTLE, DEFAULT_UPDATE_THROTTLE),
                ): vol.Coerce(int),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
