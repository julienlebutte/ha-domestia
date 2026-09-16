"""Config flow for the Domestia integration.

Adding the integration only asks for the controller's IP -- relays are
auto-discovered. The Options flow (the integration's "Configure"
button in Settings > Devices & services) is where you rename a
specific relay or mark it non-dimmable / always-on, entirely from the
Home Assistant UI: no YAML involved.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_ALWAYS_ON,
    CONF_DIMMABLE,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    default_relay_name,
)
from .domestia_client import DomestiaClient

_LOGGER = logging.getLogger(__name__)


class DomestiaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup: just the controller's host/IP."""

    VERSION = 1

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        errors: Dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            client = DomestiaClient(host)
            try:
                relays = await self.hass.async_add_executor_job(client.discover_relays)
            except OSError:
                errors["base"] = "cannot_connect"
            else:
                if not relays:
                    errors["base"] = "no_relays"
                else:
                    await self.async_set_unique_id(host)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"Domestia ({host})",
                        data={CONF_HOST: host},
                        options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
                    )

        schema = vol.Schema({vol.Required(CONF_HOST): str})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "DomestiaOptionsFlow":
        return DomestiaOptionsFlow()


class DomestiaOptionsFlow(config_entries.OptionsFlow):
    """Rename relays and toggle dimmable/always_on, from the HA UI.

    Relay overrides are stored in the config entry's Options, keyed by
    the relay number as a string (e.g. options["1"] = {"name": ...}).
    A change here triggers a reload of the entry (see
    _async_update_listener in __init__.py), which rebuilds the light
    entities with the new settings.
    """

    def __init__(self) -> None:
        self._options: Dict[str, Any] = {}
        self._selected_relay: Optional[int] = None

    def _relays(self) -> List[int]:
        stored = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {})
        return stored.get("relays", [])

    def _relay_label(self, relay: int) -> str:
        override = self._options.get(str(relay), {})
        name = override.get(CONF_NAME) or default_relay_name(relay)
        return f"{relay} - {name}"

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        if not self._options:
            self._options = dict(self.config_entry.options)

        return self.async_show_menu(
            step_id="init",
            menu_options=["scan_interval", "select_relay", "finish"],
        )

    async def async_step_scan_interval(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        if user_input is not None:
            self._options[CONF_SCAN_INTERVAL] = user_input[CONF_SCAN_INTERVAL]
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self._options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(int, vol.Range(min=2, max=3600))
            }
        )
        return self.async_show_form(step_id="scan_interval", data_schema=schema)

    async def async_step_select_relay(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        relays = self._relays()
        if not relays:
            return self.async_abort(reason="no_relays")

        if user_input is not None:
            self._selected_relay = int(user_input["relay"])
            return await self.async_step_edit_relay()

        choices = {str(r): self._relay_label(r) for r in relays}
        schema = vol.Schema({vol.Required("relay"): vol.In(choices)})
        return self.async_show_form(step_id="select_relay", data_schema=schema)

    async def async_step_edit_relay(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        relay = self._selected_relay
        assert relay is not None
        current = self._options.get(str(relay), {})

        if user_input is not None:
            self._options[str(relay)] = {
                CONF_NAME: user_input[CONF_NAME],
                CONF_DIMMABLE: user_input[CONF_DIMMABLE],
                CONF_ALWAYS_ON: user_input[CONF_ALWAYS_ON],
            }
            # Loop back to the menu so several relays can be edited in
            # one visit to the Options screen.
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=current.get(CONF_NAME) or default_relay_name(relay)
                ): str,
                vol.Required(CONF_DIMMABLE, default=current.get(CONF_DIMMABLE, False)): bool,
                vol.Required(
                    CONF_ALWAYS_ON, default=current.get(CONF_ALWAYS_ON, False)
                ): bool,
            }
        )
        return self.async_show_form(
            step_id="edit_relay",
            data_schema=schema,
            description_placeholders={"relay": str(relay)},
        )

    async def async_step_finish(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        return self.async_create_entry(title="", data=self._options)
