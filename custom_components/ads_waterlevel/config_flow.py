"""Config Flow for the ADS Water Level integration."""

from __future__ import annotations

import logging
from typing import Any, Self

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
    ObjectSelector,
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
    CONF_TANK_EMPTY_V,
    CONF_TANK_FULL_V,
    CONF_TANK_INVERT,
    CONF_TANK_MAPPING,
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

TANK_SETTINGS_SUFFIX = "_settings"


def _to_float(value: Any) -> float:
    """Convert a value to float and accept decimal comma."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    return float(text)


def _parse_mapping_list(
    raw: Any,
) -> list[dict[str, float]]:
    """Validate a raw list of {l, v} dicts from the object selector."""
    if raw in (None, "", [], {}):
        return []
    if not isinstance(raw, list):
        raise ValueError("invalid_mapping")

    points: list[dict[str, float]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("invalid_mapping")
        if "l" not in item or "v" not in item:
            raise ValueError("invalid_mapping")
        try:
            liters = _to_float(item["l"])
            volts = _to_float(item["v"])
        except (TypeError, ValueError) as err:
            raise ValueError("invalid_mapping") from err
        points.append({"v": volts, "l": liters})

    if len(points) < 2:
        raise ValueError("not_enough_points")

    points.sort(key=lambda p: p["v"])
    for i in range(1, len(points)):
        if points[i]["v"] <= points[i - 1]["v"]:
            raise ValueError("duplicate_voltage")

    return points


def _mapping_option_key(tank_name: str) -> str:
    """Return the option key for a tank mapping override."""
    return f"{tank_name}_mapping"


def _settings_option_key(tank_name: str) -> str:
    """Return the option key for tank setting overrides."""
    return f"{tank_name}{TANK_SETTINGS_SUFFIX}"


def _linear_mapping_from_empty_full(
    empty_v: float,
    full_v: float,
) -> list[dict[str, float]]:
    """Create a linear 0..100L mapping from empty/full voltages."""
    return [
        {"v": float(empty_v), "l": 0.0},
        {"v": float(full_v), "l": 100.0},
    ]


def _linear_defaults_from_mapping(
    mapping: list[dict[str, Any]] | None,
) -> tuple[float | None, float | None]:
    """Infer empty/full voltages from a simple 2-point 0..100L mapping."""
    if not mapping or len(mapping) != 2:
        return None, None

    by_liters = {float(item["l"]): float(item["v"]) for item in mapping}
    if 0.0 not in by_liters or 100.0 not in by_liters:
        return None, None
    return by_liters[0.0], by_liters[100.0]


def _mapping_default_for_form(
    mapping: list[dict[str, Any]] | None,
) -> list[dict[str, float]]:
    """Return mapping points formatted for the ObjectSelector default."""
    if not mapping:
        return []
    return [
        {"l": float(item["l"]), "v": float(item["v"])}
        for item in mapping
    ]


def _parse_mapping_input(
    user_input: dict[str, Any],
    errors: dict[str, str],
) -> list[dict[str, float]] | None:
    """Validate mapping-related fields and return mapping points."""
    raw_mapping = user_input.get(CONF_TANK_MAPPING)
    empty_v = user_input.get(CONF_TANK_EMPTY_V)
    full_v = user_input.get(CONF_TANK_FULL_V)

    has_mapping = bool(raw_mapping)

    if has_mapping and (empty_v is not None or full_v is not None):
        errors["base"] = "mapping_conflict"
        return None

    if has_mapping:
        try:
            return _parse_mapping_list(raw_mapping)
        except ValueError as err:
            code = str(err)
            if code == "not_enough_points":
                errors[CONF_TANK_MAPPING] = "mapping_not_enough_points"
            elif code == "duplicate_voltage":
                errors[CONF_TANK_MAPPING] = "mapping_duplicate_voltage"
            else:
                errors[CONF_TANK_MAPPING] = "invalid_mapping"
            return None

    if empty_v is None and full_v is None:
        return []

    if empty_v is None or full_v is None:
        errors["base"] = "mapping_linear_requires_both"
        return None

    empty_f = float(empty_v)
    full_f = float(full_v)
    if abs(empty_f - full_f) < 1e-6:
        errors["base"] = "mapping_linear_equal_voltages"
        return None

    return _linear_mapping_from_empty_full(empty_f, full_f)


def _build_tank_data(
    user_input: dict[str, Any],
    mapping_points: list[dict[str, float]],
    *,
    include_name: bool,
) -> dict[str, Any]:
    """Build normalized tank data from form input."""
    tank_data = dict(user_input)
    tank_data.pop(CONF_TANK_EMPTY_V, None)
    tank_data.pop(CONF_TANK_FULL_V, None)
    tank_data[CONF_TANK_CHANNEL] = int(user_input[CONF_TANK_CHANNEL])
    if include_name:
        tank_data[CONF_TANK_NAME] = user_input[CONF_TANK_NAME].strip()
    else:
        tank_data.pop(CONF_TANK_NAME, None)

    if mapping_points:
        tank_data[CONF_TANK_MAPPING] = mapping_points
    else:
        tank_data.pop(CONF_TANK_MAPPING, None)
    return tank_data


def _effective_tank_config(
    config_entry: ConfigEntry,
    tank_name: str,
) -> dict[str, Any]:
    """Return tank data merged with options overrides."""
    tank = next(
        tank
        for tank in config_entry.data.get(CONF_TANKS, [])
        if tank[CONF_TANK_NAME] == tank_name
    )
    settings = config_entry.options.get(_settings_option_key(tank_name), {})
    mapping = config_entry.options.get(_mapping_option_key(tank_name))
    merged = {**tank, **settings}
    if mapping is not None:
        merged[CONF_TANK_MAPPING] = mapping
    return merged


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


def _tank_schema(
    existing: dict[str, Any] | None = None,
    *,
    include_name: bool = True,
) -> vol.Schema:
    """Schema for adding or editing a single tank."""
    defaults = existing or {}
    schema: dict[Any, Any] = {}
    if include_name:
        schema[
            vol.Required(
                CONF_TANK_NAME, default=defaults.get(CONF_TANK_NAME, "")
            )
        ] = TextSelector()

    empty_v, full_v = _linear_defaults_from_mapping(
        defaults.get(CONF_TANK_MAPPING)
    )
    mapping_default: list[dict[str, float]] = []
    if empty_v is None or full_v is None:
        mapping_default = _mapping_default_for_form(
            defaults.get(CONF_TANK_MAPPING)
        )

    schema.update(
        {
            vol.Required(
                CONF_TANK_CHANNEL, default=defaults.get(CONF_TANK_CHANNEL, 1)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=4,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_TANK_MODE,
                default=defaults.get(CONF_TANK_MODE, MODE_VOLTAGE),
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
                CONF_TANK_R_PULLUP,
                default=defaults.get(CONF_TANK_R_PULLUP, 47000),
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
            vol.Optional(
                CONF_TANK_MAPPING,
                default=mapping_default,
            ): ObjectSelector(),
        }
    )

    if empty_v is not None:
        schema[vol.Optional(CONF_TANK_EMPTY_V, default=empty_v)] = (
            NumberSelector(
                NumberSelectorConfig(
                    min=0.0, max=20.0, step=0.001, mode=NumberSelectorMode.BOX
                )
            )
        )
    else:
        schema[vol.Optional(CONF_TANK_EMPTY_V)] = NumberSelector(
            NumberSelectorConfig(
                min=0.0, max=20.0, step=0.001, mode=NumberSelectorMode.BOX
            )
        )

    if full_v is not None:
        schema[vol.Optional(CONF_TANK_FULL_V, default=full_v)] = (
            NumberSelector(
                NumberSelectorConfig(
                    min=0.0, max=20.0, step=0.001, mode=NumberSelectorMode.BOX
                )
            )
        )
    else:
        schema[vol.Optional(CONF_TANK_FULL_V)] = NumberSelector(
            NumberSelectorConfig(
                min=0.0, max=20.0, step=0.001, mode=NumberSelectorMode.BOX
            )
        )

    return vol.Schema(schema)


class ADSWaterLevelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow: first the ADS hub, then one or more tanks."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._bus_num: int = DEFAULT_I2C_BUS
        self._address: int = ADS_ADDR_DEFAULT
        self._tanks: list[dict[str, Any]] = []

    def is_matching(self, other_flow: Self) -> bool:
        """Return whether another flow targets the same device."""
        return (
            self.unique_id is not None
            and self.unique_id == other_flow.unique_id
        )

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
            mapping_points: list[dict[str, float]] | None = None
            if any(t[CONF_TANK_NAME] == name for t in self._tanks):
                errors[CONF_TANK_NAME] = "duplicate_name"
            else:
                mapping_points = _parse_mapping_input(user_input, errors)

            if not errors and mapping_points is not None:
                self._tanks.append(
                    _build_tank_data(
                        user_input,
                        mapping_points,
                        include_name=True,
                    )
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
            data_schema=vol.Schema(
                {vol.Required("add_another", default=False): bool}
            ),
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
                        default=entry.data.get(
                            CONF_I2C_ADDRESS,
                            ADS_ADDR_DEFAULT,
                        ),
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
    """Options flow: edit per-tank settings and calibration."""

    def __init__(self) -> None:
        """Initialize options flow state."""
        self._selected_tank: str = ""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick which tank to edit."""
        tanks = self.config_entry.data.get(CONF_TANKS, [])
        names = [t[CONF_TANK_NAME] for t in tanks]
        if not names:
            return self.async_abort(reason="no_tanks")

        if user_input is not None:
            self._selected_tank = user_input["tank"]
            return await self.async_step_tank()

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

    async def async_step_tank(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the selected tank settings and calibration."""
        tank_name = self._selected_tank
        mapping_option_key = _mapping_option_key(tank_name)
        settings_option_key = _settings_option_key(tank_name)
        current = _effective_tank_config(self.config_entry, tank_name)

        errors: dict[str, str] = {}
        if user_input is not None:
            parsed = _parse_mapping_input(user_input, errors)
            if not errors and parsed is not None:
                settings = _build_tank_data(
                    user_input,
                    [],
                    include_name=False,
                )
                options = dict(self.config_entry.options)
                options[settings_option_key] = settings
                if parsed:
                    options[mapping_option_key] = parsed
                else:
                    options.pop(mapping_option_key, None)
                return self.async_create_entry(title="", data=options)

        return self.async_show_form(
            step_id="tank",
            data_schema=_tank_schema(current, include_name=False),
            errors=errors,
            description_placeholders={"tank": tank_name},
        )
