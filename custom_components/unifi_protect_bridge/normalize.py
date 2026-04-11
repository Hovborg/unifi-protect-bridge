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
    "license_plate": "license_plate_of_interest",
    "licenseplate": "license_plate_of_interest",
    "licence_plate": "license_plate_of_interest",
    "license_plates": "license_plate_of_interest",
    "personofinterest": "face_of_interest",
    "persons_of_interest": "face_of_interest",
    "knownface": "face_known",
    "unknownface": "face_unknown",
    "faceofinterest": "face_of_interest",
    "face": "face",
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
    "babycry": "audio_alarm_baby_cry",
    "baby_cry": "audio_alarm_baby_cry",
    "alrmbabycry": "audio_alarm_baby_cry",
}

_NAME_HINTS = (
    ("face of interest", "face_of_interest"),
    ("known face", "face_known"),
    ("unknown face", "face_unknown"),
    ("face", "face"),
    ("license plate", "license_plate_of_interest"),
    ("baby cry", "audio_alarm_baby_cry"),
    ("crying baby", "audio_alarm_baby_cry"),
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

_FACE_SUBTYPE_DETECTIONS = {
    "face_unknown",
    "face_known",
    "face_of_interest",
}

_EVENT_TYPE_TO_DETECTIONS = {
    "motion": ("motion",),
    "ring": ("ring",),
}

_SMART_EVENT_TYPE_TO_DETECTIONS = {
    "person": ("person",),
    "vehicle": ("vehicle",),
    "animal": ("animal",),
    "package": ("package",),
    "licenseplate": ("license_plate_of_interest",),
    "face": ("face",),
    "alrmbabycry": ("audio_alarm_baby_cry",),
    "alrmbark": ("audio_alarm_bark",),
    "alrmburglar": ("audio_alarm_burglar",),
    "alrmcarhorn": ("audio_alarm_car_horn",),
    "alrmcmonx": ("audio_alarm_co",),
    "alrmglassbreak": ("audio_alarm_glass_break",),
    "alrmsiren": ("audio_alarm_siren",),
    "alrmsmoke": ("audio_alarm_smoke",),
    "alrmspeak": ("audio_alarm_speak",),
}


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
    trigger_values = _extract_trigger_values(alarm, query)
    recognized_face_names = _extract_recognized_face_names(detection_types, trigger_values)
    timestamp_ms = _coerce_int(_first_present(payload.get("timestamp"), query.get("timestamp")))

    return {
        "alarm_name": alarm_name,
        "detection_types": detection_types,
        "primary_detection_type": detection_types[0] if detection_types else None,
        "device_ids": device_ids,
        "source_values": source_values,
        "trigger_values": trigger_values,
        "recognized_face_names": recognized_face_names,
        "primary_recognized_face": recognized_face_names[0] if recognized_face_names else None,
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": _timestamp_to_iso(timestamp_ms),
        "query": query,
        "raw_payload": payload,
        "event_types": [f"{DOMAIN}_{kind}" for kind in detection_types],
    }


def normalize_event_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(payload or {})
    event_type = _string_or_none(payload.get("type"))
    smart_detect_types = _extract_smart_detect_types(payload)
    detection_types = _extract_event_detection_types(event_type, smart_detect_types)

    device_ids = _unique(
        [
            value
            for value in (
                _string_or_none(payload.get("camera")),
                _string_or_none(payload.get("cameraId")),
                _string_or_none(payload.get("device")),
                _string_or_none(payload.get("deviceId")),
            )
            if value
        ]
    )
    timestamp_ms = _coerce_int(
        _first_present(payload.get("timestamp"), payload.get("start"), payload.get("end"))
    )

    return {
        "alarm_name": event_type,
        "detection_types": detection_types,
        "primary_detection_type": detection_types[0] if detection_types else None,
        "device_ids": device_ids,
        "source_values": smart_detect_types or ([event_type] if event_type else []),
        "trigger_values": [],
        "recognized_face_names": [],
        "primary_recognized_face": None,
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": _timestamp_to_iso(timestamp_ms),
        "query": {},
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


def _extract_smart_detect_types(payload: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for item in payload.get("smartDetectTypes") or []:
        text = _string_or_none(item)
        if text:
            values.append(text)
    return _unique(values)


def _extract_event_detection_types(
    event_type: str | None,
    smart_detect_types: list[str],
) -> list[str]:
    detections: list[str] = []

    if event_type:
        event_slug = _slugify(event_type)
        event_key = event_slug.replace("_", "")
        detections.extend(_EVENT_TYPE_TO_DETECTIONS.get(event_slug, ()))
    else:
        event_key = ""

    if event_key in {"smartdetectzone", "smartdetectline", "smartaudiodetect"}:
        for raw in smart_detect_types:
            detections.extend(_SMART_EVENT_TYPE_TO_DETECTIONS.get(_slugify(raw), ()))

    return _expand_detection_types(detections)


def _extract_detection_types(alarm_name: str | None, source_values: list[str]) -> list[str]:
    detections: list[str] = []

    if alarm_name:
        name_tokens = _tokenize_words(alarm_name)
        for phrase, normalized in _NAME_HINTS:
            if _contains_token_phrase(name_tokens, phrase):
                detections.append(normalized)

    for raw in source_values:
        normalized = _normalize_detection(raw)
        if normalized:
            detections.append(normalized)

    return _expand_detection_types(detections)


def _expand_detection_types(detections: list[str]) -> list[str]:
    expanded: list[str] = []
    for detection in detections:
        expanded.append(detection)
        if detection in _FACE_SUBTYPE_DETECTIONS:
            expanded.append("face")
    return _unique(expanded)


def _contains_token_phrase(name_tokens: tuple[str, ...], phrase: str) -> bool:
    phrase_tokens = _tokenize_words(phrase)
    if not phrase_tokens or len(phrase_tokens) > len(name_tokens):
        return False

    phrase_length = len(phrase_tokens)
    return any(
        name_tokens[index : index + phrase_length] == phrase_tokens
        for index in range(len(name_tokens) - phrase_length + 1)
    )


def _normalize_detection(value: str) -> str | None:
    normalized = _slugify(value)
    normalized = _ALIASES.get(normalized, normalized)
    if normalized in KNOWN_DETECTION_TYPES:
        return normalized
    return None


def _extract_device_ids(alarm: Mapping[str, Any], query: Mapping[str, str]) -> list[str]:
    source_device_ids: list[str] = []
    trigger_device_ids: list[str] = []
    query_device_ids: list[str] = []

    for item in alarm.get("sources", []) or []:
        if isinstance(item, Mapping):
            device = _string_or_none(item.get("device"))
            if device:
                source_device_ids.append(device)

    for item in alarm.get("triggers", []) or []:
        if isinstance(item, Mapping):
            for field in ("device", "deviceId", "mac"):
                device = _string_or_none(item.get(field))
                if device:
                    trigger_device_ids.append(device)

    for field in ("device", "device_id", "deviceId", "camera"):
        query_device = _string_or_none(query.get(field))
        if query_device:
            query_device_ids.append(query_device)

    if trigger_device_ids or query_device_ids:
        return _unique([*trigger_device_ids, *query_device_ids])
    return _unique(source_device_ids)


def _extract_trigger_values(alarm: Mapping[str, Any], query: Mapping[str, str]) -> list[str]:
    values: list[str] = []

    for item in alarm.get("triggers", []) or []:
        if isinstance(item, Mapping):
            for field in ("value", "label", "displayValue"):
                value = _string_or_none(item.get(field))
                if value:
                    values.append(value)

    for field in ("value", "trigger_value", "recognized_face", "recognized_name"):
        value = _string_or_none(query.get(field))
        if value:
            values.append(value)

    return _unique(values)


def _extract_recognized_face_names(
    detection_types: list[str],
    trigger_values: list[str],
) -> list[str]:
    has_face_detection = any(
        detection == "face" or detection.startswith("face_") for detection in detection_types
    )
    if not has_face_detection:
        return []
    return trigger_values


def _slugify(value: str) -> str:
    result = value.strip().lower()
    result = result.replace("-", "_").replace(" ", "_")
    return "".join(character for character in result if character.isalnum() or character == "_")


def _tokenize_words(value: str) -> tuple[str, ...]:
    tokens: list[str] = []
    current: list[str] = []
    for character in value.lower():
        if character.isalnum():
            current.append(character)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tuple(tokens)


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
    try:
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).isoformat()
    except (OSError, OverflowError, ValueError):
        return None


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


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None
