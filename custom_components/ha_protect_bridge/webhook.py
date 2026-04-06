from __future__ import annotations

import json
import logging
from http import HTTPStatus
from typing import Any

from aiohttp.web import Request, Response, json_response

from .const import CONF_WEBHOOK_ID, DOMAIN, EVENT_DETECTION, EVENT_WEBHOOK
from .entry_runtime import iter_entry_runtimes
from .normalize import normalize_webhook_payload

_LOGGER = logging.getLogger(__name__)


async def async_handle_protect_webhook(hass: Any, webhook_id: str, request: Request) -> Response:
    payload = await _read_payload(request)
    normalized = normalize_webhook_payload(payload, request.query)
    runtime = _runtime_for_webhook(hass, webhook_id)
    matched_cameras = []
    if runtime is not None:
        matched_cameras = await runtime.async_process_webhook(normalized)

    event_data = {
        **normalized,
        "webhook_id": webhook_id,
        "method": request.method,
        "path": str(request.rel_url),
        "matched_camera_names": [camera.get("name") for camera in matched_cameras],
        "matched_camera_keys": [camera.get("camera_key") for camera in matched_cameras],
        "headers": {
            key: value
            for key, value in request.headers.items()
            if key.lower().startswith("x-")
        },
    }

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

    body = await request.text()
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


def _runtime_for_webhook(hass: Any, webhook_id: str) -> Any | None:
    for runtime in iter_entry_runtimes(hass):
        if runtime.entry.data.get(CONF_WEBHOOK_ID) == webhook_id:
            return runtime
    return None
