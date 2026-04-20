"""Config Flow for the ADS Water Level integration."""

from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .ads1115 import ADS1115
from .const import (
    ADS_ADDR_DEFAULT,
    CONF_I2C_ADDRESS,
    CONF_I2C_BUS,
    CONF_TANK_CHANNEL,
    CONF_TANK_DIVIDER_RATIO,
    CONF_TANK_INVERT,
    CONF_TANK_MODE,
    CONF_TANK_NAME,
    CONF_TANK_R_PULLUP,
    CONF_TANK_V_MAX,
    CONF_TANK_V_REF,
    CONF_TANKS,
    DEFAULT_I2C_BUS,
    DOMAIN,
    MODE_VOLTAGE,
    TANK_MODES,
)

_LOGGER = logging.getLogger(__name__)


class ADSConnectionError(Exception):
    """Raised when the ADS1115 cannot be opened."""


async def _probe_ads(hass: HomeAssistant, bus_num: int, address: int) -> None:
    """Probe that an ADS1115 is reachable at the given I2C address."""
    driver = ADS1115(bus_num, address)

    def _open_and_close() -> None:
        driver.open()
        driver.close()

    try:
        await hass.async_add_executor_job(_open_and_close)
    except OSError as err:
        raise ADSConnectionError(str(err)) from err


HUB_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_I2C_BUS, default=DEFAULT_I2C_BUS): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=10)
        ),
        vol.Optional(CONF_I2C_ADDRESS, default=ADS_ADDR_DEFAULT): vol.All(
            vol.Coerce(int), vol.Range(min=0x48, max=0x4B)
        ),
    }
)


def _tank_schema(existing: dict[str, Any] | None = None) -> vol.Schema:
    """Schema for adding or editing a single tank."""
    defaults = existing or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_TANK_NAME, default=defaults.get(CONF_TANK_NAME, "")
            ): TextSelector(),
            vol.Required(
                CONF_TANK_CHANNEL, default=defaults.get(CONF_TANK_CHANNEL, 1)
            ): NumberSelector(
                NumberSelectorConfig(min=1, max=4, step=1, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_TANK_MODE, default=defaults.get(CONF_TANK_MODE, MODE_VOLTAGE)
            ): SelectSelector(
                SelectSelectorConfig(
                    options=TANK_MODES, mode=SelectSelectorMode.DROPDOWN
                )
            ),
            vol.Optional(
                CONF_TANK_V_MAX, default=defaults.get(CONF_TANK_V_MAX, 3.3)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.1, max=20.0, step=0.01, mode=NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_TANK_INVERT, default=defaults.get(CONF_TANK_INVERT, False)
            ): bool,
            vol.Optional(
                CONF_TANK_DIVIDER_RATIO,
                default=defaults.get(CONF_TANK_DIVIDER_RATIO, 1.0),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.1, max=50.0, step=0.01, mode=NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_TANK_R_PULLUP, default=defaults.get(CONF_TANK_R_PULLUP, 47000)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=100, max=1_000_000, step=1, mode=NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_TANK_V_REF, default=defaults.get(CONF_TANK_V_REF, 3.3)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.5, max=24.0, step=0.01, mode=NumberSelectorMode.BOX
                )
            ),
        }
    )


class ADSWaterLevelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow: first the ADS hub, then one or more tanks."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._bus_num: int = DEFAULT_I2C_BUS
        self._address: int = ADS_ADDR_DEFAULT
        self._tanks: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the ADS1115 hub (bus + address)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            bus_num = int(user_input[CONF_I2C_BUS])
            address = int(user_input[CONF_I2C_ADDRESS])
            await self.async_set_unique_id(f"{bus_num}_{address:#04x}")
            self._abort_if_unique_id_configured()

            try:
                await _probe_ads(self.hass, bus_num, address)
            except ADSConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected probe error")
                errors["base"] = "unknown"
            else:
                self._bus_num = bus_num
                self._address = address
                return await self.async_step_tank()

        return self.async_show_form(
            step_id="user", data_schema=HUB_SCHEMA, errors=errors
        )

    async def async_step_tank(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a tank (repeatable)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_TANK_NAME].strip()
            if any(t[CONF_TANK_NAME] == name for t in self._tanks):
                errors[CONF_TANK_NAME] = "duplicate_name"
            else:
                self._tanks.append(
                    {
                        **user_input,
                        CONF_TANK_NAME: name,
                        CONF_TANK_CHANNEL: int(user_input[CONF_TANK_CHANNEL]),
                    }
                )
                return await self.async_step_add_another()

        return self.async_show_form(
            step_id="tank", data_schema=_tank_schema(), errors=errors
        )

    async def async_step_add_another(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask whether to add another tank or finish."""
        if user_input is not None:
            if user_input.get("add_another"):
                return await self.async_step_tank()
            return self._finish()

        return self.async_show_form(
            step_id="add_another",
            data_schema=vol.Schema({vol.Required("add_another", default=False): bool}),
        )

    def _finish(self) -> ConfigFlowResult:
        """Create the config entry with all tanks."""
        return self.async_create_entry(
            title=f"ADS1115 @ 0x{self._address:02x}",
            data={
                CONF_I2C_BUS: self._bus_num,
                CONF_I2C_ADDRESS: self._address,
                CONF_TANKS: self._tanks,
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure the ADS bus/address."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            bus_num = int(user_input[CONF_I2C_BUS])
            address = int(user_input[CONF_I2C_ADDRESS])
            await self.async_set_unique_id(f"{bus_num}_{address:#04x}")
            self._abort_if_unique_id_mismatch(reason="address_mismatch")

            try:
                await _probe_ads(self.hass, bus_num, address)
            except ADSConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected probe error")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_I2C_BUS: bus_num,
                        CONF_I2C_ADDRESS: address,
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_I2C_BUS,
                        default=entry.data.get(CONF_I2C_BUS, DEFAULT_I2C_BUS),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
                    vol.Required(
                        CONF_I2C_ADDRESS,
                        default=entry.data.get(CONF_I2C_ADDRESS, ADS_ADDR_DEFAULT),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0x48, max=0x4B)),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return ADSOptionsFlow()


class ADSOptionsFlow(OptionsFlow):
    """Options flow: edit per-tank mapping curves."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick which tank's mapping to edit."""
        tanks = self.config_entry.data.get(CONF_TANKS, [])
        names = [t[CONF_TANK_NAME] for t in tanks]
        if not names:
            return self.async_abort(reason="no_tanks")

        if user_input is not None:
            self._selected_tank = user_input["tank"]
            return await self.async_step_mapping()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("tank", default=names[0]): SelectSelector(
                        SelectSelectorConfig(
                            options=names, mode=SelectSelectorMode.DROPDOWN
                        )
                    )
                }
            ),
        )

    async def async_step_mapping(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the mapping curve as JSON list of {v, l} pairs."""
        tank_name = self._selected_tank
        option_key = f"{tank_name}_mapping"

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                parsed = json.loads(user_input["mapping_json"])
                if not isinstance(parsed, list):
                    raise ValueError("mapping must be a JSON list")
                for item in parsed:
                    if "v" not in item or "l" not in item:
                        raise ValueError("each item needs v and l")
                    float(item["v"])
                    float(item["l"])
            except (ValueError, TypeError, json.JSONDecodeError) as err:
                _LOGGER.warning("Invalid mapping JSON: %s", err)
                errors["base"] = "invalid_mapping"
            else:
                options = dict(self.config_entry.options)
                options[option_key] = parsed
                return self.async_create_entry(title="", data=options)

        default = json.dumps(
            self.config_entry.options.get(option_key, []), ensure_ascii=False
        )
        return self.async_show_form(
            step_id="mapping",
            data_schema=vol.Schema(
                {vol.Required("mapping_json", default=default): TextSelector()}
            ),
            errors=errors,
            description_placeholders={"tank": tank_name},
        )
