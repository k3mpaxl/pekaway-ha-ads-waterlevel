"""Thin synchronous ADS1115 driver. Always invoked from executor."""

from __future__ import annotations

import logging
import time

from smbus2 import SMBus

from .const import (
    COMP_DISABLE,
    CONVERSION_DELAY_SEC,
    DR_128SPS,
    MODE_SINGLE,
    MUX_MAP,
    OS_START,
    PGA_BITS,
    PGA_RANGE_V,
    REG_CONFIG,
    REG_CONV,
)

_LOGGER = logging.getLogger(__name__)


def _build_cfg(channel: int) -> int:
    """Build an ADS1115 config word for single-ended AINx vs GND."""
    return OS_START | MUX_MAP[channel] | PGA_BITS | MODE_SINGLE | DR_128SPS | COMP_DISABLE


class ADS1115:
    """Minimal ADS1115 wrapper.  All methods block — run from executor."""

    def __init__(self, bus_num: int, address: int) -> None:
        """Initialize — does not open the bus yet."""
        self._bus_num = bus_num
        self._address = address
        self._bus: SMBus | None = None

    def open(self) -> None:
        """Open the I2C bus. Blocking — call from executor."""
        self._bus = SMBus(self._bus_num)
        # Sanity read: will raise OSError if device is missing.
        self._bus.read_byte(self._address)

    def close(self) -> None:
        """Close the I2C bus."""
        if self._bus is not None:
            try:
                self._bus.close()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Error closing SMBus: %s", err)
            self._bus = None

    def read_channel_voltage(self, channel: int) -> float | None:
        """Read a single-shot conversion on the given AINx channel. Blocking."""
        if self._bus is None:
            raise OSError("ADS1115 bus is not open")
        cfg = _build_cfg(channel)
        self._bus.write_i2c_block_data(
            self._address, REG_CONFIG, [(cfg >> 8) & 0xFF, cfg & 0xFF]
        )
        time.sleep(CONVERSION_DELAY_SEC)
        raw = self._bus.read_i2c_block_data(self._address, REG_CONV, 2)
        val = (raw[0] << 8) | raw[1]
        if val > 0x7FFF:
            val -= 0x10000  # signed 16-bit
        v_adc = (val * PGA_RANGE_V) / 32768.0
        if v_adc < 0:
            v_adc = 0.0
        return v_adc
