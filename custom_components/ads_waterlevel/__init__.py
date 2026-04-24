"""The ADS Water Level integration."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .ads1115 import ADS1115
from .const import (
    ADS_ADDR_DEFAULT,
    CONF_I2C_ADDRESS,
    CONF_I2C_BUS,
    DEFAULT_I2C_BUS,
    PLATFORMS,
)
from .coordinator import ADSConfigEntry, ADSCoordinator, ADSData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ADSConfigEntry
) -> bool:
    """Set up an ADS Water Level config entry."""
    bus_num = entry.data.get(CONF_I2C_BUS, DEFAULT_I2C_BUS)
    address = entry.data.get(CONF_I2C_ADDRESS, ADS_ADDR_DEFAULT)

    driver = ADS1115(bus_num, address)
    try:
        await hass.async_add_executor_job(driver.open)
    except OSError as err:
        raise ConfigEntryNotReady(
            f"Cannot open I2C bus {bus_num} at 0x{address:02x}: {err}"
        ) from err

    coordinator = ADSCoordinator(hass, entry, driver)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = ADSData(driver=driver, coordinator=coordinator)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ADSConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unload_ok:
        driver = entry.runtime_data.driver
        await hass.async_add_executor_job(driver.close)
    return unload_ok


async def async_reload_entry(
    hass: HomeAssistant, entry: ADSConfigEntry
) -> None:
    """Reload entry after options changes."""
    await hass.config_entries.async_reload(entry.entry_id)
