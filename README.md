# Wahoo Kickr Core Home Assistant Integration (Custom)

This repository contains a custom Home Assistant integration for a Wahoo KICKR CORE trainer using WFTNP over TCP.

## Important notes

- This integration is largely AI-generated.
- The AI used this project as a source reference:
- I do not take any responsibility for damage of any kind. Use at your own risk.
- Tested with Kickr Core V2 (Wifi only)

```
https://github.com/elfrances/wahoo-fitness-tnp
```

## What it does

- Discovers and connects to Wahoo WFTNP devices on the LAN (optionally via zeroconf).
- Exposes sensors for speed, cadence, and power.
- Provides services for ERG and grade control, plus basic control point actions.

## Installation (custom component)

1. Copy `custom_components/wahoo_kickr_core` into your Home Assistant config directory.
2. Restart Home Assistant.
3. Add the integration via Settings -> Devices & Services.

## Installation (HACS)

1. In Home Assistant, go to HACS -> Integrations.
2. Open the three‑dot menu and choose “Custom repositories”.
3. Add this repository URL and select category “Integration”:

```
https://github.com/kilianyp/hacs-wahoo-kickr-core
```

4. Install “Wahoo Kickr Core” from HACS.
5. Restart Home Assistant.
6. Add the integration via Settings -> Devices & Services.

## Docker on macOS note

If you run Home Assistant in Docker on macOS, mDNS discovery may not work. Use manual setup and consider a host-side TCP forward (e.g., socat) to reach the trainer.
