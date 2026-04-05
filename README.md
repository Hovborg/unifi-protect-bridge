# HA Protect Bridge

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=Hovborg&repository=sitebridge&category=integration">
    <img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open in HACS">
  </a>
</p>

<p align="center">
  <a href="https://github.com/Hovborg/sitebridge/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/Hovborg/sitebridge/ci.yml?branch=main&label=CI&style=for-the-badge" alt="CI"></a>
  <a href="https://github.com/Hovborg/sitebridge/actions/workflows/hassfest.yml"><img src="https://img.shields.io/github/actions/workflow/status/Hovborg/sitebridge/hassfest.yml?branch=main&label=Hassfest&style=for-the-badge" alt="Hassfest"></a>
  <img src="https://img.shields.io/badge/HACS-Integration-41BDF5?style=for-the-badge" alt="HACS Integration">
  <img src="https://img.shields.io/badge/Home%20Assistant-2026.3%2B-18BCF2?style=for-the-badge" alt="Home Assistant 2026.3+">
</p>

A Home Assistant custom integration for UniFi Protect that discovers your cameras, creates the needed Protect webhook automations automatically, and exposes detection sensors in Home Assistant.

Instead of building Alarm Manager webhook rules by hand, you install the integration, add your Protect host, and let the bridge provision the Protect side automatically.

> [!TIP]
> The easiest install path is through **HACS** once this repository is public. Click the badge above or follow the short HACS guide below.

## Quick Install

### Install with HACS

1. Open **HACS** in Home Assistant.
2. Open the top-right menu.
3. Select **Custom repositories**.
4. Add this repository URL:
   `https://github.com/Hovborg/sitebridge`
5. Choose category: **Integration**.
6. Click **Add**.
7. Open **HA Protect Bridge** in HACS.
8. Click **Download**.
9. Restart Home Assistant.
10. Go to **Settings -> Devices & services -> Add Integration**.
11. Search for **HA Protect Bridge**.

> [!NOTE]
> If the integration does not show up after restart, refresh the browser and try again.

### Configure it

When you add the integration, Home Assistant asks for:

- `Protect host`
- `Username`
- `Password`
- `Verify SSL certificate`
- `Webhook base URL override` only if Protect cannot reach Home Assistant's normal URL

After setup, the integration will:

- log in to Protect
- inspect cameras and supported detections
- create or refresh managed Protect automations
- register the webhook endpoint in Home Assistant
- expose sensors and events automatically

## What You Get

### Automatic Protect setup

- no manual Alarm Manager webhook rules for the normal detection types
- one managed Protect automation per supported detection source
- automatic re-sync when the integration is refreshed

### Automatic Home Assistant entities

- one bridge status sensor
- one global timestamp sensor per managed detection type
- one per-camera timestamp sensor for each supported detection type
- typed HA events for every incoming detection

Examples:

- `sensor.bridge_status`
- `sensor.last_person`
- `sensor.front_door_last_ring`
- `sensor.driveway_last_vehicle`
- `ha_protect_bridge_person`
- `ha_protect_bridge_package`

## Supported Detections

The current automatic coverage focuses on the normal Protect 7.x camera detections:

- `motion`
- `person`
- `vehicle`
- `animal`
- `package`
- `ring`
- `face_unknown`
- `face_known`
- `face_of_interest`
- `audio_alarm_bark`
- `audio_alarm_burglar`
- `audio_alarm_car_horn`
- `audio_alarm_co`
- `audio_alarm_glass_break`
- `audio_alarm_siren`
- `audio_alarm_smoke`
- `audio_alarm_speak`

## Private Repo Warning

> [!IMPORTANT]
> **HACS cannot use private GitHub repositories.**
>
> HACS install works only when this repository is public.
>
> Official HACS note: <https://www.hacs.xyz/docs/faq/private_repositories/>

While the repo is still private, install it manually instead.

## Manual Install While Private

1. Copy `custom_components/ha_protect_bridge` into your Home Assistant config directory.
2. Make sure the final path is:

```text
config/custom_components/ha_protect_bridge/
```

3. Restart Home Assistant.
4. Go to **Settings -> Devices & services**.
5. Click **Add Integration** and search for **HA Protect Bridge**.

## HACS Links

- HACS download docs: <https://www.hacs.xyz/docs/use/download/download/>
- HACS custom repositories: <https://www.hacs.xyz/docs/faq/custom_repositories/>
- My Home Assistant HACS links: <https://www.hacs.xyz/docs/use/my/>

## Why This Exists

UniFi Protect can already send webhook-based automations, but building and maintaining them manually gets messy fast when you have many cameras and multiple detection types. This integration turns that into a normal Home Assistant config flow and keeps the Protect side aligned automatically.

## Technical Note

> [!IMPORTANT]
> Automatic provisioning uses UniFi Protect's private `/proxy/protect/api/automations` endpoint.
>
> That is what makes zero-manual setup possible, but it also means future Protect updates may require compatibility fixes in this integration.

## Development

```bash
cd /path/to/sitebridge
python3.14 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest
```

## Status

This repository is still being tested privately before public release. The HACS structure is already in place, and the integration is being prepared for a normal public custom-repository install flow.
