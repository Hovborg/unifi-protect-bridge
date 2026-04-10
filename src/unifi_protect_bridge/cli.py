from __future__ import annotations

import asyncio
import json
import webbrowser
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode, urlsplit

import aiohttp
import httpx
import typer

from unifi_protect_bridge import __version__
from unifi_protect_bridge.cli_helpers import (
    CliConfigError,
    automation_items,
    automation_prefix_kind,
    build_doctor_report,
    build_integration_report,
    component_module,
    default_repo_path,
    load_json_file,
    manifest_summary,
    parse_query_string,
    redact_automation,
    redact_url,
)
from unifi_protect_bridge.config import Settings
from unifi_protect_bridge.detections import (
    KNOWN_DETECTION_TYPES,
    build_camera_catalog,
    inspect_automations,
    source_label,
)
from unifi_protect_bridge.detections import (
    build_bridge_plan as build_detection_plan,
)

HA_CONFIG_FLOW_URL = (
    "https://my.home-assistant.io/redirect/config_flow_start/?"
    + urlencode({"domain": "unifi_protect_bridge"})
)

app = typer.Typer(
    help="Support CLI for UniFi Protect Bridge.",
    no_args_is_help=True,
)

integration_app = typer.Typer(help="Validate the local Home Assistant integration.")
repo_app = typer.Typer(help="Validate repository configuration and release metadata.")
webhook_app = typer.Typer(help="Debug UniFi Protect webhook payloads.")
automation_app = typer.Typer(help="Render and inspect managed Protect automations.")
bridge_app = typer.Typer(help="Plan bridge-owned Protect automation changes.")
protect_app = typer.Typer(help="Inspect exported UniFi Protect data.")
ha_app = typer.Typer(help="Optional live Home Assistant checks.")

app.add_typer(integration_app, name="integration")
app.add_typer(repo_app, name="repo")
app.add_typer(integration_app, name="hacs")
app.add_typer(webhook_app, name="webhook")
app.add_typer(automation_app, name="automation")
app.add_typer(bridge_app, name="bridge")
app.add_typer(protect_app, name="protect")
app.add_typer(ha_app, name="ha")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"UniFi Protect Bridge {__version__}")
        raise typer.Exit()


VersionOption = Annotated[
    bool,
    typer.Option(
        "--version",
        callback=_version_callback,
        help="Show the CLI version.",
        is_eager=True,
    ),
]
JsonOption = Annotated[bool, typer.Option("--json", help="Print machine-readable JSON.")]
RepoOption = Annotated[
    Path | None,
    typer.Option("--repo", help="Repository path containing custom_components."),
]
ProtectUrlOption = Annotated[
    str | None,
    typer.Option("--protect-url", help="Override UNIFI_PROTECT_BASE_URL."),
]
ProtectUsernameOption = Annotated[
    str | None,
    typer.Option("--username", help="Override UNIFI_PROTECT_USERNAME."),
]
ProtectPasswordOption = Annotated[
    str | None,
    typer.Option("--password", help="Override UNIFI_PROTECT_PASSWORD. Prefer env."),
]
TimeoutOption = Annotated[
    float | None,
    typer.Option("--timeout", help="HTTP timeout in seconds."),
]
VerifySslOption = Annotated[
    bool | None,
    typer.Option("--verify-ssl/--no-verify-ssl", help="Override VERIFY_SSL."),
]


@app.callback()
def root_callback(version: VersionOption = False) -> None:
    """Support CLI for local diagnostics, dry-runs, and release checks."""


@app.command()
def doctor(
    repo: RepoOption = None,
    json_output: JsonOption = False,
) -> None:
    """Show local CLI, environment, and integration readiness."""
    report = build_doctor_report(repo)
    if json_output:
        _echo_json(report)
        return

    typer.echo("UniFi Protect Bridge doctor")
    typer.echo(f"version: {report['version']}")
    typer.echo(f"python: {report['python']}")
    typer.echo(f"Repository: {report['repo']['path']} ({_ok(report['repo']['detected'])})")
    typer.echo(f"integration: {report['integration']['status']}")
    typer.echo("environment:")
    for key, status in report["env"].items():
        typer.echo(f"  {key}: {status}")


@repo_app.command("check")
def repo_check(
    repo: RepoOption = None,
    json_output: JsonOption = False,
) -> None:
    """Run repository, HACS, manifest, and version checks."""
    try:
        report = build_integration_report(repo or default_repo_path())
    except CliConfigError as err:
        _fail(str(err))

    summary = report["summary"]
    if json_output:
        _echo_json(report)
    else:
        passed = summary["ok"] + summary["warn"]
        typer.echo(f"Repository: {report['repo']}")
        typer.echo(f"{passed} passed, {summary['fail']} failed")
        for check in report["checks"]:
            typer.echo(f"[{check['status']}] {check['name']}: {check['detail']}")

    if summary["fail"]:
        raise typer.Exit(1)


@integration_app.command("check")
def integration_check(
    repo: RepoOption = None,
    json_output: JsonOption = False,
) -> None:
    """Validate local HACS/Home Assistant paths and metadata."""
    try:
        report = build_integration_report(repo or default_repo_path())
    except CliConfigError as err:
        _fail(str(err))

    if json_output:
        _echo_json(report)
    else:
        typer.echo(f"Repository: {report['repo']}")
        typer.echo(f"Status: {report['summary']['status']}")
        typer.echo(
            "Checks: "
            f"{report['summary']['ok']} ok, "
            f"{report['summary']['warn']} warn, "
            f"{report['summary']['fail']} fail"
        )
        for check in report["checks"]:
            typer.echo(f"[{check['status']}] {check['name']}: {check['detail']}")

    if report["summary"]["fail"]:
        raise typer.Exit(1)


@integration_app.command("manifest")
def integration_manifest(
    repo: RepoOption = None,
    json_output: JsonOption = False,
) -> None:
    """Print the integration manifest summary."""
    try:
        summary = manifest_summary(repo or default_repo_path())
    except CliConfigError as err:
        _fail(str(err))

    if json_output:
        _echo_json(summary)
        return

    for key, value in summary.items():
        typer.echo(f"{key}: {value}")


@bridge_app.command("sources")
def bridge_sources(
    json_output: JsonOption = False,
) -> None:
    """List detection sources supported by the bridge."""
    sources = [
        {"source": source, "label": source_label(source)}
        for source in KNOWN_DETECTION_TYPES
    ]
    if json_output:
        _echo_json({"sources": sources})
        return

    for item in sources:
        typer.echo(f"{item['source']}: {item['label']}")


@protect_app.command("cameras")
def protect_cameras(
    bootstrap: Annotated[
        Path | None,
        typer.Option(
            "--bootstrap",
            "--bootstrap-json",
            help="UniFi Protect bootstrap JSON file. No live Protect login is performed.",
        ),
    ] = None,
    connect: Annotated[
        bool,
        typer.Option("--connect", help="Connect to UniFi Protect using env/options."),
    ] = False,
    protect_url: ProtectUrlOption = None,
    username: ProtectUsernameOption = None,
    password: ProtectPasswordOption = None,
    timeout: TimeoutOption = None,
    verify_ssl: VerifySslOption = None,
    repo: RepoOption = None,
    json_output: JsonOption = False,
    show_ids: Annotated[
        bool,
        typer.Option("--show-ids", help="Show camera IDs and MAC addresses."),
    ] = False,
) -> None:
    """Summarize cameras and supported detections from exported bootstrap JSON."""
    try:
        if connect:
            catalog, _automations = _load_live_protect_snapshot(
                repo=repo,
                protect_url=protect_url,
                username=username,
                password=password,
                timeout=timeout,
                verify_ssl=verify_ssl,
                include_automations=False,
            )
        elif bootstrap:
            catalog = build_camera_catalog(load_json_file(bootstrap))
        else:
            _fail("Pass --bootstrap for offline mode, or --connect for live Protect.")
    except CliConfigError as err:
        _fail(str(err))

    if json_output:
        _echo_json(_public_camera_catalog(catalog, show_ids=show_ids))
        return

    typer.echo(f"NVR: {catalog.get('nvr_name') or 'unknown'}")
    typer.echo(f"Cameras: {len(catalog.get('cameras') or [])}")
    typer.echo(f"Managed sources: {', '.join(catalog.get('managed_sources') or []) or 'none'}")
    for camera in catalog.get("cameras") or []:
        typer.echo(
            "- "
            f"{camera['name']} ({camera['model']}): "
            f"{', '.join(camera['supported_sources']) or 'no detections'}"
        )


@protect_app.command("login-check")
def protect_login_check(
    connect: Annotated[
        bool,
        typer.Option("--connect", help="Connect to UniFi Protect using env/options."),
    ] = False,
    protect_url: ProtectUrlOption = None,
    username: ProtectUsernameOption = None,
    password: ProtectPasswordOption = None,
    timeout: TimeoutOption = None,
    verify_ssl: VerifySslOption = None,
    repo: RepoOption = None,
    json_output: JsonOption = False,
) -> None:
    """Verify Protect credentials by logging in and reading bootstrap."""
    if not connect:
        _fail("Pass --connect to perform a live Protect login check.")

    try:
        catalog, _automations = _load_live_protect_snapshot(
            repo=repo,
            protect_url=protect_url,
            username=username,
            password=password,
            timeout=timeout,
            verify_ssl=verify_ssl,
            include_automations=False,
        )
    except CliConfigError as err:
        _fail(str(err))

    result = {
        "ok": True,
        "nvr_name": catalog.get("nvr_name"),
        "camera_count": len(catalog.get("cameras") or []),
    }
    if json_output:
        _echo_json(result)
        return

    typer.echo("Protect login: ok")
    typer.echo(f"NVR: {result['nvr_name'] or 'unknown'}")
    typer.echo(f"Cameras: {result['camera_count']}")


@protect_app.command("automations")
def protect_automations(
    automations_file: Annotated[
        Path | None,
        typer.Option(
            "--file",
            "--automations-json",
            "-f",
            help="Protect automations JSON list or object with an automations list.",
        ),
    ] = None,
    connect: Annotated[
        bool,
        typer.Option("--connect", help="Connect to UniFi Protect using env/options."),
    ] = False,
    protect_url: ProtectUrlOption = None,
    username: ProtectUsernameOption = None,
    password: ProtectPasswordOption = None,
    timeout: TimeoutOption = None,
    verify_ssl: VerifySslOption = None,
    repo: RepoOption = None,
    json_output: JsonOption = False,
) -> None:
    """Inspect exported Protect automations for bridge ownership and duplicates."""
    try:
        if connect:
            _catalog, automations = _load_live_protect_snapshot(
                repo=repo,
                protect_url=protect_url,
                username=username,
                password=password,
                timeout=timeout,
                verify_ssl=verify_ssl,
                include_automations=True,
            )
        elif automations_file:
            automations = automation_items(load_json_file(automations_file))
        else:
            _fail("Pass --file for offline mode, or --connect for live Protect.")
        report = inspect_automations(automations)
    except CliConfigError as err:
        _fail(str(err))

    if json_output:
        _echo_json(report)
        return

    typer.echo(f"Automations: {report['total']}")
    typer.echo(f"Bridge-managed: {report['managed_total']}")
    typer.echo(f"User-owned/ignored: {report['user_total']}")
    if report["duplicate_sources"]:
        for source in report["duplicate_sources"]:
            duplicate_count = len(report["duplicates"][source])
            noun = "duplicate" if duplicate_count == 1 else "duplicates"
            typer.echo(f"{source}: {duplicate_count} {noun}")
    else:
        typer.echo("Duplicate managed sources: none")


@webhook_app.command("normalize")
def webhook_normalize(
    payload_file: Annotated[
        Path,
        typer.Option("--file", "-f", help="JSON webhook payload file."),
    ],
    query: Annotated[
        str | None,
        typer.Option("--query", "-q", help="Optional URL query string, e.g. 'source=person'."),
    ] = None,
    repo: RepoOption = None,
    json_output: JsonOption = False,
    show_ids: Annotated[
        bool,
        typer.Option("--show-ids", help="Show device/camera identifiers in output."),
    ] = False,
) -> None:
    """Normalize a saved UniFi Protect webhook payload without exposing raw data."""
    try:
        payload = load_json_file(payload_file)
        normalize = component_module(
            repo or default_repo_path(),
            "normalize",
        ).normalize_webhook_payload
    except CliConfigError as err:
        _fail(str(err))

    normalized = normalize(payload, parse_query_string(query))
    public = _public_normalized_payload(normalized, show_ids=show_ids)

    if json_output:
        _echo_json(public)
        return

    typer.echo(f"primary_detection_type: {public['primary_detection_type']}")
    typer.echo(f"detection_types: {', '.join(public['detection_types']) or 'none'}")
    typer.echo(f"device_count: {public['device_count']}")
    if show_ids:
        typer.echo(f"device_ids: {', '.join(public['device_ids']) or 'none'}")
    typer.echo(f"timestamp_iso: {public['timestamp_iso']}")
    typer.echo(f"event_types: {', '.join(public['event_types']) or 'none'}")


@automation_app.command("render")
def automation_render(
    source: Annotated[str, typer.Argument(help="Detection source, e.g. person.")],
    webhook_url: Annotated[
        str,
        typer.Option("--webhook-url", help="Home Assistant webhook URL."),
    ],
    device: Annotated[
        list[str] | None,
        typer.Option("--device", "-d", help="Protect camera MAC/device id. Repeatable."),
    ] = None,
    repo: RepoOption = None,
    json_output: JsonOption = False,
    show_url: Annotated[
        bool,
        typer.Option("--show-url", help="Show the full webhook URL instead of redacting it."),
    ] = False,
) -> None:
    """Render the Protect automation payload the bridge would create."""
    payload = _render_payload(repo or default_repo_path(), source, device or [], webhook_url)
    public_payload = redact_automation(payload, show_urls=show_url)

    if json_output:
        _echo_json(public_payload)
        return

    metadata = public_payload["actions"][0]["metadata"]
    typer.echo(f"name: {public_payload['name']}")
    typer.echo(f"source: {source}")
    typer.echo(f"device_count: {len(public_payload['sources'])}")
    typer.echo(f"method: {metadata['method']}")
    typer.echo(f"use_thumbnail: {metadata['useThumbnail']}")
    typer.echo(f"url: {metadata['url']}")


@automation_app.command("inspect")
def automation_inspect(
    automations_file: Annotated[
        Path,
        typer.Option("--file", "-f", help="JSON file from Protect automations export/API."),
    ],
    repo: RepoOption = None,
    json_output: JsonOption = False,
    show_urls: Annotated[
        bool,
        typer.Option("--show-urls", help="Show full webhook URLs instead of redacting them."),
    ] = False,
) -> None:
    """Inspect exported Protect automations for managed entries and duplicates."""
    try:
        automations = automation_items(load_json_file(automations_file))
        payloads = component_module(repo or default_repo_path(), "automation_payloads")
    except CliConfigError as err:
        _fail(str(err))

    report = _automation_inspection_report(automations, payloads, show_urls=show_urls)

    if json_output:
        _echo_json(report)
        return

    typer.echo(f"total: {report['total']}")
    typer.echo(f"managed: {report['managed_count']}")
    typer.echo(f"User-owned/ignored: {report['unmanaged_count']}")
    typer.echo(f"unmanaged: {report['unmanaged_count']}")
    for item in report["sources"]:
        typer.echo(
            f"{item['source']}: keep {item['kept']['id']} "
            f"({item['kept']['prefix']}), duplicates={len(item['duplicates'])}"
        )
        if item["duplicates"]:
            duplicate_count = len(item["duplicates"])
            typer.echo(
                f"{item['source']}: {duplicate_count} "
                f"duplicate{'' if duplicate_count == 1 else 's'}"
            )


@bridge_app.command("plan")
def bridge_plan(
    source: Annotated[
        str | None,
        typer.Argument(help="Detection source, e.g. person. Optional with --bootstrap."),
    ] = None,
    webhook_url: Annotated[
        str | None,
        typer.Option("--webhook-url", help="Home Assistant webhook URL."),
    ] = None,
    bootstrap_file: Annotated[
        Path | None,
        typer.Option("--bootstrap", "--bootstrap-json", "-b", help="Protect bootstrap JSON file."),
    ] = None,
    device: Annotated[
        list[str] | None,
        typer.Option("--device", "-d", help="Protect camera MAC/device id. Repeatable."),
    ] = None,
    repo: RepoOption = None,
    json_output: JsonOption = False,
) -> None:
    """Show a dry-run plan without changing Protect or Home Assistant."""
    if bootstrap_file is not None:
        try:
            catalog = build_camera_catalog(load_json_file(bootstrap_file))
        except CliConfigError as err:
            _fail(str(err))
        plan_items = build_detection_plan(catalog, webhook_configured=bool(webhook_url))
        if source:
            plan_items = [item for item in plan_items if item["source"] == source]
        plan = {
            "action": "plan_bridge_owned_automations",
            "dry_run": True,
            "webhook_configured": bool(webhook_url),
            "nvr_name": catalog.get("nvr_name"),
            "camera_count": len(catalog.get("cameras") or []),
            "automation_count": len(plan_items),
            "automations": plan_items,
            "note": "No Protect changes were made. A future apply command must require --yes.",
        }

        if json_output:
            _echo_json(plan)
            return

        typer.echo("Dry run only. No Protect changes were made.")
        typer.echo(f"Webhook URL: {'set' if webhook_url else 'missing'}")
        typer.echo(f"nvr: {plan['nvr_name'] or 'unknown'}")
        typer.echo(f"cameras: {plan['camera_count']}")
        for item in plan_items:
            typer.echo(
                f"{item['source']}: {item['camera_count']} "
                f"camera{'' if item['camera_count'] == 1 else 's'} "
                f"({item['automation_name']})"
            )
        return

    if not source:
        _fail("Pass a source argument, or use --bootstrap for a full offline plan.")
    if not webhook_url:
        _fail("Pass --webhook-url when rendering a source-specific automation.")
    payload = _render_payload(repo or default_repo_path(), source, device or [], webhook_url)
    plan = {
        "action": "create_or_replace_bridge_owned_automation",
        "dry_run": True,
        "source": source,
        "device_count": len(payload["sources"]),
        "automation": redact_automation(payload),
        "note": "No Protect changes were made. A future apply command must require --yes.",
    }

    if json_output:
        _echo_json(plan)
        return

    typer.echo("Dry run only. No Protect changes were made.")
    typer.echo(f"action: {plan['action']}")
    typer.echo(f"source: {source}")
    typer.echo(f"device_count: {plan['device_count']}")
    typer.echo(f"name: {plan['automation']['name']}")


@bridge_app.command("diff")
def bridge_diff(
    webhook_url: Annotated[
        str,
        typer.Option("--webhook-url", help="Home Assistant webhook URL."),
    ],
    bootstrap_file: Annotated[
        Path | None,
        typer.Option("--bootstrap", "--bootstrap-json", "-b", help="Protect bootstrap JSON file."),
    ] = None,
    automations_file: Annotated[
        Path | None,
        typer.Option("--automations", "--automations-json", help="Protect automations JSON file."),
    ] = None,
    connect: Annotated[
        bool,
        typer.Option("--connect", help="Connect to UniFi Protect using env/options."),
    ] = False,
    protect_url: ProtectUrlOption = None,
    username: ProtectUsernameOption = None,
    password: ProtectPasswordOption = None,
    timeout: TimeoutOption = None,
    verify_ssl: VerifySslOption = None,
    repo: RepoOption = None,
    json_output: JsonOption = False,
    show_ids: Annotated[
        bool,
        typer.Option("--show-ids", help="Show camera IDs/MACs in JSON payloads."),
    ] = False,
    show_urls: Annotated[
        bool,
        typer.Option("--show-urls", help="Show full webhook URLs in JSON payloads."),
    ] = False,
) -> None:
    """Diff desired bridge-owned automations against Protect state."""
    try:
        plan = _build_bridge_diff_plan(
            repo=repo,
            webhook_url=webhook_url,
            bootstrap_file=bootstrap_file,
            automations_file=automations_file,
            connect=connect,
            protect_url=protect_url,
            username=username,
            password=password,
            timeout=timeout,
            verify_ssl=verify_ssl,
        )
    except CliConfigError as err:
        _fail(str(err))

    public_plan = _public_bridge_plan(plan, show_ids=show_ids, show_urls=show_urls)
    if json_output:
        _echo_json(public_plan)
        return

    _echo_plan_summary(public_plan)


@bridge_app.command("apply")
def bridge_apply(
    webhook_url: Annotated[
        str,
        typer.Option("--webhook-url", help="Home Assistant webhook URL."),
    ],
    connect: Annotated[
        bool,
        typer.Option("--connect", help="Connect to UniFi Protect using env/options."),
    ] = False,
    protect_url: ProtectUrlOption = None,
    username: ProtectUsernameOption = None,
    password: ProtectPasswordOption = None,
    timeout: TimeoutOption = None,
    verify_ssl: VerifySslOption = None,
    repo: RepoOption = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Apply bridge-owned automation changes."),
    ] = False,
    max_deletes: Annotated[
        int,
        typer.Option("--max-deletes", help="Maximum Protect automations to delete."),
    ] = 5,
    allow_custom_webhook_url: Annotated[
        bool,
        typer.Option(
            "--allow-custom-webhook-url",
            help="Allow webhook URLs outside /api/webhook/.",
        ),
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Create/update/delete bridge-owned Protect webhook automations."""
    if not connect:
        _fail("Pass --connect to apply directly to UniFi Protect.")
    if not yes:
        _fail("Pass --yes to apply bridge-owned Protect automation changes.")
    if not allow_custom_webhook_url and "/api/webhook/" not in urlsplit(webhook_url).path:
        _fail("Webhook URL must contain /api/webhook/, or pass --allow-custom-webhook-url.")

    try:
        plan = _build_bridge_diff_plan(
            repo=repo,
            webhook_url=webhook_url,
            bootstrap_file=None,
            automations_file=None,
            connect=True,
            protect_url=protect_url,
            username=username,
            password=password,
            timeout=timeout,
            verify_ssl=verify_ssl,
        )
        plan_mod = component_module(repo or default_repo_path(), "automation_plan")
        delete_count = plan_mod.plan_delete_count(plan)
        if plan_mod.plan_has_missing_delete_ids(plan):
            _fail("Plan contains bridge-owned deletes without automation ids.")
        if delete_count > max_deletes:
            _fail(f"Plan would delete {delete_count} automations; increase --max-deletes to allow.")
        result = _apply_live_bridge_plan(
            repo=repo,
            plan=plan,
            protect_url=protect_url,
            username=username,
            password=password,
            timeout=timeout,
            verify_ssl=verify_ssl,
        )
    except CliConfigError as err:
        _fail(str(err))

    if json_output:
        _echo_json(result)
        return

    typer.echo("Applied bridge-owned Protect automation changes.")
    for key, value in result["summary"].items():
        typer.echo(f"{key}: {value}")


@ha_app.command("ping")
def ha_ping(
    base_url: Annotated[
        str | None,
        typer.Option("--base-url", help="Home Assistant base URL. Defaults to HA_BASE_URL."),
    ] = None,
    token: Annotated[
        str | None,
        typer.Option("--token", help="Long-lived access token. Defaults to HA_TOKEN."),
    ] = None,
    timeout: Annotated[
        float | None,
        typer.Option("--timeout", help="HTTP timeout in seconds."),
    ] = None,
    verify_ssl: Annotated[
        bool | None,
        typer.Option("--verify-ssl/--no-verify-ssl", help="Override VERIFY_SSL."),
    ] = None,
    json_output: JsonOption = False,
) -> None:
    """Check Home Assistant's REST API with an explicit token."""
    settings = Settings.load()
    resolved_base_url = base_url or settings.ha_base_url
    resolved_token = token or settings.ha_token
    resolved_timeout = timeout or float(settings.request_timeout_seconds)
    resolved_verify_ssl = settings.verify_ssl if verify_ssl is None else verify_ssl
    if not resolved_base_url:
        _fail("Missing Home Assistant base URL. Pass --base-url or set HA_BASE_URL.")
    if not resolved_token:
        _fail("Missing Home Assistant token. Pass --token or set HA_TOKEN.")

    api_url = _ha_api_url(resolved_base_url)
    try:
        response = httpx.get(
            api_url,
            headers={
                "Authorization": f"Bearer {resolved_token}",
                "Accept": "application/json",
            },
            timeout=resolved_timeout,
            verify=resolved_verify_ssl,
        )
    except httpx.HTTPError as err:
        report = {
            "ok": False,
            "base_url": redact_url(resolved_base_url),
            "error": str(err),
        }
        if json_output:
            _echo_json(report)
        else:
            typer.echo(f"Home Assistant unreachable: {err}")
        raise typer.Exit(1) from err

    report = {
        "ok": response.is_success,
        "base_url": redact_url(resolved_base_url),
        "status_code": response.status_code,
    }
    if json_output:
        _echo_json(report)
    else:
        typer.echo(
            f"Home Assistant {'reachable' if response.is_success else 'returned an error'}: "
            f"{response.status_code}"
        )

    if not response.is_success:
        raise typer.Exit(1)


@ha_app.command("setup-url")
def ha_setup_url(
    open_browser: Annotated[
        bool,
        typer.Option("--open", help="Open the setup URL in the default browser."),
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Print the Home Assistant config-flow URL for first setup."""
    result = {
        "url": HA_CONFIG_FLOW_URL,
        "domain": "unifi_protect_bridge",
        "note": "Use Home Assistant's config flow for first setup, then run ha resync --yes.",
    }
    if open_browser:
        webbrowser.open(HA_CONFIG_FLOW_URL)
        result["opened"] = True
    else:
        result["opened"] = False

    if json_output:
        _echo_json(result)
        return

    typer.echo("Open this Home Assistant setup URL:")
    typer.echo(HA_CONFIG_FLOW_URL)
    typer.echo("After the entry exists, run: unifi-protect-bridge ha resync --yes")


@ha_app.command("resync")
def ha_resync(
    base_url: Annotated[
        str | None,
        typer.Option("--base-url", help="Home Assistant base URL. Defaults to HA_BASE_URL."),
    ] = None,
    token: Annotated[
        str | None,
        typer.Option("--token", help="Long-lived access token. Defaults to HA_TOKEN."),
    ] = None,
    entry_id: Annotated[
        str | None,
        typer.Option("--entry-id", help="Optional UniFi Protect Bridge config entry id."),
    ] = None,
    timeout: Annotated[
        float | None,
        typer.Option("--timeout", help="HTTP timeout in seconds."),
    ] = None,
    verify_ssl: Annotated[
        bool | None,
        typer.Option("--verify-ssl/--no-verify-ssl", help="Override VERIFY_SSL."),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Confirm calling the Home Assistant resync service."),
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Call Home Assistant's bridge resync service after explicit confirmation."""
    if not yes:
        _fail("Pass --yes to call unifi_protect_bridge.resync.")

    settings = Settings.load()
    resolved_base_url = base_url or settings.ha_base_url
    resolved_token = token or settings.ha_token
    resolved_timeout = timeout or float(settings.request_timeout_seconds)
    resolved_verify_ssl = settings.verify_ssl if verify_ssl is None else verify_ssl
    if not resolved_base_url:
        _fail("Missing Home Assistant base URL. Pass --base-url or set HA_BASE_URL.")
    if not resolved_token:
        _fail("Missing Home Assistant token. Pass --token or set HA_TOKEN.")

    api_url = _ha_service_url(
        resolved_base_url,
        "unifi_protect_bridge",
        "resync",
    )
    payload = {"entry_id": entry_id} if entry_id else {}
    try:
        response = httpx.post(
            api_url,
            headers={
                "Authorization": f"Bearer {resolved_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=resolved_timeout,
            verify=resolved_verify_ssl,
        )
    except httpx.HTTPError as err:
        report = {
            "ok": False,
            "base_url": redact_url(resolved_base_url),
            "service": "unifi_protect_bridge.resync",
            "error": str(err),
        }
        if json_output:
            _echo_json(report)
        else:
            typer.echo(f"Home Assistant resync failed: {err}")
        raise typer.Exit(1) from err

    report = {
        "ok": response.is_success,
        "base_url": redact_url(resolved_base_url),
        "service": "unifi_protect_bridge.resync",
        "status_code": response.status_code,
    }
    if json_output:
        _echo_json(report)
    else:
        typer.echo(f"Called unifi_protect_bridge.resync: {response.status_code}")

    if not response.is_success:
        raise typer.Exit(1)


def _build_bridge_diff_plan(
    *,
    repo: Path | None,
    webhook_url: str,
    bootstrap_file: Path | None,
    automations_file: Path | None,
    connect: bool,
    protect_url: str | None,
    username: str | None,
    password: str | None,
    timeout: float | None,
    verify_ssl: bool | None,
) -> dict[str, Any]:
    repo_path = repo or default_repo_path()
    if connect:
        catalog, automations = _load_live_protect_snapshot(
            repo=repo_path,
            protect_url=protect_url,
            username=username,
            password=password,
            timeout=timeout,
            verify_ssl=verify_ssl,
            include_automations=True,
        )
    else:
        if not bootstrap_file or not automations_file:
            raise CliConfigError(
                "Pass --bootstrap and --automations for offline mode, or --connect."
            )
        catalog_builder = component_module(repo_path, "catalog").build_camera_catalog
        catalog = catalog_builder(load_json_file(bootstrap_file))
        automations = automation_items(load_json_file(automations_file))

    plan_builder = component_module(repo_path, "automation_plan").build_managed_automation_plan
    return plan_builder(catalog, automations, webhook_url)


def _load_live_protect_snapshot(
    *,
    repo: Path | None,
    protect_url: str | None,
    username: str | None,
    password: str | None,
    timeout: float | None,
    verify_ssl: bool | None,
    include_automations: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    settings = Settings.load()
    resolved_url = protect_url or settings.unifi_protect_base_url
    resolved_username = username or settings.unifi_protect_username
    resolved_password = password or settings.unifi_protect_password
    resolved_verify_ssl = settings.verify_ssl if verify_ssl is None else verify_ssl
    resolved_timeout = _resolve_timeout(timeout, settings.request_timeout_seconds)

    if not resolved_url or not resolved_username or not resolved_password:
        raise CliConfigError(
            "Set UNIFI_PROTECT_BASE_URL, UNIFI_PROTECT_USERNAME, and "
            "UNIFI_PROTECT_PASSWORD, or pass --protect-url, --username, and --password."
        )

    return asyncio.run(
        _async_load_live_protect_snapshot(
            repo=repo or default_repo_path(),
            protect_url=resolved_url,
            username=resolved_username,
            password=resolved_password,
            timeout=resolved_timeout,
            verify_ssl=resolved_verify_ssl,
            include_automations=include_automations,
        )
    )


async def _async_load_live_protect_snapshot(
    *,
    repo: Path,
    protect_url: str,
    username: str,
    password: str,
    timeout: float,
    verify_ssl: bool,
    include_automations: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    protect_api = component_module(repo, "protect_api")
    catalog_builder = component_module(repo, "catalog").build_camera_catalog
    try:
        client = protect_api.ProtectApiClient(
            protect_url,
            username,
            password,
            verify_ssl,
            timeout,
        )
    except protect_api.ProtectApiError as err:
        raise CliConfigError(str(err)) from err
    try:
        await client.async_setup()
        bootstrap = await client.async_get_bootstrap()
        automations = await client.async_get_automations() if include_automations else []
    except (protect_api.ProtectApiError, aiohttp.ClientError, TimeoutError, OSError) as err:
        raise CliConfigError(f"Protect request failed: {err}") from err
    finally:
        await client.async_close()
    return catalog_builder(bootstrap), automations


def _apply_live_bridge_plan(
    *,
    repo: Path | None,
    plan: Mapping[str, Any],
    protect_url: str | None,
    username: str | None,
    password: str | None,
    timeout: float | None,
    verify_ssl: bool | None,
) -> dict[str, Any]:
    settings = Settings.load()
    resolved_url = protect_url or settings.unifi_protect_base_url
    resolved_username = username or settings.unifi_protect_username
    resolved_password = password or settings.unifi_protect_password
    resolved_verify_ssl = settings.verify_ssl if verify_ssl is None else verify_ssl
    resolved_timeout = _resolve_timeout(timeout, settings.request_timeout_seconds)

    if not resolved_url or not resolved_username or not resolved_password:
        raise CliConfigError(
            "Set UNIFI_PROTECT_BASE_URL, UNIFI_PROTECT_USERNAME, and "
            "UNIFI_PROTECT_PASSWORD, or pass --protect-url, --username, and --password."
        )

    return asyncio.run(
        _async_apply_live_bridge_plan(
            repo=repo or default_repo_path(),
            plan=plan,
            protect_url=resolved_url,
            username=resolved_username,
            password=resolved_password,
            timeout=resolved_timeout,
            verify_ssl=resolved_verify_ssl,
        )
    )


async def _async_apply_live_bridge_plan(
    *,
    repo: Path,
    plan: Mapping[str, Any],
    protect_url: str,
    username: str,
    password: str,
    timeout: float,
    verify_ssl: bool,
) -> dict[str, Any]:
    protect_api = component_module(repo, "protect_api")
    try:
        client = protect_api.ProtectApiClient(
            protect_url,
            username,
            password,
            verify_ssl,
            timeout,
        )
    except protect_api.ProtectApiError as err:
        raise CliConfigError(str(err)) from err
    applied = {
        "create": 0,
        "replace": 0,
        "delete_duplicate": 0,
        "delete_stale": 0,
        "keep": 0,
    }
    try:
        await client.async_setup()
        for action in plan.get("actions") or []:
            action_type = action.get("action")
            if action_type == "keep":
                applied["keep"] += 1
            elif action_type == "create":
                await client.async_create_automation(action["payload"])
                applied["create"] += 1
            elif action_type == "replace":
                for automation_id in action.get("delete_ids") or []:
                    await client.async_delete_automation(automation_id)
                await client.async_create_automation(action["payload"])
                applied["replace"] += 1
            elif action_type in {"delete_duplicate", "delete_stale"}:
                await client.async_delete_automation(action["id"])
                applied[action_type] += 1
    except (protect_api.ProtectApiError, aiohttp.ClientError, TimeoutError, OSError) as err:
        raise CliConfigError(f"Protect request failed: {err}") from err
    finally:
        await client.async_close()

    return {
        "ok": True,
        "summary": applied,
    }


def _resolve_timeout(timeout: float | None, default_timeout: int) -> float:
    resolved_timeout = float(default_timeout if timeout is None else timeout)
    if resolved_timeout <= 0:
        raise CliConfigError("Timeout must be greater than 0.")
    return resolved_timeout


def _render_payload(
    repo: Path,
    source: str,
    devices: list[str],
    webhook_url: str,
) -> dict[str, Any]:
    if not devices:
        _fail("At least one --device value is required.")

    try:
        payloads = component_module(repo, "automation_payloads")
        return payloads.build_managed_automation_payload(source, devices, webhook_url)
    except CliConfigError as err:
        _fail(str(err))
    except ValueError as err:
        _fail(str(err))


def _automation_inspection_report(
    automations: list[dict[str, Any]],
    payloads: Any,
    *,
    show_urls: bool,
) -> dict[str, Any]:
    grouped = payloads.group_managed_automations(automations)
    managed_ids = {id(item) for items in grouped.values() for item in items}
    sources = []

    for source, items in sorted(grouped.items()):
        kept = items[0]
        duplicates = items[1:]
        sources.append(
            {
                "source": source,
                "kept": _automation_ref(kept, show_urls=show_urls),
                "duplicates": [
                    _automation_ref(item, show_urls=show_urls) for item in duplicates
                ],
            }
        )

    unmanaged = [item for item in automations if id(item) not in managed_ids]
    return {
        "total": len(automations),
        "managed_count": len(automations) - len(unmanaged),
        "unmanaged_count": len(unmanaged),
        "source_count": len(sources),
        "sources": sources,
    }


def _automation_ref(
    automation: dict[str, Any],
    *,
    show_urls: bool,
) -> dict[str, Any]:
    redacted = redact_automation(automation, show_urls=show_urls)
    return {
        "id": redacted.get("id") or "<missing-id>",
        "name": redacted.get("name"),
        "prefix": automation_prefix_kind(redacted.get("name")),
        "enabled": bool(redacted.get("enable", True)),
        "actions": redacted.get("actions") or [],
    }


def _public_bridge_plan(
    plan: Mapping[str, Any],
    *,
    show_ids: bool,
    show_urls: bool,
) -> dict[str, Any]:
    public_actions = []
    for action in plan.get("actions") or []:
        public_action = dict(action)
        if "payload" in public_action and isinstance(public_action["payload"], Mapping):
            public_action["payload"] = _redact_plan_payload(
                public_action["payload"],
                show_ids=show_ids,
                show_urls=show_urls,
            )
        public_actions.append(public_action)

    return {
        "dry_run": bool(plan.get("dry_run", True)),
        "nvr_name": plan.get("nvr_name"),
        "camera_count": plan.get("camera_count"),
        "managed_source_count": plan.get("managed_source_count"),
        "ignored_user_owned": plan.get("ignored_user_owned"),
        "summary": dict(plan.get("summary") or {}),
        "actions": public_actions,
    }


def _redact_plan_payload(
    payload: Mapping[str, Any],
    *,
    show_ids: bool,
    show_urls: bool,
) -> dict[str, Any]:
    redacted = redact_automation(payload, show_urls=show_urls)
    if not show_ids:
        for source in redacted.get("sources") or []:
            if isinstance(source, dict) and "device" in source:
                source["device"] = "<device_id>"
    return redacted


def _echo_plan_summary(plan: Mapping[str, Any]) -> None:
    typer.echo("No Protect changes were made.")
    typer.echo(f"NVR: {plan.get('nvr_name') or 'unknown'}")
    typer.echo(f"Cameras: {plan.get('camera_count')}")
    summary = plan.get("summary") or {}
    for action in (
        "keep",
        "create",
        "replace",
        "delete_duplicate",
        "delete_stale",
        "ignored_user_owned",
    ):
        typer.echo(f"{action}: {summary.get(action, 0)}")
    for action in plan.get("actions") or []:
        action_type = action.get("action")
        source = action.get("source")
        if action_type == "keep":
            typer.echo(f"keep: {source}")
        elif action_type in {"create", "replace", "delete_duplicate", "delete_stale"}:
            typer.echo(f"{action_type}: {source}")


def _public_camera_catalog(catalog: Mapping[str, Any], *, show_ids: bool) -> dict[str, Any]:
    cameras = []
    for camera in catalog.get("cameras") or []:
        item = {
            "name": camera.get("name"),
            "model": camera.get("model"),
            "is_doorbell": bool(camera.get("is_doorbell")),
            "supported_sources": list(camera.get("supported_sources") or []),
        }
        if show_ids:
            item["camera_id"] = camera.get("camera_id")
            item["device_mac"] = camera.get("device_mac")
        cameras.append(item)

    return {
        "nvr_id": catalog.get("nvr_id") if show_ids else None,
        "nvr_name": catalog.get("nvr_name"),
        "managed_sources": list(catalog.get("managed_sources") or []),
        "cameras": cameras,
    }


def _public_normalized_payload(
    normalized: Mapping[str, Any],
    *,
    show_ids: bool,
) -> dict[str, Any]:
    device_ids = list(normalized.get("device_ids") or [])
    public = {
        "alarm_name": normalized.get("alarm_name"),
        "detection_types": list(normalized.get("detection_types") or []),
        "primary_detection_type": normalized.get("primary_detection_type"),
        "device_count": len(device_ids),
        "timestamp_ms": normalized.get("timestamp_ms"),
        "timestamp_iso": normalized.get("timestamp_iso"),
        "source_values": list(normalized.get("source_values") or []),
        "event_types": list(normalized.get("event_types") or []),
    }
    if show_ids:
        public["device_ids"] = device_ids
    return public


def _echo_json(value: Any) -> None:
    typer.echo(json.dumps(value, indent=2, sort_keys=True))


def _ha_api_url(base_url: str) -> str:
    return f"{_ha_base_url(base_url)}/api/"


def _ha_service_url(base_url: str, domain: str, service: str) -> str:
    return f"{_ha_base_url(base_url)}/api/services/{domain}/{service}"


def _ha_base_url(base_url: str) -> str:
    text = base_url.strip()
    if "://" not in text:
        text = f"http://{text}"
    parsed = urlsplit(text)
    if not parsed.scheme or not parsed.netloc:
        _fail(f"Invalid Home Assistant base URL: {base_url}")
    return text.rstrip("/")


def _ok(value: bool) -> str:
    return "ok" if value else "missing"


def _fail(message: str) -> None:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
