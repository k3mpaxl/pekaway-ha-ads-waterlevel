"""ADS Water Level sensor entities."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfElectricPotential, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_TANK_CHANNEL,
    CONF_TANK_DIVIDER_RATIO,
    CONF_TANK_INVERT,
    CONF_TANK_MAPPING,
    CONF_TANK_MODE,
    CONF_TANK_NAME,
    CONF_TANK_R_PULLUP,
    CONF_TANK_V_MAX,
    CONF_TANK_V_REF,
    CONF_TANKS,
    DOMAIN,
    MANUFACTURER,
    MODE_RESISTIVE,
    MODEL,
)
from .coordinator import ADSConfigEntry, ADSCoordinator
from .mapping import build_linear_mapping, ch_human_to_ain, interp, normalize_mapping_points

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 0


VOLTAGE_DESCRIPTION = SensorEntityDescription(
    key="voltage",
    translation_key="voltage",
    device_class=SensorDeviceClass.VOLTAGE,
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=2,
)

LEVEL_DESCRIPTION = SensorEntityDescription(
    key="level",
    translation_key="level",
    native_unit_of_measurement=UnitOfVolume.LITERS,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=1,
)

RESISTANCE_DESCRIPTION = SensorEntityDescription(
    key="resistance",
    translation_key="resistance",
    native_unit_of_measurement="Ω",
    state_class=SensorStateClass.MEASUREMENT,
    entity_registry_enabled_default=False,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ADSConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    coordinator = entry.runtime_data.coordinator
    tanks: list[dict[str, Any]] = entry.data.get(CONF_TANKS, [])

    entities: list[SensorEntity] = []
    for tank in tanks:
        name = tank[CONF_TANK_NAME]
        ain = ch_human_to_ain(tank[CONF_TANK_CHANNEL])
        v_max = float(tank.get(CONF_TANK_V_MAX, 3.3))
        invert = bool(tank.get(CONF_TANK_INVERT, False))
        divider = float(tank.get(CONF_TANK_DIVIDER_RATIO, 1.0))
        mode = tank.get(CONF_TANK_MODE, "voltage")

        # Mapping curve (options override data, data falls back to linear)
        option_mapping = entry.options.get(f"{name}_mapping")
        mapping_items = option_mapping or tank.get(CONF_TANK_MAPPING)
        if mapping_items:
            mapping = normalize_mapping_points(mapping_items, v_max=v_max, invert=invert)
        else:
            mapping = build_linear_mapping(v_max=v_max, invert=invert)

        device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{name}")},
            name=name,
            manufacturer=MANUFACTURER,
            model=MODEL,
            via_device=(DOMAIN, entry.entry_id),
        )

        entities.append(
            ADSVoltageSensor(
                coordinator=coordinator,
                entry=entry,
                tank_name=name,
                ain=ain,
                divider_ratio=divider,
                device_info=device_info,
            )
        )
        entities.append(
            ADSLevelSensor(
                coordinator=coordinator,
                entry=entry,
                tank_name=name,
                ain=ain,
                divider_ratio=divider,
                mapping=mapping,
                device_info=device_info,
            )
        )
        if mode == MODE_RESISTIVE:
            entities.append(
                ADSResistanceSensor(
                    coordinator=coordinator,
                    entry=entry,
                    tank_name=name,
                    ain=ain,
                    divider_ratio=divider,
                    r_pullup=float(tank.get(CONF_TANK_R_PULLUP, 47000)),
                    v_ref=float(tank.get(CONF_TANK_V_REF, 3.3)),
                    device_info=device_info,
                )
            )

    async_add_entities(entities)


class _ADSBase(CoordinatorEntity[ADSCoordinator], SensorEntity):
    """Base class for ADS Water Level sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ADSCoordinator,
        entry: ADSConfigEntry,
        tank_name: str,
        ain: int,
        divider_ratio: float,
        device_info: DeviceInfo,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entity_description = description
        self._tank_name = tank_name
        self._ain = ain
        self._ratio = divider_ratio
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_{tank_name}_{description.key}"

    def _last_v_in(self) -> float | None:
        """Return the latest input voltage after divider correction."""
        if self.coordinator.data is None:
            return None
        v_adc = self.coordinator.data.get(self._ain)
        if v_adc is None:
            return None
        return round(v_adc * self._ratio, 3)

    @property
    def available(self) -> bool:
        """Sensor available if the coordinator has a reading for its AIN."""
        if not super().available:
            return False
        return self._last_v_in() is not None


class ADSVoltageSensor(_ADSBase):
    """Raw input voltage on one tank's AIN."""

    def __init__(
        self,
        coordinator: ADSCoordinator,
        entry: ADSConfigEntry,
        tank_name: str,
        ain: int,
        divider_ratio: float,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize."""
        super().__init__(
            coordinator,
            entry,
            tank_name,
            ain,
            divider_ratio,
            device_info,
            VOLTAGE_DESCRIPTION,
        )

    @property
    def native_value(self) -> float | None:
        """Return the current voltage."""
        v = self._last_v_in()
        return None if v is None else round(v, 2)


class ADSLevelSensor(_ADSBase):
    """Mapped tank level in liters."""

    def __init__(
        self,
        coordinator: ADSCoordinator,
        entry: ADSConfigEntry,
        tank_name: str,
        ain: int,
        divider_ratio: float,
        mapping: list[tuple[float, float]],
        device_info: DeviceInfo,
    ) -> None:
        """Initialize."""
        super().__init__(
            coordinator,
            entry,
            tank_name,
            ain,
            divider_ratio,
            device_info,
            LEVEL_DESCRIPTION,
        )
        self._mapping = mapping

    @property
    def native_value(self) -> float | None:
        """Return the interpolated tank level in liters."""
        v = self._last_v_in()
        if v is None:
            return None
        return round(interp(self._mapping, v), 1)


class ADSResistanceSensor(_ADSBase):
    """Computed sensor resistance from a pull-up divider."""

    def __init__(
        self,
        coordinator: ADSCoordinator,
        entry: ADSConfigEntry,
        tank_name: str,
        ain: int,
        divider_ratio: float,
        r_pullup: float,
        v_ref: float,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize."""
        super().__init__(
            coordinator,
            entry,
            tank_name,
            ain,
            divider_ratio,
            device_info,
            RESISTANCE_DESCRIPTION,
        )
        self._r_pullup = r_pullup
        self._v_ref = v_ref

    @property
    def native_value(self) -> float | None:
        """Return the computed resistance in ohms."""
        v = self._last_v_in()
        if v is None or v >= self._v_ref:
            return None
        r = self._r_pullup * (v / (self._v_ref - v))
        return round(r, 0)
