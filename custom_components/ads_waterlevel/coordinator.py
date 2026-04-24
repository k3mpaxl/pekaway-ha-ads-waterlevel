"""DataUpdateCoordinator for the ADS Water Level integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .ads1115 import ADS1115
from .const import (
    CONF_TANK_CHANNEL,
    CONF_TANKS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .mapping import ch_human_to_ain

_LOGGER = logging.getLogger(__name__)


@dataclass
class ADSData:
    """Runtime data for an ADS Water Level config entry."""

    driver: ADS1115
    coordinator: ADSCoordinator


type ADSConfigEntry = ConfigEntry[ADSData]


class ADSCoordinator(DataUpdateCoordinator[dict[int, float | None]]):
    """Read all configured channels once per cycle."""

    config_entry: ADSConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ADSConfigEntry,
        driver: ADS1115,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}-{entry.entry_id}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.driver = driver

    def _channels_to_read(self) -> set[int]:
        """Derive the AIN set from configured tanks."""
        tanks: list[dict[str, Any]] = self.config_entry.data.get(
            CONF_TANKS, []
        )
        ains: set[int] = set()
        for t in tanks:
            ains.add(ch_human_to_ain(t[CONF_TANK_CHANNEL]))
        return ains

    async def _async_update_data(self) -> dict[int, float | None]:
        """Poll all required AIN channels once and return raw voltages."""
        ains = self._channels_to_read()
        try:
            return await self.hass.async_add_executor_job(self._read_all, ains)
        except OSError as err:
            raise UpdateFailed(f"ADS1115 I/O error: {err}") from err

    def _read_all(self, ains: set[int]) -> dict[int, float | None]:
        """Blocking read of each AIN. Errors per-channel are logged."""
        out: dict[int, float | None] = {}
        for ain in sorted(ains):
            try:
                out[ain] = self.driver.read_channel_voltage(ain)
            except OSError as err:
                _LOGGER.debug("Read failed on AIN%d: %s", ain, err)
                out[ain] = None
        return out
