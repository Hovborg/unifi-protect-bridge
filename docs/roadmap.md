# Roadmap

## Phase 0

- pivot repo toward HACS-compatible Protect bridge
- add webhook-based custom integration scaffold
- normalize person/animal/vehicle/package/motion webhook payloads
- keep the HACS integration and support CLI in one repo while their contracts are tightly coupled

## Phase 1

- test real Protect Alarm Manager webhook payloads from your environment
- harden normalization rules
- add options for filtering, debounce, and event noise control
- keep live CLI provisioning conservative: login check, diff, explicit apply, and HA resync

## Phase 2

- add convenience entities for recent detections / counters / last event
- add docs and blueprints for common automations

## Phase 3

- split the CLI into a separate repo only if it needs an independent release cadence
- publish shared Protect client/planner code as a separate package only if another project needs it
