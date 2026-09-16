"""The Domestia integration.

Talks directly to a Domestia DMC-008 controller over TCP -- no MQTT
broker and no separate bridge process, unlike the original
go-domestia project this was ported from.

Set up entirely from the Home Assistant UI: Settings > Devices &
services > Add integration > Domestia, enter the controller's IP.
Relays are auto-discovered; use the integration's "Configure" button
afterwards to rename a relay or mark it non-dimmable / always-on.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_ALWAYS_ON,
    CONF_DIMMABLE,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    default_relay_name,
)
from .coordinator import DomestiaCoordinator
from .domestia_client import DomestiaClient, LightConfig

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.LIGHT]

# Options keys that aren't a relay override (relay overrides are keyed by
# the relay number as a string, e.g. options["1"] = {...}).
_NON_RELAY_OPTION_KEYS = {CONF_SCAN_INTERVAL}


def _build_light_configs(
    discovered_relays: List[int], options: Dict[str, Any]
) -> List[LightConfig]:
    """Merge discovered relays with any per-relay overrides from Options."""
    return [
        LightConfig(
            name=options.get(str(relay), {}).get(CONF_NAME) or default_relay_name(relay),
            relay=relay,
            dimmable=options.get(str(relay), {}).get(CONF_DIMMABLE, False),
            always_on=options.get(str(relay), {}).get(CONF_ALWAYS_ON, False),
        )
        for relay in discovered_relays
    ]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Domestia from a config entry."""
    host = entry.data[CONF_HOST]
    client = DomestiaClient(host)

    try:
        discovered_relays = await hass.async_add_executor_job(client.discover_relays)
    except OSError as err:
        raise ConfigEntryNotReady(
            f"Cannot reach Domestia controller at {host}: {err}"
        ) from err

    if not discovered_relays:
        raise ConfigEntryNotReady(f"Domestia controller at {host} reported no relays")

    overrides = {k: v for k, v in entry.options.items() if k not in _NON_RELAY_OPTION_KEYS}
    light_configs = _build_light_configs(discovered_relays, overrides)
    client.set_lights(light_configs)

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = DomestiaCoordinator(hass, client, timedelta(seconds=scan_interval))
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "relays": discovered_relays,
        "light_configs": light_configs,
    }

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry whenever its Options change (e.g. a relay was renamed)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
