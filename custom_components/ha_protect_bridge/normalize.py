from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from .const import DOMAIN, KNOWN_DETECTION_TYPES

_ALIASES = {
    "people": "person",
    "persons": "person",
    "pet": "animal",
    "pets": "animal",
    "car": "vehicle",
    "cars": "vehicle",
    "licenseplate": "license_plate_of_interest",
    "licence_plate": "license_plate_of_interest",
    "license_plates": "license_plate_of_interest",
    "personofinterest": "face_of_interest",
    "persons_of_interest": "face_of_interest",
    "knownface": "face_known",
    "unknownface": "face_unknown",
    "faceofinterest": "face_of_interest",
    "doorbellring": "ring",
    "doorbell": "ring",
    "known_face": "face_known",
    "unknown_face": "face_unknown",
    "person_of_interest": "face_of_interest",
    "smokealarm": "audio_alarm_smoke",
    "smoke": "audio_alarm_smoke",
    "carbon_monoxide": "audio_alarm_co",
    "co": "audio_alarm_co",
    "glassbreak": "audio_alarm_glass_break",
    "carhorn": "audio_alarm_car_horn",
    "burglaralarm": "audio_alarm_burglar",
    "siren": "audio_alarm_siren",
    "speech": "audio_alarm_speak",
    "bark": "audio_alarm_bark",
}

_NAME_HINTS = (
    ("face of interest", "face_of_interest"),
    ("known face", "face_known"),
    ("unknown face", "face_unknown"),
    ("license plate", "license_plate_of_interest"),
    ("doorbell ring", "ring"),
    ("doorbell", "ring"),
    ("vehicle", "vehicle"),
    ("package", "package"),
    ("animal", "animal"),
    ("person", "person"),
    ("motion", "motion"),
    ("smoke", "audio_alarm_smoke"),
    ("glass break", "audio_alarm_glass_break"),
    ("car horn", "audio_alarm_car_horn"),
    ("speech", "audio_alarm_speak"),
    ("bark", "audio_alarm_bark"),
)


def normalize_webhook_payload(
    payload: Mapping[str, Any] | None,
    query: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    payload = dict(payload or {})
    query = dict(query or {})
    alarm = payload.get("alarm") if isinstance(payload.get("alarm"), Mapping) else {}
    alarm = dict(alarm)

    alarm_name = _first_non_empty(
        _string_or_none(alarm.get("name")),
        _string_or_none(query.get("alarm")),
        _string_or_none(query.get("name")),
    )
    source_values = _extract_source_values(alarm, query)
    detection_types = _extract_detection_types(alarm_name, source_values)
    device_ids = _extract_device_ids(alarm, query)
    timestamp_ms = _coerce_int(payload.get("timestamp") or query.get("timestamp"))

    return {
        "alarm_name": alarm_name,
        "detection_types": detection_types,
        "primary_detection_type": detection_types[0] if detection_types else None,
        "device_ids": device_ids,
        "source_values": source_values,
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": _timestamp_to_iso(timestamp_ms),
        "query": query,
        "raw_payload": payload,
        "event_types": [f"{DOMAIN}_{kind}" for kind in detection_types],
    }


def _extract_source_values(alarm: Mapping[str, Any], query: Mapping[str, str]) -> list[str]:
    values: list[str] = []

    for item in alarm.get("sources", []) or []:
        if isinstance(item, str):
            values.append(item)
        elif isinstance(item, Mapping):
            for field in ("source", "key", "type", "name", "device"):
                value = _string_or_none(item.get(field))
                if value:
                    values.append(value)

    for item in alarm.get("conditions", []) or []:
        if isinstance(item, Mapping):
            condition_value = item.get("condition")
            condition = condition_value if isinstance(condition_value, Mapping) else item
            for field in ("source", "key", "type", "name"):
                value = _string_or_none(condition.get(field))
                if value:
                    values.append(value)

    for item in alarm.get("triggers", []) or []:
        if isinstance(item, Mapping):
            for field in ("key", "source", "type", "name"):
                value = _string_or_none(item.get(field))
                if value:
                    values.append(value)

    for field in ("key", "event", "type", "detection", "source"):
        value = _string_or_none(query.get(field))
        if value:
            values.append(value)

    return _unique(values)


def _extract_detection_types(alarm_name: str | None, source_values: list[str]) -> list[str]:
    detections: list[str] = []

    if alarm_name:
        lowered_name = alarm_name.lower()
        for phrase, normalized in _NAME_HINTS:
            if phrase in lowered_name:
                detections.append(normalized)

    for raw in source_values:
        normalized = _normalize_detection(raw)
        if normalized:
            detections.append(normalized)

    return _unique(detections)


def _normalize_detection(value: str) -> str | None:
    normalized = _slugify(value)
    normalized = _ALIASES.get(normalized, normalized)
    if normalized in KNOWN_DETECTION_TYPES:
        return normalized
    return None


def _extract_device_ids(alarm: Mapping[str, Any], query: Mapping[str, str]) -> list[str]:
    device_ids: list[str] = []

    for item in alarm.get("sources", []) or []:
        if isinstance(item, Mapping):
            device = _string_or_none(item.get("device"))
            if device:
                device_ids.append(device)

    for item in alarm.get("triggers", []) or []:
        if isinstance(item, Mapping):
            for field in ("device", "deviceId", "mac"):
                device = _string_or_none(item.get(field))
                if device:
                    device_ids.append(device)

    for field in ("device", "device_id", "deviceId", "camera"):
        query_device = _string_or_none(query.get(field))
        if query_device:
            device_ids.append(query_device)

    return _unique(device_ids)


def _slugify(value: str) -> str:
    result = value.strip().lower()
    result = result.replace("-", "_").replace(" ", "_")
    return "".join(character for character in result if character.isalnum() or character == "_")


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _timestamp_to_iso(timestamp_ms: int | None) -> str | None:
    if timestamp_ms is None:
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).isoformat()


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if value:
            return value
    return None
