from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

MANAGED_AUTOMATION_PREFIX = "UniFi Protect Bridge:"
LEGACY_MANAGED_AUTOMATION_PREFIX = "HA Protect Bridge:"

KNOWN_DETECTION_TYPES = (
    "motion",
    "person",
    "vehicle",
    "animal",
    "package",
    "license_plate_of_interest",
    "ring",
    "face_unknown",
    "face_known",
    "face_of_interest",
    "audio_alarm_baby_cry",
    "audio_alarm_bark",
    "audio_alarm_burglar",
    "audio_alarm_car_horn",
    "audio_alarm_co",
    "audio_alarm_glass_break",
    "audio_alarm_siren",
    "audio_alarm_smoke",
    "audio_alarm_speak",
)

SOURCE_LABELS = {
    "motion": "motion",
    "person": "person",
    "vehicle": "vehicle",
    "animal": "animal",
    "package": "package",
    "license_plate_of_interest": "license plate of interest",
    "ring": "doorbell ring",
    "face_unknown": "unknown face",
    "face_known": "known face",
    "face_of_interest": "face of interest",
    "audio_alarm_baby_cry": "baby cry alarm",
    "audio_alarm_bark": "bark alarm",
    "audio_alarm_burglar": "burglar alarm",
    "audio_alarm_car_horn": "car horn alarm",
    "audio_alarm_co": "carbon monoxide alarm",
    "audio_alarm_glass_break": "glass-break alarm",
    "audio_alarm_siren": "siren alarm",
    "audio_alarm_smoke": "smoke alarm",
    "audio_alarm_speak": "speech alarm",
}

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


def source_label(source: str) -> str:
    return SOURCE_LABELS.get(source, source.replace("_", " "))


def build_camera_catalog(bootstrap: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(bootstrap or {})
    cameras: list[dict[str, Any]] = []
    managed_sources: set[str] = set()

    for index, raw_camera in enumerate(data.get("cameras") or [], start=1):
        if not isinstance(raw_camera, Mapping):
            continue

        camera_id = _string(raw_camera.get("id"))
        device_mac = normalize_device_key(raw_camera.get("mac"))
        supported_sources = _camera_sources(raw_camera)
        camera = {
            "camera_id": camera_id,
            "camera_key": camera_id or device_mac or f"camera_{index}",
            "device_mac": device_mac,
            "name": _camera_name(raw_camera, device_mac, index),
            "model": _string(raw_camera.get("marketName")) or "UniFi Protect Camera",
            "is_doorbell": bool((raw_camera.get("featureFlags") or {}).get("isDoorbell")),
            "supported_sources": supported_sources,
        }
        cameras.append(camera)
        managed_sources.update(supported_sources)

    cameras.sort(key=lambda item: item["name"].casefold())
    return {
        "nvr_id": _string((data.get("nvr") or {}).get("id")),
        "nvr_name": _string((data.get("nvr") or {}).get("name")) or "UniFi Protect",
        "cameras": cameras,
        "managed_sources": _sort_sources(managed_sources),
    }


def build_bridge_plan(
    catalog: Mapping[str, Any],
    *,
    webhook_configured: bool,
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    cameras = catalog.get("cameras") or []

    for source in catalog.get("managed_sources") or []:
        source_cameras = [
            camera
            for camera in cameras
            if source in (camera.get("supported_sources") or [])
        ]
        plan.append(
            {
                "source": source,
                "label": source_label(source),
                "automation_name": f"{MANAGED_AUTOMATION_PREFIX} {source}",
                "camera_count": len(source_cameras),
                "device_macs": [
                    camera["device_mac"] for camera in source_cameras if camera.get("device_mac")
                ],
                "webhook_configured": webhook_configured,
            }
        )

    return plan


def inspect_automations(automations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    items = [dict(item) for item in automations]
    grouped = group_managed_automations(items)
    managed_total = sum(len(source_items) for source_items in grouped.values())
    duplicates = {
        source: [_automation_summary(item) for item in source_items[1:]]
        for source, source_items in grouped.items()
        if len(source_items) > 1
    }

    return {
        "total": len(items),
        "managed_total": managed_total,
        "user_total": len(items) - managed_total,
        "duplicate_sources": sorted(duplicates),
        "managed": {
            source: [_automation_summary(item) for item in source_items]
            for source, source_items in grouped.items()
        },
        "duplicates": duplicates,
    }


def group_managed_automations(
    automations: Iterable[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for automation in automations:
        source = managed_source_from_automation(automation)
        if source:
            grouped.setdefault(source, []).append(automation)

    for items in grouped.values():
        items.sort(key=_managed_automation_rank)

    return grouped


def managed_source_from_automation(automation: Mapping[str, Any]) -> str | None:
    name = _string(automation.get("name"))
    if not name:
        return None

    for prefix in (MANAGED_AUTOMATION_PREFIX, LEGACY_MANAGED_AUTOMATION_PREFIX):
        full_prefix = f"{prefix} "
        if name.startswith(full_prefix):
            return name[len(full_prefix) :].strip() or None

    return None


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


def _object_type_to_sources(value: Any) -> tuple[str, ...]:
    normalized = "".join(character for character in str(value).lower() if character.isalnum())
    sources = _OBJECT_TYPE_TO_SOURCES.get(normalized, ())
    return tuple(source for source in sources if source in KNOWN_DETECTION_TYPES)


def _audio_type_to_source(value: Any) -> str | None:
    normalized = "".join(character for character in str(value).lower() if character.isalnum())
    source = _AUDIO_TYPE_TO_SOURCE.get(normalized)
    if source in KNOWN_DETECTION_TYPES:
        return source
    return None


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


def _managed_automation_rank(automation: Mapping[str, Any]) -> int:
    name = _string(automation.get("name")) or ""
    if name.startswith(f"{MANAGED_AUTOMATION_PREFIX} "):
        return 0
    if name.startswith(f"{LEGACY_MANAGED_AUTOMATION_PREFIX} "):
        return 1
    return 2


def _automation_summary(automation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _string(automation.get("id")),
        "name": _string(automation.get("name")),
        "enabled": bool(automation.get("enable", automation.get("enabled", True))),
    }


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
