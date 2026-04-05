# Sitebridge

Private-first scaffold for an unofficial CLI and bridge that combines Home Assistant with official UniFi APIs and selected UniFi Protect capabilities.

`Sitebridge` is a working title chosen to avoid shipping a public repo or package name that looks official or reuses Ubiquiti trademarks as the product name.

## Status

Early scaffold. This repo is intended to start closed, stabilize against your environment, and only then move toward a public GitHub release.

## Goals

- Provide a single CLI for Home Assistant, UniFi Site Manager, UniFi Network, and UniFi Protect.
- Support cameras and Protect events from the start, not only network devices.
- Add a clean HA bridge layer for automations, event forwarding, and state enrichment.
- Stay on documented, supported APIs whenever possible.
- Keep branding clearly unofficial.

## Planned Command Areas

- `sitebridge ha ...`
- `sitebridge site ...`
- `sitebridge network ...`
- `sitebridge protect ...`
- `sitebridge bridge ...`
- `sitebridge doctor`

## Principles

- Use official APIs first.
- Avoid undocumented private endpoints by default.
- Keep Home Assistant integration local-first.
- Require explicit configuration for anything security-sensitive.
- Treat publishing, naming, and trademarks as first-class concerns.

## Quick Start

```bash
cd /path/to/sitebridge
cp .env.example .env
uv sync --extra dev
uv run sitebridge doctor
```

If `uv` is not installed yet, create a virtual environment manually:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
sitebridge doctor
```

## Key Docs

- [AI_CONTEXT.md](AI_CONTEXT.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/apis-and-scope.md](docs/apis-and-scope.md)
- [docs/ha-protect-bridge.md](docs/ha-protect-bridge.md)
- [docs/legal-and-publishing.md](docs/legal-and-publishing.md)
- [docs/roadmap.md](docs/roadmap.md)

## Publishing Posture

Do not open this repo publicly until these are true:

- naming has been reviewed for trademark risk
- Protect support is explicitly scoped
- documentation clearly states unofficial status
- CI is green
- secrets handling and config examples are clean
