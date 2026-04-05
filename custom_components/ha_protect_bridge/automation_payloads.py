from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .const import AUDIO_DETECTION_TYPES, MANAGED_AUTOMATION_PREFIX, MANAGED_AUTOMATION_TIMEOUT_MS

_HTTP_REQUEST = "HTTP_REQUEST"


def build_managed_automation_name(source: str) -> str:
    return f"{MANAGED_AUTOMATION_PREFIX} {source}"


def build_managed_automation_payload(
    source: str,
    device_macs: Iterable[str],
    webhook_url: str,
) -> dict[str, Any]:
    unique_devices = sorted(dict.fromkeys(device for device in device_macs if device))
    if not unique_devices:
        raise ValueError(f"No device MACs available for {source}")

    return {
        "name": build_managed_automation_name(source),
        "enable": True,
        "isCreatedBySystem": False,
        "sources": [{"device": device, "type": "include"} for device in unique_devices],
        "conditions": [{"condition": {"type": "is", "source": source}}],
        "historyConditions": [],
        "schedules": [],
        "actions": [
            {
                "type": _HTTP_REQUEST,
                "metadata": {
                    "url": build_webhook_target_url(webhook_url, source),
                    "method": "POST",
                    "headers": [],
                    "timeout": MANAGED_AUTOMATION_TIMEOUT_MS,
                    "useThumbnail": source not in AUDIO_DETECTION_TYPES,
                },
                "order": -1,
            }
        ],
        "cooldown": {
            "enable": False,
            "timeout": 600000,
        },
    }


def build_webhook_target_url(webhook_url: str, source: str) -> str:
    parsed = urlsplit(webhook_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["source"] = source
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query),
            parsed.fragment,
        )
    )


def managed_source_from_automation(automation: Mapping[str, Any]) -> str | None:
    name = _string(automation.get("name"))
    prefix = f"{MANAGED_AUTOMATION_PREFIX} "
    if name and name.startswith(prefix):
        return name[len(prefix) :].strip() or None

    metadata = _http_request_metadata(automation)
    url = _string(metadata.get("url"))
    if not url:
        return None
    return dict(parse_qsl(urlsplit(url).query)).get("source")


def map_managed_automations(
    automations: Iterable[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    managed: dict[str, Mapping[str, Any]] = {}
    for automation in automations:
        source = managed_source_from_automation(automation)
        if source and source not in managed:
            managed[source] = automation
    return managed


def automation_needs_replace(existing: Mapping[str, Any], desired: Mapping[str, Any]) -> bool:
    return any(
        (
            _string(existing.get("name")) != _string(desired.get("name")),
            bool(existing.get("enable", True)) != bool(desired.get("enable", True)),
            _normalized_sources(existing) != _normalized_sources(desired),
            _normalized_conditions(existing) != _normalized_conditions(desired),
            _normalized_http_request(existing) != _normalized_http_request(desired),
        )
    )


def _normalized_sources(automation: Mapping[str, Any]) -> tuple[str, ...]:
    devices = []
    for item in automation.get("sources") or []:
        if isinstance(item, Mapping):
            device = _string(item.get("device"))
            if device:
                devices.append(device)
    return tuple(sorted(devices))


def _normalized_conditions(
    automation: Mapping[str, Any],
) -> tuple[tuple[str | None, str | None], ...]:
    conditions = []
    for item in automation.get("conditions") or []:
        if not isinstance(item, Mapping):
            continue
        condition = item.get("condition")
        if not isinstance(condition, Mapping):
            condition = item
        conditions.append((_string(condition.get("type")), _string(condition.get("source"))))
    return tuple(sorted(conditions))


def _normalized_http_request(automation: Mapping[str, Any]) -> tuple[Any, ...]:
    metadata = _http_request_metadata(automation)
    headers = tuple(
        sorted(
            (
                _string(header.get("key")),
                _string(header.get("value")),
            )
            for header in metadata.get("headers") or []
            if isinstance(header, Mapping)
        )
    )
    return (
        _string(metadata.get("url")),
        _string(metadata.get("method")),
        _coerce_int(metadata.get("timeout")),
        bool(metadata.get("useThumbnail")),
        headers,
    )


def _http_request_metadata(automation: Mapping[str, Any]) -> Mapping[str, Any]:
    for action in automation.get("actions") or []:
        if isinstance(action, Mapping) and action.get("type") == _HTTP_REQUEST:
            metadata = action.get("metadata")
            if isinstance(metadata, Mapping):
                return metadata
    return {}


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
