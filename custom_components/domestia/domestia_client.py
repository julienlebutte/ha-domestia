"""Low-level TCP client for a Domestia DMC-008 controller.

This is a faithful Python port of the Go client from
https://github.com/victorjacobs/go-domestia (domestia/client.go and
domestia/light.go). It talks the controller's own binary protocol
directly over TCP -- no MQTT, no external bridge process.

Wire format (see packCommand in client.go):
    0xff 0x00 0x00 <len(cmd)> <cmd bytes...> <checksum>
where checksum is the sum of the command bytes, truncated to one byte.
"""
from __future__ import annotations

import socket
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

DEFAULT_PORT = 52001
TIMEOUT_SECONDS = 1.0  # matches the 1s deadline set in the Go client

RELAY_STATE_OFF = 0
RELAY_STATE_ON = 1

# Command bytes, taken directly from client.go
CMD_GET_STATE = 0x3C
CMD_RELAY_ON = 0x0E
CMD_RELAY_OFF = 0x0F
CMD_SET_BRIGHTNESS = 0x10

MAX_BRIGHTNESS = 63


@dataclass
class LightConfig:
    """Static configuration for one light (equivalent of config.Light)."""

    name: str
    relay: int
    dimmable: bool = False
    always_on: bool = False


class Light:
    """A light's state as read from the controller (equivalent of light.go's Light)."""

    def __init__(self, cfg: LightConfig, brightness: int) -> None:
        # If brightness is exactly 1, the relay is not dimmable and on.
        # (same special case as NewLight in light.go)
        if brightness == 1:
            brightness = MAX_BRIGHTNESS
        self.configuration = cfg
        self.brightness = brightness

    def is_max_brightness(self) -> bool:
        return self.brightness == MAX_BRIGHTNESS

    def is_min_brightness(self) -> bool:
        return self.brightness == 0


class DomestiaError(RuntimeError):
    """Raised when the controller returns an unexpected response."""


class DomestiaClient:
    """TCP client for a Domestia DMC-008 controller.

    One connection is opened, used, and closed per command -- exactly
    like the Go client -- and a lock serializes access so two threads
    (e.g. two HA entities polling at once) never talk to the
    controller at the same time.
    """

    def __init__(self, ip_address: str, lights: Optional[List[LightConfig]] = None) -> None:
        if not ip_address:
            raise ValueError("DomestiaClient requires ip_address")

        self._ip_address = ip_address
        self._lock = threading.Lock()
        self._light_configuration: Dict[int, LightConfig] = {
            light.relay: light for light in (lights or [])
        }

    def set_lights(self, lights: List[LightConfig]) -> None:
        """Replace the known light configuration (used after discover_relays())."""
        self._light_configuration = {light.relay: light for light in lights}

    def discover_relays(self) -> List[int]:
        """Ask the controller how many relays it manages, and their numbers.

        The DMC-008 has no concept of light names or zones -- GetState just
        returns one status byte per relay it knows about, with nothing
        else identifying them. This is as far as auto-discovery can go:
        it tells you *how many* relays exist and lets Home Assistant
        create an entity for each one automatically, but friendly names,
        dimmable/always_on flags are metadata the controller simply
        doesn't have, so those still need to come from configuration
        (with sensible defaults when not given).
        """
        response = self._send(bytes([CMD_GET_STATE]))
        if not response or response[0] != 0xFF:
            return []
        relay_count = len(response) - 3
        return list(range(1, relay_count + 1))

    def get_state(self) -> List[Light]:
        """Query the controller and return the current state of all configured lights."""
        response = self._send(bytes([CMD_GET_STATE]))

        lights: List[Light] = []
        if not response or response[0] != 0xFF:
            return lights

        # response[3:] mirrors the Go code's `response[3:]` -- one byte per relay
        for i, relay_byte in enumerate(response[3:]):
            cfg = self._light_configuration.get(i + 1)
            if cfg is not None:
                lights.append(Light(cfg, relay_byte))

        return lights

    def poll(self) -> Dict[int, Light]:
        """Fetch the state of every configured light in a single round trip.

        This is the one call the Home Assistant integration should use for
        polling, however many lights are configured: it issues exactly one
        GetState command (one TCP connection) and returns every light keyed
        by relay, instead of each entity opening its own connection.

        It also enforces that any light configured as always_on is really
        at max brightness, turning it back on otherwise -- this mirrors
        publishLightState() in the original project's bridge.go, which does
        the same check right after every poll.
        """
        by_relay = {light.configuration.relay: light for light in self.get_state()}

        for cfg in self._light_configuration.values():
            if not cfg.always_on:
                continue
            light = by_relay.get(cfg.relay)
            if light is not None and not light.is_max_brightness():
                self.turn_on(cfg.relay)
                self.set_max_brightness(cfg.relay)
                by_relay[cfg.relay] = Light(cfg, MAX_BRIGHTNESS)

        return by_relay

    def turn_on(self, relay: int) -> None:
        self._set_relay_state(relay, RELAY_STATE_ON)

    def turn_off(self, relay: int) -> None:
        self._set_relay_state(relay, RELAY_STATE_OFF)

    def _set_relay_state(self, relay: int, state: int) -> None:
        toggle_command = CMD_RELAY_ON if state == RELAY_STATE_ON else CMD_RELAY_OFF
        response = self._send(bytes([toggle_command, relay]))
        if response != b"OK":
            raise DomestiaError(f"expected OK, received {response!r}")

    def set_brightness(self, relay: int, brightness: int) -> None:
        """brightness is 0-63, the controller's own native range."""
        brightness = max(0, min(MAX_BRIGHTNESS, brightness))
        response = self._send(bytes([CMD_SET_BRIGHTNESS, relay, brightness]))
        if response != b"OK":
            raise DomestiaError(f"expected OK, received {response!r}")

    def set_max_brightness(self, relay: int) -> None:
        self.set_brightness(relay, MAX_BRIGHTNESS)

    def _connect(self) -> socket.socket:
        sock = socket.create_connection(
            (self._ip_address, DEFAULT_PORT), timeout=TIMEOUT_SECONDS
        )
        sock.settimeout(TIMEOUT_SECONDS)
        return sock

    def _send(self, command: bytes) -> bytes:
        with self._lock:
            sock = self._connect()
            try:
                sock.sendall(_pack_command(command))
                response = sock.recv(256)
                if len(response) == 0:
                    raise DomestiaError("read 0 bytes from controller")
                return response
            finally:
                sock.close()


def _pack_command(cmd: bytes) -> bytes:
    """Pack a command into a controller message (mirrors packCommand in client.go)."""
    checksum = sum(cmd) & 0xFF
    return bytes([0xFF, 0x00, 0x00, len(cmd)]) + bytes(cmd) + bytes([checksum])
