"""Home Assistant light platform for a Domestia DMC-008 controller.

Entities are created from a config entry (set up via the UI -- see
config_flow.py), not from configuration.yaml. All the state comes
from the shared DomestiaCoordinator set up in __init__.py: one
client.poll() call refreshes every relay in a single TCP round trip,
however many lights there are (tested with 30), and each entity here
just reads its relay's slice of that cached result.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DomestiaCoordinator
from .domestia_client import DomestiaClient, DomestiaError, Light, LightConfig

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Domestia lights from a config entry."""
    stored = hass.data[DOMAIN][entry.entry_id]
    coordinator: DomestiaCoordinator = stored["coordinator"]
    client: DomestiaClient = stored["client"]
    light_configs: List[LightConfig] = stored["light_configs"]

    entities = [
        DomestiaLight(coordinator, client, cfg)
        for cfg in light_configs
        if not cfg.always_on
    ]
    async_add_entities(entities)


class DomestiaLight(CoordinatorEntity[DomestiaCoordinator], LightEntity):
    """A single Domestia relay, exposed as a Home Assistant light.

    State comes entirely from the shared coordinator's cached data --
    this entity never opens its own connection to the controller for
    polling, only for the turn_on/turn_off/brightness commands the
    user actually triggers.
    """

    _attr_should_poll = False

    def __init__(
        self, coordinator: DomestiaCoordinator, client: DomestiaClient, cfg: LightConfig
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._cfg = cfg
        self._attr_name = cfg.name
        self._attr_unique_id = f"domestia_relay_{cfg.relay}"

        color_mode = ColorMode.BRIGHTNESS if cfg.dimmable else ColorMode.ONOFF
        self._attr_color_mode = color_mode
        self._attr_supported_color_modes = {color_mode}

    @property
    def _light(self) -> Optional[Light]:
        data = self.coordinator.data
        return data.get(self._cfg.relay) if data else None

    @property
    def available(self) -> bool:
        return super().available and self._light is not None

    @property
    def is_on(self) -> Optional[bool]:
        light = self._light
        return None if light is None else not light.is_min_brightness()

    @property
    def brightness(self) -> Optional[int]:
        light = self._light
        if light is None:
            return None
        # controller range is 0-63, HA expects 0-255
        return round(light.brightness / 63 * 255)

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)

        def _do_turn_on() -> None:
            self._client.turn_on(self._cfg.relay)
            if not self._cfg.dimmable:
                self._client.set_max_brightness(self._cfg.relay)
            elif brightness is not None:
                self._client.set_brightness(self._cfg.relay, round(brightness / 255 * 63))

        try:
            await self.hass.async_add_executor_job(_do_turn_on)
        except (DomestiaError, OSError) as err:
            _LOGGER.error("Failed to turn on %s: %s", self._cfg.name, err)
            return

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self.hass.async_add_executor_job(self._client.turn_off, self._cfg.relay)
        except (DomestiaError, OSError) as err:
            _LOGGER.error("Failed to turn off %s: %s", self._cfg.name, err)
            return

        await self.coordinator.async_request_refresh()
