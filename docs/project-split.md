# Project Split

UniFi Protect Bridge is split into two GitHub repositories.

## Home Assistant Integration

Repository:

<https://github.com/Hovborg/unifi-protect-bridge>

Purpose:

- HACS custom integration
- Home Assistant config flow
- Home Assistant runtime
- Protect webhook provisioning from inside Home Assistant
- sensors, events, diagnostics, services, and optional blueprint examples

Install path:

```text
config/custom_components/unifi_protect_bridge/
```

Install method:

- HACS custom repository: `https://github.com/Hovborg/unifi-protect-bridge`
- Category: **Integration**
- Home Assistant config flow: **Settings -> Devices & services -> Add Integration -> UniFi Protect Bridge**

The CLI is not required for HACS installs. Home Assistant runs this integration
directly and manages UniFi Protect from the config entry.

HACS installs integration repositories under `custom_components/`. Any
top-level blueprint files in this repository are examples and must be imported
or copied separately if an installer wants to use them.

## CLI

Repository:

<https://github.com/Hovborg/unifi-protect-bridge-cli>

Purpose:

- terminal diagnostics
- UniFi Protect login checks
- camera and automation inspection
- bridge diff/apply support
- Home Assistant setup URL, ping, and resync helpers

The CLI is installed separately with Python tooling and is used manually by an
admin or developer. It is not run by Home Assistant.

Current global CLI install:

```bash
pipx install "git+https://github.com/Hovborg/unifi-protect-bridge-cli.git@v0.1.5"
```

Installed command names:

- `upb`
- `unifi-bridge`
- `unifi-protect-bridge`
- `unifi-protect-bridge-cli`

`upb` is the recommended short command.

Typical CLI login flow:

```bash
upb login --save-password
upb cameras
upb automations
upb diff
upb apply
```

## Shared Contract

Both projects must stay aligned on:

- Home Assistant domain: `unifi_protect_bridge`
- Home Assistant resync service: `unifi_protect_bridge.resync`
- Protect automation prefix: `UniFi Protect Bridge:`
- legacy prefix recognition: `HA Protect Bridge:`
- webhook query source naming, such as `source=person`
- supported detection source names

If these values change in the Home Assistant integration, update the CLI repo in
the same work session and release both repositories.
