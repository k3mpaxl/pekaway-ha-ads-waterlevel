# ADS1115 Water Level — Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-%E2%89%A52024.10-blue)](https://www.home-assistant.io/)
[![Validate](https://github.com/k3mpaxl/pekaway-ha-ads-waterlevel/actions/workflows/validate.yml/badge.svg)](https://github.com/k3mpaxl/pekaway-ha-ads-waterlevel/actions/workflows/validate.yml)

Read water tank levels using an **ADS1115** 4-channel ADC on the I²C bus. Supports up to 4 tanks with configurable voltage/resistance-to-liter mapping.

> Part of the [Pekaway VAN PI CORE](https://github.com/k3mpaxl/pekaway-vanpi-homeassistant) integration family.

## Features

- Up to **4 channels** (single-ended or differential)
- Modes: **voltage**, **resistive**, **capacitive**
- Custom mapping curves (voltage → liters) as JSON
- Pull-up resistor configuration for resistive sensors
- Full Config Flow UI — no YAML needed

## Prerequisites

| | |
|---|---|
| **Hardware** | ADS1115 ADC on I²C bus |
| **Home Assistant** | ≥ 2024.10 |

## Installation via HACS

1. **HACS** → **Integrations** → three dots → **Custom repositories**
2. Add: `https://github.com/k3mpaxl/pekaway-ha-ads-waterlevel` → **Integration**
3. Install **ADS1115 Water Level**, restart Home Assistant.

## Setup

1. **Settings → Devices & Services → + Add Integration**
2. Search for **ADS1115 Water Level**
3. Enter I²C bus and address (default `0x48`)
4. Configure each tank: name, channel, mode, and mapping curve.

## Removal

1. **Settings → Devices & Services** → click the integration → **Delete**
2. Optionally uninstall via HACS.

## License

MIT — see [LICENSE](./LICENSE).
