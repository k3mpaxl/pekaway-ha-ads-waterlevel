"""Constants for the ADS Water Level integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "ads_waterlevel"
PLATFORMS: list[Platform] = [Platform.SENSOR]

MANUFACTURER = "Texas Instruments"
MODEL = "ADS1115"

# ------------------ ADS1115 I²C registers ---------------------------------
ADS_ADDR_DEFAULT = 0x48
REG_CONV = 0x00
REG_CONFIG = 0x01

MUX_MAP: dict[int, int] = {
    0: 0x4000,
    1: 0x5000,
    2: 0x6000,
    3: 0x7000,
}

PGA_BITS = 0x0200  # ±4.096 V
PGA_RANGE_V = 4.096
OS_START = 0x8000
MODE_SINGLE = 0x0100
DR_128SPS = 0x0080
COMP_DISABLE = 0x0003

DEFAULT_I2C_BUS = 1
DEFAULT_SCAN_INTERVAL = 5  # seconds
CONVERSION_DELAY_SEC = 0.009  # ~8 ms @ 128 SPS

# ------------------ Config / option keys ----------------------------------
CONF_I2C_BUS = "i2c_bus"
CONF_I2C_ADDRESS = "i2c_address"
CONF_TANKS = "tanks"

CONF_TANK_NAME = "name"
CONF_TANK_CHANNEL = "channel"
CONF_TANK_MODE = "mode"
CONF_TANK_V_MAX = "v_max"
CONF_TANK_INVERT = "invert"
CONF_TANK_DIVIDER_RATIO = "divider_ratio"
CONF_TANK_R_PULLUP = "r_pullup_ohm"
CONF_TANK_V_REF = "v_ref"
CONF_TANK_MAPPING = "mapping_points"
CONF_TANK_MAPPING_TEXT = "mapping_points_text"
CONF_TANK_EMPTY_V = "empty_voltage"
CONF_TANK_FULL_V = "full_voltage"

# Tank operating modes
MODE_VOLTAGE = "voltage"
MODE_CAPACITIVE = "capacitive"
MODE_RESISTIVE = "resistive"
TANK_MODES = [MODE_VOLTAGE, MODE_CAPACITIVE, MODE_RESISTIVE]
