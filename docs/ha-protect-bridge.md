# Home Assistant And UniFi Protect Bridge

## Why this matters

The bridge is one of the strongest reasons to build this project at all. Home Assistant already knows how to automate, notify, and orchestrate. UniFi Protect already knows cameras, detections, doorbells, and event timing. The value is in connecting them cleanly.

## Realistic bridge patterns

### 1. Protect integration already inside Home Assistant

Use the official Home Assistant UniFi Protect integration for:

- camera feeds
- motion and smart detections
- doorbell events
- thumbnails and video clips

This is the fastest path for user-facing automation value.

### 2. Protect webhooks into Home Assistant

Protect can send alert data to external web services. Home Assistant supports webhook-triggered automations. Sitebridge can eventually sit in the middle and:

- validate payloads
- normalize event structure
- enrich events with local metadata
- forward into HA cleanly

### 3. Cross-link with UniFi Network presence

Bridge logic can combine:

- who is home according to UniFi Network
- whether Protect sees motion, people, vehicles, or rings
- whether Home Assistant should escalate, ignore, or notify

## Example future flows

- Unknown motion while all tracked phones are away -> aggressive alerting
- Doorbell event -> HA notification with Protect thumbnail/video
- Car detection when a known device enters Wi-Fi -> suppress duplicate alert
- Camera event at night -> HA lights and siren logic

## Implementation caution

- Prefer existing HA integrations before inventing parallel functionality.
- Use Sitebridge where it adds structure, not where it duplicates mature HA features.
