Læs `/mnt/c/codex_projekts/.ai/infrastructure.md` for delt system-kontekst.
Læs `/mnt/c/codex_projekts/.ai/model-routing.md` for model-valg og token-besparelse.
Læs `/mnt/c/codex_projekts/.ai/conventions.md` for projektstruktur og AI-filkonventioner.

# Sitebridge

## Formål

`Sitebridge` er et nyt standalone projekt i `/mnt/c/codex_projekts/projects/sitebridge`.

Projektet skal ende som en uofficiel CLI og integrationsbro mellem:

- Home Assistant
- UniFi Site Manager API
- UniFi Network API
- UniFi Protect

Målet er både lokal drift i homelabbet og senere mulig publicering på GitHub, når projektet er teknisk og dokumentationsmæssigt modent.

## Vigtige Regler

1. Brug et neutralt produktnavn. Undgå at gøre `UniFi` eller `Ubiquiti` til repo-, package- eller CLI-navn.
2. Beskriv altid projektet som uofficielt/community-drevet, medmindre der kommer skriftlig godkendelse fra Ubiquiti.
3. Brug officielle eller tydeligt dokumenterede API'er først.
4. Hvis en Protect-funktion kun findes via private/ustabile endpoints, skal det markeres eksplicit i docs før implementering.
5. Home Assistant live-adgang på denne Linux-host skal bruge `hass-cli`, aldrig `ha`.
6. Direkte REST-kald til Home Assistant er fallback, hvis MCP og `hass-cli` ikke er nok.
7. Hold hemmeligheder ude af repoet. Brug `.env`, lokale shell-variabler eller secret managers.
8. Repoet starter lukket/private-first. Publicering kommer først efter review af navn, docs, sikkerhed og API-scope.

## Scope

### Inden for scope

- CLI til forespørgsler mod officielle UniFi API'er
- CLI til Home Assistant-funktioner relevante for netværk, presence, kameraer og automations
- Protect/kamera-relaterede kommandoer
- HA-bridge for events, webhooks og state-enrichment
- Dokumentation for lovlig/publicerbar struktur

### Uden for scope indtil videre

- Reverse engineering af private mobil-app endpoints
- Branding der kan forveksles med officiel Ubiquiti software
- Automatisk publicering til GitHub/PyPI uden manuel gennemgang

## Teknisk Retning

- Sprog: Python 3.14
- Pakkestruktur: `src/` layout
- CLI: Typer
- HTTP: `httpx`
- Konfiguration: miljøvariabler fra `.env`
- Kvalitet: `ruff`, `pytest`, GitHub Actions

## Planlagte Moduler

- `sitebridge.cli`
- `sitebridge.config`
- `sitebridge.ha`
- `sitebridge.unifi.site_manager`
- `sitebridge.unifi.network`
- `sitebridge.unifi.protect`
- `sitebridge.bridge`

## Kilder og Research

Brug primært officielle kilder, især:

- Ubiquiti Help Center
- `developer.ui.com`
- Home Assistant officiel dokumentation

Når brugerens spørgsmål handler om "seneste", aktuelle API-muligheder eller support-status, skal der browses først.

## Lokale Kommandoer

```bash
uv sync --extra dev
uv run sitebridge doctor
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Hvis `uv` ikke er installeret:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```
