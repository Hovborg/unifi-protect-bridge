# Legal And Publishing

This document is operational guidance, not legal advice.

## Current publishing posture

The repository starts closed/private. Open publication comes later.

## Main risks

### 1. Trademark confusion

Avoid product names like:

- `unifi-cli`
- `ubiquiti-cli`
- names that imply official vendor sponsorship

Prefer a neutral project name and state clearly that the project is unofficial.

### 2. API support ambiguity

Not every UniFi product surface is documented equally. Public release should not oversell support or imply stability beyond what is actually documented and tested.

### 3. Secret handling

Public release requires clean examples, no embedded credentials, and documented environment variables.

## Rules before opening the repo

1. Confirm naming is still acceptable.
2. Add a clear disclaimer in `README.md`.
3. Decide on a license intentionally.
4. Ensure no screenshots, docs, or logos imply endorsement.
5. Mark any experimental Protect feature as experimental.
6. Run a final secret scan.

## Proposed public wording

`Sitebridge is an unofficial community project for Home Assistant and official UniFi APIs. It is not affiliated with or endorsed by Ubiquiti.`
