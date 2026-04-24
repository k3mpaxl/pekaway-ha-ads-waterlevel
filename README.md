# ADS1115 Water Level — Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-%E2%89%A52024.10-blue)](https://www.home-assistant.io/)
[![Validate](https://github.com/k3mpaxl/pekaway-ha-ads-waterlevel/actions/workflows/validate.yml/badge.svg)](https://github.com/k3mpaxl/pekaway-ha-ads-waterlevel/actions/workflows/validate.yml)

Read water tank levels using an **ADS1115** 4-channel ADC on the I²C bus. Supports up to 4 tanks with configurable voltage/resistance-to-liter mapping.

> Part of the [Pekaway VAN PI CORE](https://github.com/k3mpaxl/pekaway-vanpi-homeassistant) integration family.

## Features

- Up to **4 channels** (single-ended or differential)
- Modes: **voltage**, **resistive**, **capacitive**
- Custom mapping curves via measured points (`liters - volts`, one line per point)
- Alternative linear calibration via **empty voltage** and **full voltage**
- Pull-up resistor configuration for resistive sensors
- Full Config Flow UI — no YAML needed
- Editable per-tank Options Flow (channel, mode, electrical parameters, calibration)
- Fully localized UI in English and German (Deutsch)
- Automatic reload of the integration when options are saved

## Prerequisites

| | |
|---|---|
| **Hardware** | ADS1115 ADC on I²C bus |
| **Raspberry Pi** | `dtparam=i2c_vc=on`, `dtparam=i2c_arm=on` and `i2c-dev` module in `config.txt` |
| **Home Assistant** | ≥ 2024.10 |

> See the [VAN PI CORE setup guide](https://github.com/k3mpaxl/pekaway-vanpi-homeassistant#2-configtxt-anpassen) for detailed `config.txt` and I²C instructions.

## Installation via HACS

1. **HACS** → **Integrations** → three dots → **Custom repositories**
2. Add: `https://github.com/k3mpaxl/pekaway-ha-ads-waterlevel` → **Integration**
3. Install **ADS1115 Water Level**, restart Home Assistant.

## Setup

1. **Settings → Devices & Services → + Add Integration**
2. Search for **ADS1115 Water Level**
3. Enter I²C bus and address (default `0x48`)
4. Configure each tank: name, channel, mode, and mapping curve.
5. Optional calibration: add a list of measured points `{l: liters, v: volts}` (see format below).
6. Alternative: leave the list empty and enter **Empty voltage** + **Full voltage** for linear 0-100 L calibration.

### Editing later

Via **Settings → Devices & Services → ADS1115 Water Level → Configure** you can pick any configured tank and edit it later. The options flow lets you change:

- Channel (1–4)
- Sensor mode (`voltage`, `resistive`, `capacitive`)
- Maximum voltage (`v_max`) and invert flag
- Voltage divider ratio
- Pull-up resistor and reference voltage (for `resistive` mode)
- Calibration — either **measured points** or **empty/full voltage**

Saving options triggers an automatic reload of the integration, so new values take effect immediately without restarting Home Assistant.

> The **tank name** cannot be changed via the options flow (it is the stable identifier for overrides and entity IDs). To rename a tank, remove and re-add the integration.

The I²C **bus and address** of the ADS1115 are changed via the **Reconfigure** entry of the integration, not via options.

### Calibration format

Measured points are entered as a **structured list** (the field uses Home Assistant's built-in YAML/JSON editor — the same component used in the automation UI, so it stays responsive with any number of points). Each entry has two keys:

- `l` — liters
- `v` — volts

YAML example (short):

```yaml
- l: 13
  v: 0.319
- l: 19.5
  v: 0.717
- l: 26
  v: 0.922
- l: 100
  v: 2.263
```

JSON equivalent:

```json
[
  {"l": 13,   "v": 0.319},
  {"l": 19.5, "v": 0.717},
  {"l": 26,   "v": 0.922},
  {"l": 100,  "v": 2.263}
]
```

#### Full real-world example (Pekaway 100 L tank)

A dense calibration table pays off, especially around the quarter, half, and three-quarter marks. Example with 14 measured points:

```yaml
- l: 13
  v: 0.319
- l: 19.5
  v: 0.717
- l: 26
  v: 0.922
- l: 32.5
  v: 1.035
- l: 39
  v: 1.160
- l: 45.5
  v: 1.274
- l: 52
  v: 1.387
- l: 58.5
  v: 1.490
- l: 65
  v: 1.615
- l: 78
  v: 1.842
- l: 84.5
  v: 1.956
- l: 91
  v: 2.081
- l: 97.5
  v: 2.217
- l: 100
  v: 2.263
```

#### Rules

- At least **2 points** are required
- Voltages must be **strictly increasing** (no duplicates)
- Points are sorted automatically by voltage
- Interpolation between points is piecewise linear; outside the range the nearest value is held

### Linear empty/full format

- Empty voltage = measured voltage when the tank is empty (0 L)
- Full voltage = measured voltage when the tank is full (100 L)
- Enter either measured points or empty/full voltages, not both

## Entities

For each configured tank the integration creates:

- `sensor.<tank>_voltage` — raw input voltage after divider correction
- `sensor.<tank>_level` — interpolated tank level in liters
- `sensor.<tank>_resistance` — computed sensor resistance (only in `resistive` mode, disabled by default)

## Language support

The UI is provided in **English** and **Deutsch** via the standard Home Assistant translation system. No configuration needed — the language follows your Home Assistant profile.

## Removal

1. **Settings → Devices & Services** → click the integration → **Delete**
2. Optionally uninstall via HACS.

## License

MIT — see [LICENSE](./LICENSE).
