# Architecture

## Positioning

Sitebridge is meant to be a thin, explicit bridge between existing systems, not a replacement for Home Assistant, UniFi consoles, or vendor UIs.

## Layers

### 1. CLI surface

Human-facing commands:

- `ha`
- `site`
- `network`
- `protect`
- `bridge`
- `doctor`

### 2. Connectors

Transport-specific clients:

- Home Assistant via `hass-cli` first, direct REST fallback
- UniFi Site Manager via official cloud API
- UniFi Network via official local API
- UniFi Protect via documented/public mechanisms only

### 3. Domain mapping

Normalize objects such as:

- sites
- network devices
- clients
- cameras
- detections
- doors
- Home Assistant entities

### 4. Bridge logic

Cross-system features:

- presence enrichment
- camera event forwarding
- webhook ingestion
- Home Assistant automation helpers
- future policy sync and tagging

## Safety Rules

- Never assume cloud access if local access exists.
- Do not store secrets in code or committed fixtures.
- Prefer read operations before write operations.
- Keep write paths explicit and opt-in.

## First Implementation Order

1. `doctor`
2. read-only `site`
3. read-only `network`
4. read-only `protect`
5. read-only `ha`
6. bridge webhook/event features
7. controlled write operations
