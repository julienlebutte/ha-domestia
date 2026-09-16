"""Shared polling coordinator for the Domestia integration.

However many relays are configured, this issues exactly one
client.poll() (one TCP round trip) per update cycle, and every light
entity just reads the cached result -- see DomestiaLight in light.py.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Dict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .domestia_client import DomestiaClient, DomestiaError, Light

_LOGGER = logging.getLogger(__name__)


class DomestiaCoordinator(DataUpdateCoordinator[Dict[int, Light]]):
    """Polls the Domestia controller once per cycle for every configured light."""

    def __init__(
        self, hass: HomeAssistant, client: DomestiaClient, update_interval: timedelta
    ) -> None:
        super().__init__(hass, _LOGGER, name="domestia", update_interval=update_interval)
        self._client = client

    async def _async_update_data(self) -> Dict[int, Light]:
        try:
            # client.poll() does exactly one TCP round trip for every
            # configured relay, and also re-asserts always_on lights.
            return await self.hass.async_add_executor_job(self._client.poll)
        except (DomestiaError, OSError) as err:
            raise UpdateFailed(f"Error communicating with controller: {err}") from err
