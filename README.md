# Sitebridge

Private-first scaffold that is now pivoting toward a Home Assistant custom integration for UniFi Protect webhook bridging.

`Sitebridge` is still a working title. The important shift is architectural: if this should be installable via HACS, the Home Assistant bridge must live as a real custom integration under `custom_components/`.

## Current direction

This repository now focuses first on `ha_protect_bridge`:

- a HACS-style Home Assistant custom integration
- webhook ingestion from UniFi Protect Alarm Manager
- automatic Home Assistant events for motion, person, animal, vehicle, package, and related detections
- automatic HA-side webhook generation and setup info inside Home Assistant

Shared CLI/core clients are still useful, but they should be split out later into a separate package/repository if we want both a clean HACS experience and reusable Python tooling.

## What is automatic right now

- the integration generates its own Home Assistant webhook endpoint
- the integration exposes setup info via persistent notification and service
- the integration exposes webhook details via a diagnostic sensor
- HA automations can react directly to typed events like `ha_protect_bridge_person` or `ha_protect_bridge_animal`

## What is not fully automatic yet

I did not find an official Ubiquiti API document for creating Protect Alarm Manager webhook actions automatically. So the supported path is currently:

- auto-generate the HA destination URL
- create the UniFi Protect Webhook action once in Alarm Manager
- let HA handle the rest automatically

## Why split the architecture

Official sources point in this direction:

- HACS expects one integration per repository under `custom_components/`
- UniFi APIs are already split by Ubiquiti into Site Manager, Network, Protect, and Access surfaces
- Home Assistant itself treats UniFi Network and UniFi Protect as separate integrations

## What is implemented now

- HACS metadata via `hacs.json`
- a custom integration scaffold in `custom_components/ha_protect_bridge/`
- webhook setup via Home Assistant webhook config flow
- setup helper service and notification inside Home Assistant
- diagnostic sensor for webhook details
- payload normalization for Protect Alarm Manager motion/object detections
- Home Assistant event firing for automations
- an example automation blueprint

## Event model

Every received webhook fires:

- `ha_protect_bridge_webhook`

Detection-aware payloads also fire:

- `ha_protect_bridge_detection`
- `ha_protect_bridge_motion`
- `ha_protect_bridge_person`
- `ha_protect_bridge_animal`
- `ha_protect_bridge_vehicle`
- `ha_protect_bridge_package`
- and similar typed events when recognized

## Quick start for local development

```bash
cd /path/to/sitebridge
python3.14 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Key docs

- [AI_CONTEXT.md](AI_CONTEXT.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/apis-and-scope.md](docs/apis-and-scope.md)
- [docs/ha-protect-bridge.md](docs/ha-protect-bridge.md)
- [docs/repo-split.md](docs/repo-split.md)
- [docs/legal-and-publishing.md](docs/legal-and-publishing.md)

## Status

This repo is still private. It is now positioned as the HA/Protect bridge first. The shared client/CLI layer should follow as a separate package once the webhook/event model is proven.
