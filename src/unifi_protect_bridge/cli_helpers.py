from __future__ import annotations

import importlib
import json
import platform
import sys
import types
from collections.abc import Iterable, Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from unifi_protect_bridge import __version__
from unifi_protect_bridge.config import Settings

DOMAIN = "unifi_protect_bridge"
NAME = "UniFi Protect Bridge"
REPO = "unifi-protect-bridge"

ENV_KEYS = (
    "HA_BASE_URL",
    "HA_TOKEN",
    "UNIFI_PROTECT_BASE_URL",
    "UNIFI_PROTECT_USERNAME",
    "UNIFI_PROTECT_PASSWORD",
    "VERIFY_SSL",
    "REQUEST_TIMEOUT_SECONDS",
)

SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "auth",
    "key",
    "password",
    "secret",
    "sig",
    "signature",
    "token",
}


class CliConfigError(RuntimeError):
    """Raised when CLI input or local repo state is invalid."""


def default_repo_path() -> Path:
    cwd = Path.cwd()
    if _is_repo_path(cwd):
        return cwd

    package_repo = Path(__file__).resolve().parents[2]
    if _is_repo_path(package_repo):
        return package_repo

    return cwd


def build_doctor_report(repo: Path | None = None) -> dict[str, Any]:
    repo_path = (repo or default_repo_path()).expanduser().resolve()
    settings = Settings.load()
    report: dict[str, Any] = {
        "name": NAME,
        "version": __version__,
        "python": platform.python_version(),
        "executable": sys.executable,
        "repo": {
            "path": str(repo_path),
            "detected": _is_repo_path(repo_path),
        },
        "env": env_status(settings),
    }

    if _is_repo_path(repo_path):
        integration = build_integration_report(repo_path)
        report["integration"] = integration["summary"]
    else:
        report["integration"] = {
            "ok": 0,
            "warn": 0,
            "fail": 1,
            "status": "fail",
            "message": "Repository layout was not detected.",
        }

    return report


def env_status(settings: Settings) -> dict[str, str]:
    values = {
        "HA_BASE_URL": settings.ha_base_url,
        "HA_TOKEN": settings.ha_token,
        "UNIFI_PROTECT_BASE_URL": settings.unifi_protect_base_url,
        "UNIFI_PROTECT_USERNAME": settings.unifi_protect_username,
        "UNIFI_PROTECT_PASSWORD": settings.unifi_protect_password,
        "VERIFY_SSL": str(settings.verify_ssl).lower(),
        "REQUEST_TIMEOUT_SECONDS": str(settings.request_timeout_seconds),
    }
    return {
        key: values[key] if key in {"VERIFY_SSL", "REQUEST_TIMEOUT_SECONDS"} else _flag(values[key])
        for key in ENV_KEYS
    }


def build_integration_report(repo: Path) -> dict[str, Any]:
    repo = repo.expanduser().resolve()
    checks: list[dict[str, str]] = []

    component = repo / "custom_components" / DOMAIN
    blueprint = repo / "blueprints" / "automation" / DOMAIN / "react_to_detection.yaml"
    manifest_path = component / "manifest.json"
    hacs_path = repo / "hacs.json"
    services_path = component / "services.yaml"
    translations_path = component / "translations" / "en.json"

    _add_path_check(checks, "component path", component, expect_dir=True)
    _add_path_check(checks, "manifest", manifest_path)
    _add_path_check(checks, "hacs metadata", hacs_path)
    _add_path_check(checks, "services", services_path)
    _add_path_check(checks, "translations", translations_path)
    _add_path_check(checks, "detection blueprint", blueprint)
    _add_path_absent_check(
        checks,
        "legacy component path absent",
        repo / "custom_components" / "ha_protect_bridge",
    )
    _add_path_absent_check(
        checks,
        "legacy blueprint path absent",
        repo / "blueprints" / "automation" / "ha_protect_bridge",
    )
    _add_path_absent_check(checks, "legacy src package absent", repo / "src" / "sitebridge")

    manifest = _load_json_if_exists(manifest_path)
    hacs = _load_json_if_exists(hacs_path)
    translations = _load_json_if_exists(translations_path)

    _add_value_check(checks, "manifest domain", manifest.get("domain"), DOMAIN)
    _add_value_check(checks, "manifest name", manifest.get("name"), NAME)
    _add_value_check(checks, "manifest version", manifest.get("version"), __version__)
    _add_value_check(
        checks,
        "manifest documentation",
        manifest.get("documentation"),
        f"https://github.com/Hovborg/{REPO}",
    )
    _add_value_check(checks, "hacs name", hacs.get("name"), NAME)
    _add_presence_check(
        checks,
        "hacs minimum Home Assistant version",
        hacs.get("homeassistant"),
    )
    _add_presence_check(checks, "translations config flow", translations.get("config"))

    services_text = _read_text_if_exists(services_path)
    _add_text_check(checks, "service show_setup_info", services_text, "show_setup_info:")
    _add_text_check(checks, "service resync", services_text, "resync:")

    blueprint_text = _read_text_if_exists(blueprint)
    _add_text_check(
        checks,
        "blueprint domain events",
        blueprint_text,
        "unifi_protect_bridge_detection",
    )

    summary = summarize_checks(checks)
    return {
        "repo": str(repo),
        "summary": summary,
        "checks": checks,
    }


def manifest_summary(repo: Path) -> dict[str, Any]:
    manifest_path = repo.expanduser().resolve() / "custom_components" / DOMAIN / "manifest.json"
    manifest = load_json_file(manifest_path)
    keys = (
        "domain",
        "name",
        "version",
        "documentation",
        "issue_tracker",
        "iot_class",
        "integration_type",
    )
    return {key: manifest.get(key) for key in keys}


def summarize_checks(checks: Iterable[Mapping[str, str]]) -> dict[str, Any]:
    counts = {"ok": 0, "warn": 0, "fail": 0}
    for check in checks:
        status = check.get("status")
        if status in counts:
            counts[status] += 1

    if counts["fail"]:
        status = "fail"
    elif counts["warn"]:
        status = "warn"
    else:
        status = "ok"

    return {
        **counts,
        "status": status,
    }


def load_json_file(path: Path) -> Any:
    try:
        with path.expanduser().open(encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError as err:
        raise CliConfigError(f"File not found: {path}") from err
    except json.JSONDecodeError as err:
        raise CliConfigError(f"Invalid JSON in {path}: {err.msg}") from err


def parse_query_string(query: str | None) -> dict[str, str]:
    if not query:
        return {}
    text = query[1:] if query.startswith("?") else query
    return {key: value for key, value in parse_qsl(text, keep_blank_values=True)}


def component_module(repo: Path, module_name: str) -> Any:
    repo = repo.expanduser().resolve()
    component = repo / "custom_components" / DOMAIN
    if not component.is_dir():
        raise CliConfigError(f"Could not find {component}")

    custom_components = sys.modules.get("custom_components")
    if custom_components is None:
        custom_components = types.ModuleType("custom_components")
        custom_components.__path__ = [str(repo / "custom_components")]
        sys.modules["custom_components"] = custom_components

    package_name = f"custom_components.{DOMAIN}"
    package = sys.modules.get(package_name)
    if package is None:
        package = types.ModuleType(package_name)
        package.__path__ = [str(component)]
        sys.modules[package_name] = package

    return importlib.import_module(f"{package_name}.{module_name}")


def automation_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        items = data.get("automations")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    raise CliConfigError("Expected a JSON list, or an object with an 'automations' list.")


def redact_url(url: str | None, *, show_url: bool = False) -> str | None:
    if not url:
        return url
    if show_url:
        return url

    parsed = urlsplit(url)
    path_parts = parsed.path.split("/")
    redacted_parts = [
        "<webhook_id>" if index > 0 and path_parts[index - 1] == "webhook" else part
        for index, part in enumerate(path_parts)
    ]
    query = [
        (key, "<redacted>" if key.lower() in SENSITIVE_QUERY_KEYS else value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            "/".join(redacted_parts),
            urlencode(query),
            parsed.fragment,
        )
    )


def redact_automation(value: Mapping[str, Any], *, show_urls: bool = False) -> dict[str, Any]:
    redacted = deepcopy(dict(value))
    for action in redacted.get("actions") or []:
        if not isinstance(action, dict):
            continue
        metadata = action.get("metadata")
        if not isinstance(metadata, dict):
            continue
        if "url" in metadata:
            metadata["url"] = redact_url(str(metadata["url"]), show_url=show_urls)
        if "headers" in metadata and not show_urls:
            metadata["headers"] = "<redacted>"
    return redacted


def automation_prefix_kind(name: str | None) -> str:
    if name and name.startswith("UniFi Protect Bridge: "):
        return "current"
    if name and name.startswith("HA Protect Bridge: "):
        return "legacy"
    return "unmanaged"


def _flag(value: str | None) -> str:
    return "set" if value else "missing"


def _is_repo_path(path: Path) -> bool:
    return (path / "custom_components" / DOMAIN / "manifest.json").is_file()


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = load_json_file(path)
    return data if isinstance(data, dict) else {}


def _read_text_if_exists(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _add_path_check(
    checks: list[dict[str, str]],
    name: str,
    path: Path,
    *,
    expect_dir: bool = False,
) -> None:
    exists = path.is_dir() if expect_dir else path.is_file()
    checks.append(
        {
            "name": name,
            "status": "ok" if exists else "fail",
            "detail": str(path) if exists else f"Missing: {path}",
        }
    )


def _add_path_absent_check(checks: list[dict[str, str]], name: str, path: Path) -> None:
    exists = path.exists()
    checks.append(
        {
            "name": name,
            "status": "fail" if exists else "ok",
            "detail": f"Unexpected path exists: {path}" if exists else str(path),
        }
    )


def _add_value_check(
    checks: list[dict[str, str]],
    name: str,
    actual: Any,
    expected: str,
) -> None:
    ok = actual == expected
    checks.append(
        {
            "name": name,
            "status": "ok" if ok else "fail",
            "detail": str(actual) if ok else f"Expected {expected!r}, got {actual!r}",
        }
    )


def _add_presence_check(checks: list[dict[str, str]], name: str, value: Any) -> None:
    ok = bool(value)
    checks.append(
        {
            "name": name,
            "status": "ok" if ok else "fail",
            "detail": "present" if ok else "missing",
        }
    )


def _add_text_check(
    checks: list[dict[str, str]],
    name: str,
    text: str,
    needle: str,
) -> None:
    ok = needle in text
    checks.append(
        {
            "name": name,
            "status": "ok" if ok else "fail",
            "detail": f"found {needle!r}" if ok else f"missing {needle!r}",
        }
    )
