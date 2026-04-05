# HA Protect Bridge

## Goal

Build a Home Assistant custom integration that turns UniFi Protect Alarm Manager webhooks into reliable Home Assistant automation triggers.

## Why not rely only on the built-in Protect integration

The official Home Assistant UniFi Protect integration already provides motion sensors, detected object sensors, thumbnails, clips, and several event entities.

The gap this bridge is trying to close is different:

- direct Alarm Manager webhook ingestion
- a clean automation-first event model
- one place to normalize Protect webhook payloads for person, animal, vehicle, package, motion and related detections
- easier future extension toward cross-system workflows

## What is automatic now

- the Home Assistant webhook endpoint is generated automatically by the integration
- the integration shows the setup info in a persistent notification
- the integration exposes webhook details through a diagnostic sensor
- typed HA events are fired automatically when recognized payloads arrive

## What is not fully automatic yet

Based on the official docs reviewed on 5 April 2026, I did not find an officially documented API for creating Protect Alarm Manager webhook actions automatically from this integration. The supported path in the docs still appears to be creating the Webhook action in the UniFi UI.

## Initial event contract

Generic events:

- `ha_protect_bridge_webhook`
- `ha_protect_bridge_detection`

Typed events:

- `ha_protect_bridge_motion`
- `ha_protect_bridge_person`
- `ha_protect_bridge_animal`
- `ha_protect_bridge_vehicle`
- `ha_protect_bridge_package`
- `ha_protect_bridge_line_crossing`
- additional typed events when recognized from payloads

## Setup helpers inside Home Assistant

- Service: `ha_protect_bridge.show_setup_info`
- Diagnostic sensor with webhook URL/path and supported detection types

The service recreates the setup notification, and the sensor exposes the generated webhook URL/path and supported detection types.

## Example automation shape

```yaml
alias: Protect person detected
triggers:
  - trigger: event
    event_type: ha_protect_bridge_person
actions:
  - action: notify.mobile_app_phone
    data:
      title: Person detected
      message: >-
        {{ trigger.event.data.alarm_name or 'Protect person detection' }}
```

## Important implementation note

The official Ubiquiti webhook article shows a generic JSON example for motion. The broader Protect trigger categories are documented in Alarm Manager docs. That means some payload interpretation for person, animal, package, or vehicle specific events is still an inference from those official docs plus the structured webhook format.

We should therefore:

- prefer POST webhooks
- log unknown payload shapes safely
- keep normalization rules explicit and testable
