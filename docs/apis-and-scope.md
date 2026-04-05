# APIs And Scope

Status reviewed against official sources on **5 April 2026**.

## Home Assistant

### Supported direction

- Use `hass-cli` on this Linux host for live operational checks.
- Use Home Assistant REST and native integrations where appropriate.

### Why

- `hass-cli` is the correct external CLI on this host.
- `ha` is primarily for Home Assistant OS / supervised environments, not this Linux host.

## UniFi Site Manager

### Current posture

Supported and should be first-class.

### Reason

Ubiquiti has an official developer portal and a stable Site Manager API.

## UniFi Network

### Current posture

Supported and should be first-class.

### Reason

Ubiquiti documents a local Network API and exposes integrations/API-key workflow in the product UI.

## UniFi Protect

### Current posture

Supported, but with stricter documentation discipline.

### Reason

Protect is strategically important because cameras and event flows are a core requirement. However, the documentation picture is less straightforward than Site Manager and Network, so every feature must be labeled by confidence:

- `official`
- `documented-but-product-local`
- `experimental`

### Rule

Do not silently treat a private or weakly documented Protect endpoint as stable.

## Home Assistant <-> UniFi Protect

### Practical integration paths

- Home Assistant official UniFi Protect integration
- Protect webhooks into Home Assistant webhook-triggered automations
- future bridge helpers that normalize event payloads

## Naming Rule

The repository and package name should remain neutral unless legal/trademark review says otherwise.
