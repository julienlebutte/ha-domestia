"""Shared constants for the Domestia integration."""
from __future__ import annotations

DOMAIN = "domestia"

CONF_RELAY = "relay"
CONF_DIMMABLE = "dimmable"
CONF_ALWAYS_ON = "always_on"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 10  # seconds


def default_relay_name(relay: int) -> str:
    """Fallback friendly name for a relay with no override configured.

    The controller has no notion of light names, so any relay that
    hasn't been renamed via the integration's Options screen gets this.
    """
    return f"Domestia relay {relay}"
