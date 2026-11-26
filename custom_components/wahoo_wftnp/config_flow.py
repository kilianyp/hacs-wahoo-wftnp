"""Config flow for Wahoo Kickr Core."""

from __future__ import annotations

import logging
from typing import Any, Dict

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.data_entry_flow import AbortFlow, FlowResult

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


def _friendly_name(service_name: str) -> str:
    """Strip the mDNS service type, e.g. "KICKR CORE 1234._wahoo-fitness-tnp..."."""
    return service_name.split("._", 1)[0].strip()


def _normalize_host(host: str) -> str:
    return host.rstrip(".").lower()


class WahooKickrConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Wahoo Kickr Core."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: Dict[str, Dict[str, Any]] = {}
        self._zeroconf_device: Dict[str, Any] = {}

    async def async_step_user(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            if user_input["device"] == "manual":
                return await self.async_step_manual()

            dev = self._discovered.get(user_input["device"])
            if not dev:
                return self.async_abort(reason="not_found")

            await self.async_set_unique_id(user_input["device"])
            self._abort_if_unique_id_configured()
            self._abort_if_host_configured(dev[CONF_HOST])

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
            self._abort_if_host_configured(user_input[CONF_HOST])

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
        service_name = discovery_info.name or ""
        hostname = getattr(discovery_info, "hostname", None) or ""
        unique_id = service_name or host

        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})

        # Entries created before 0.4.1 used the host (IP or mDNS hostname) as
        # unique_id, so discovery could not match them and created a duplicate.
        # Adopt such an entry instead of offering the trainer a second time.
        if entry := self._find_entry_by_host(host, hostname):
            self.hass.config_entries.async_update_entry(entry, unique_id=unique_id)
            return self.async_abort(reason="already_configured")

        name = _friendly_name(service_name) or "Wahoo Kickr Core"
        self._zeroconf_device = {CONF_NAME: name, CONF_HOST: host, CONF_PORT: port}
        self.context["title_placeholders"] = {"name": name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        device = self._zeroconf_device
        if user_input is not None:
            name = user_input.get(CONF_NAME) or device[CONF_NAME]
            return self.async_create_entry(
                title=name,
                data={**device, CONF_NAME: name},
            )

        schema = vol.Schema({vol.Optional(CONF_NAME, default=device[CONF_NAME]): str})
        return self.async_show_form(
            step_id="zeroconf_confirm",
            data_schema=schema,
            description_placeholders={"name": device[CONF_NAME]},
        )

    def _find_entry_by_host(self, *hosts: str) -> config_entries.ConfigEntry | None:
        candidates = {_normalize_host(host) for host in hosts if host}
        for entry in self._async_current_entries(include_ignore=False):
            known = {
                _normalize_host(entry.unique_id or ""),
                _normalize_host(str(entry.data.get(CONF_HOST, ""))),
            }
            if candidates & known:
                return entry
        return None

    def _abort_if_host_configured(self, host: str) -> None:
        if self._find_entry_by_host(host):
            raise AbortFlow("already_configured")

    async def _async_discover(self) -> None:
        self._discovered = {}
        try:
            devices = await WFTNPClient.discover(timeout=2.0)
        except Exception as err:
            _LOGGER.warning("Discovery failed: %s", err)
            return

        configured = self._async_current_ids()
        for dev in devices.values():
            key = dev.name or dev.host
            if key in configured or self._find_entry_by_host(dev.host):
                continue
            self._discovered[key] = {
                CONF_NAME: _friendly_name(dev.name) or dev.host,
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
