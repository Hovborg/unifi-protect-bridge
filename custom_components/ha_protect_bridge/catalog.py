from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .const import KNOWN_DETECTION_TYPES, SOURCE_LABELS

_OBJECT_TYPE_TO_SOURCES = {
    "person": ("person",),
    "vehicle": ("vehicle",),
    "animal": ("animal",),
    "package": ("package",),
    "licenseplate": ("license_plate_of_interest",),
    "face": ("face_unknown", "face_known", "face_of_interest"),
}

_AUDIO_TYPE_TO_SOURCE = {
    "alrmbark": "audio_alarm_bark",
    "alrmbabycry": "audio_alarm_baby_cry",
    "alrmburglar": "audio_alarm_burglar",
    "alrmcarhorn": "audio_alarm_car_horn",
    "alrmcmonx": "audio_alarm_co",
    "alrmglassbreak": "audio_alarm_glass_break",
    "alrmsiren": "audio_alarm_siren",
    "alrmsmoke": "audio_alarm_smoke",
    "alrmspeak": "audio_alarm_speak",
}

_SOURCE_ORDER = {source: index for index, source in enumerate(KNOWN_DETECTION_TYPES)}


def build_camera_catalog(bootstrap: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(bootstrap or {})
    lookup: dict[str, str] = {}
    cameras: list[dict[str, Any]] = []
    managed_sources: set[str] = set()

    for index, raw_camera in enumerate(data.get("cameras") or [], start=1):
        if not isinstance(raw_camera, Mapping):
            continue

        camera_id = _string(raw_camera.get("id"))
        device_mac = normalize_device_key(raw_camera.get("mac"))
        camera_key = camera_id or device_mac or f"camera_{index}"
        name = _camera_name(raw_camera, device_mac, index)
        supported_sources = _camera_sources(raw_camera)
        camera = {
            "camera_id": camera_id,
            "camera_key": camera_key,
            "device_mac": device_mac,
            "name": name,
            "model": _string(raw_camera.get("marketName")) or "UniFi Protect Camera",
            "is_doorbell": bool((raw_camera.get("featureFlags") or {}).get("isDoorbell")),
            "last_motion_ms": _int_or_none(raw_camera.get("lastMotion")),
            "last_ring_ms": _int_or_none(raw_camera.get("lastRing")),
            "supported_sources": supported_sources,
        }
        cameras.append(camera)
        managed_sources.update(supported_sources)

        for alias in (camera_key, camera_id, device_mac):
            normalized = normalize_device_key(alias)
            if normalized:
                lookup[normalized] = camera_key

    cameras.sort(key=lambda item: item["name"].casefold())
    return {
        "nvr_id": _string((data.get("nvr") or {}).get("id")),
        "nvr_name": _string((data.get("nvr") or {}).get("name")) or "UniFi Protect",
        "cameras": cameras,
        "lookup": lookup,
        "managed_sources": _sort_sources(managed_sources),
    }


def resolve_cameras(catalog: Mapping[str, Any], device_ids: Iterable[str]) -> list[dict[str, Any]]:
    lookup = catalog.get("lookup") or {}
    cameras = catalog.get("cameras") or []
    by_key = {camera["camera_key"]: camera for camera in cameras}
    resolved: list[dict[str, Any]] = []

    for device_id in device_ids:
        normalized = normalize_device_key(device_id)
        if not normalized:
            continue
        camera_key = lookup.get(normalized)
        if not camera_key or camera_key not in by_key:
            continue
        camera = by_key[camera_key]
        if camera not in resolved:
            resolved.append(camera)

    return resolved


def camera_by_key(catalog: Mapping[str, Any], camera_key: str) -> dict[str, Any] | None:
    for camera in catalog.get("cameras") or []:
        if camera.get("camera_key") == camera_key:
            return camera
    return None


def humanize_source(source: str) -> str:
    return SOURCE_LABELS.get(source, source.replace("_", " "))


def normalize_device_key(value: Any) -> str | None:
    if value is None:
        return None
    text = "".join(character for character in str(value).upper() if character.isalnum())
    return text or None


def _camera_sources(camera: Mapping[str, Any]) -> list[str]:
    sources = ["motion"]
    smart_detect_settings = camera.get("smartDetectSettings") or {}

    for object_type in smart_detect_settings.get("objectTypes") or []:
        sources.extend(_object_type_to_sources(object_type))

    if bool((camera.get("featureFlags") or {}).get("isDoorbell")):
        sources.append("ring")

    for audio_type in smart_detect_settings.get("audioTypes") or []:
        normalized = _audio_type_to_source(audio_type)
        if normalized:
            sources.append(normalized)

    return _sort_sources(sources)


def _audio_type_to_source(value: Any) -> str | None:
    normalized = "".join(character for character in str(value).lower() if character.isalnum())
    source = _AUDIO_TYPE_TO_SOURCE.get(normalized)
    if source in KNOWN_DETECTION_TYPES:
        return source
    return None


def _object_type_to_sources(value: Any) -> tuple[str, ...]:
    normalized = "".join(character for character in str(value).lower() if character.isalnum())
    sources = _OBJECT_TYPE_TO_SOURCES.get(normalized, ())
    return tuple(source for source in sources if source in KNOWN_DETECTION_TYPES)


def _camera_name(camera: Mapping[str, Any], device_mac: str | None, index: int) -> str:
    explicit_name = _string(camera.get("name"))
    if explicit_name:
        return explicit_name
    if device_mac:
        return f"Camera {device_mac[-6:]}"
    return f"Camera {index}"


def _sort_sources(values: Iterable[str]) -> list[str]:
    unique = dict.fromkeys(value for value in values if value in KNOWN_DETECTION_TYPES)
    return sorted(unique, key=lambda value: (_SOURCE_ORDER.get(value, 999), value))


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
