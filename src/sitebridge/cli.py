from __future__ import annotations

import typer

from sitebridge.config import Settings

app = typer.Typer(
    help="Unofficial CLI scaffold for Home Assistant and official UniFi APIs.",
    no_args_is_help=True,
)

ha_app = typer.Typer(help="Home Assistant commands.")
site_app = typer.Typer(help="UniFi Site Manager commands.")
network_app = typer.Typer(help="UniFi Network commands.")
protect_app = typer.Typer(help="UniFi Protect commands.")
bridge_app = typer.Typer(help="Home Assistant <-> UniFi bridge commands.")

app.add_typer(ha_app, name="ha")
app.add_typer(site_app, name="site")
app.add_typer(network_app, name="network")
app.add_typer(protect_app, name="protect")
app.add_typer(bridge_app, name="bridge")


def _flag(value: str | None) -> str:
    return "set" if value else "missing"


@app.command()
def doctor() -> None:
    """Show local configuration readiness."""
    settings = Settings.load()
    lines = [
        "Sitebridge doctor",
        f"HA_BASE_URL: {_flag(settings.ha_base_url)}",
        f"HA_TOKEN: {_flag(settings.ha_token)}",
        f"UNIFI_SITE_MANAGER_API_KEY: {_flag(settings.unifi_site_manager_api_key)}",
        f"UNIFI_NETWORK_BASE_URL: {_flag(settings.unifi_network_base_url)}",
        f"UNIFI_NETWORK_API_KEY: {_flag(settings.unifi_network_api_key)}",
        f"UNIFI_PROTECT_BASE_URL: {_flag(settings.unifi_protect_base_url)}",
        f"UNIFI_PROTECT_USERNAME: {_flag(settings.unifi_protect_username)}",
        f"UNIFI_PROTECT_PASSWORD: {_flag(settings.unifi_protect_password)}",
        f"UNIFI_PROTECT_API_KEY: {_flag(settings.unifi_protect_api_key)}",
    ]
    typer.echo("\n".join(lines))


@ha_app.command("ping")
def ha_ping() -> None:
    """Placeholder for future Home Assistant connectivity checks."""
    typer.echo("Not implemented yet. Planned transport: hass-cli first, direct API fallback.")


@site_app.command("list")
def site_list() -> None:
    """Placeholder for future UniFi Site Manager listing."""
    typer.echo("Not implemented yet. Planned transport: official Site Manager API.")


@network_app.command("devices")
def network_devices() -> None:
    """Placeholder for future UniFi Network device listing."""
    typer.echo("Not implemented yet. Planned transport: official local UniFi Network API.")


@protect_app.command("cameras")
def protect_cameras() -> None:
    """Placeholder for future UniFi Protect camera listing."""
    typer.echo("Not implemented yet. Planned transport: documented Protect capabilities only.")


@bridge_app.command("plan")
def bridge_plan() -> None:
    """Show the current bridge direction."""
    typer.echo("Bridge layer is planned for HA automations, Protect webhooks, and state enrichment.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
