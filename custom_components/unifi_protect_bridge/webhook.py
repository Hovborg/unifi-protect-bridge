from __future__ import annotations

import json
import logging
from http import HTTPStatus
from typing import Any

from aiohttp.web import Request, Response, json_response

from .const import CONF_WEBHOOK_ID, DOMAIN, EVENT_DETECTION, EVENT_WEBHOOK, SUPPORTED_METHODS
from .entry_runtime import iter_entry_runtimes
from .normalize import normalize_webhook_payload

_LOGGER = logging.getLogger(__name__)
MAX_WEBHOOK_BODY_BYTES = 256 * 1024


class WebhookPayloadTooLarge(ValueError):
    """Webhook request body exceeded the integration limit."""


async def async_handle_protect_webhook(hass: Any, webhook_id: str, request: Request) -> Response:
    if request.method not in SUPPORTED_METHODS:
        return json_response(
            {"status": HTTPStatus.METHOD_NOT_ALLOWED},
            status=HTTPStatus.METHOD_NOT_ALLOWED,
        )

    try:
        payload = await _read_payload(request)
    except WebhookPayloadTooLarge:
        return json_response(
            {"status": HTTPStatus.REQUEST_ENTITY_TOO_LARGE},
            status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
        )
    normalized = normalize_webhook_payload(payload, request.query)
    runtime = _runtime_for_webhook(hass, webhook_id)
    matched_cameras = []
    if runtime is not None:
        matched_cameras = await runtime.async_process_webhook(normalized)
    else:
        _LOGGER.warning("Received UniFi Protect Bridge webhook for unknown runtime")

    event_data = _build_event_data(normalized, request.method, matched_cameras)

    hass.bus.async_fire(EVENT_WEBHOOK, event_data)

    if normalized["detection_types"]:
        hass.bus.async_fire(EVENT_DETECTION, event_data)
        for detection in normalized["detection_types"]:
            hass.bus.async_fire(f"{DOMAIN}_{detection}", event_data)
    else:
        _LOGGER.debug("Webhook received without recognized detection type: %s", event_data)

    return json_response(
        {
            "status": HTTPStatus.OK,
            "primary_detection_type": normalized["primary_detection_type"],
            "detection_types": normalized["detection_types"],
            "matched_cameras": [camera.get("name") for camera in matched_cameras],
        },
        status=HTTPStatus.OK,
    )


async def _read_payload(request: Request) -> dict[str, Any]:
    if request.method not in {"POST", "PUT"}:
        return {}

    content_length = _content_length(request)
    if content_length is not None and content_length > MAX_WEBHOOK_BODY_BYTES:
        raise WebhookPayloadTooLarge

    body = await request.text()
    if len(body.encode("utf-8")) > MAX_WEBHOOK_BODY_BYTES:
        raise WebhookPayloadTooLarge
    if not body.strip():
        return {}

    content_type = (request.headers.get("Content-Type") or "").lower()
    if "json" in content_type or body.lstrip().startswith(("{", "[")):
        try:
            loaded = json.loads(body)
        except json.JSONDecodeError:
            _LOGGER.warning("Received invalid JSON body from Protect webhook")
            return {"raw_body": body}
        return loaded if isinstance(loaded, dict) else {"raw_body": loaded}

    return {"raw_body": body}


def _content_length(request: Request) -> int | None:
    try:
        value = getattr(request, "content_length", None)
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _runtime_for_webhook(hass: Any, webhook_id: str) -> Any | None:
    for runtime in iter_entry_runtimes(hass):
        if runtime.entry.data.get(CONF_WEBHOOK_ID) == webhook_id:
            return runtime
    return None


def _build_event_data(
    normalized: dict[str, Any],
    method: str,
    matched_cameras: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "alarm_name": normalized.get("alarm_name"),
        "detection_types": list(normalized.get("detection_types") or []),
        "primary_detection_type": normalized.get("primary_detection_type"),
        "device_ids": list(normalized.get("device_ids") or []),
        "source_values": list(normalized.get("source_values") or []),
        "trigger_values": list(normalized.get("trigger_values") or []),
        "recognized_face_names": list(normalized.get("recognized_face_names") or []),
        "primary_recognized_face": normalized.get("primary_recognized_face"),
        "timestamp_ms": normalized.get("timestamp_ms"),
        "timestamp_iso": normalized.get("timestamp_iso"),
        "event_types": list(normalized.get("event_types") or []),
        "method": method,
        "matched_camera_names": [camera.get("name") for camera in matched_cameras],
        "matched_camera_keys": [camera.get("camera_key") for camera in matched_cameras],
    }
