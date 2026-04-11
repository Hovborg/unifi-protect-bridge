from custom_components.unifi_protect_bridge.normalize import (
    normalize_event_payload,
    normalize_webhook_payload,
)


def test_normalize_official_motion_sample_shape() -> None:
    payload = {
        "alarm": {
            "name": "Camera has detected motion",
            "sources": [],
            "conditions": [{"condition": {"type": "is", "source": "motion"}}],
            "triggers": [{"key": "motion", "device": "74ACB99F4E24"}],
        },
        "timestamp": 1727382771168,
    }

    normalized = normalize_webhook_payload(payload, {})

    assert normalized["alarm_name"] == "Camera has detected motion"
    assert normalized["primary_detection_type"] == "motion"
    assert normalized["detection_types"] == ["motion"]
    assert normalized["device_ids"] == ["74ACB99F4E24"]
    assert normalized["timestamp_iso"] is not None


def test_normalize_person_detection_from_alarm_manager_style_payload() -> None:
    payload = {
        "alarm": {
            "name": "Front Door detected a person",
            "conditions": [{"condition": {"type": "is", "source": "person"}}],
            "triggers": [{"key": "person", "device": "1C6A1B0E8173"}],
        }
    }

    normalized = normalize_webhook_payload(payload, {})

    assert normalized["primary_detection_type"] == "person"
    assert normalized["device_ids"] == ["1C6A1B0E8173"]
    assert normalized["event_types"] == ["unifi_protect_bridge_person"]


def test_normalize_query_only_doorbell_ring_alias() -> None:
    normalized = normalize_webhook_payload(
        {},
        {
            "alarm": "Front doorbell ring",
            "source": "doorbell",
            "device": "1C6A1B0E8173",
        },
    )

    assert normalized["alarm_name"] == "Front doorbell ring"
    assert normalized["detection_types"] == ["ring"]
    assert normalized["device_ids"] == ["1C6A1B0E8173"]


def test_normalize_audio_alarm_alias() -> None:
    normalized = normalize_webhook_payload(
        {
            "alarm": {
                "name": "Kitchen heard smoke",
                "conditions": [{"condition": {"type": "is", "source": "audio_alarm_smoke"}}],
                "triggers": [{"device": "84784828725C"}],
            }
        },
        {},
    )

    assert normalized["primary_detection_type"] == "audio_alarm_smoke"
    assert normalized["device_ids"] == ["84784828725C"]


def test_normalize_license_plate_alias() -> None:
    normalized = normalize_webhook_payload(
        {},
        {
            "alarm": "Driveway detected a license plate",
            "source": "licenseplate",
            "device": "84784828725C",
        },
    )

    assert normalized["primary_detection_type"] == "license_plate_of_interest"
    assert normalized["detection_types"] == ["license_plate_of_interest"]
    assert normalized["device_ids"] == ["84784828725C"]


def test_normalize_audio_baby_cry_alias() -> None:
    normalized = normalize_webhook_payload(
        {},
        {
            "alarm": "Nursery heard baby cry",
            "source": "baby_cry",
            "device": "84784828725C",
        },
    )

    assert normalized["primary_detection_type"] == "audio_alarm_baby_cry"
    assert normalized["detection_types"] == ["audio_alarm_baby_cry"]
    assert normalized["device_ids"] == ["84784828725C"]


def test_normalize_face_name_hint_requires_token_match() -> None:
    normalized = normalize_webhook_payload(
        {
            "alarm": {
                "name": "Network interface changed state",
                "conditions": [],
                "triggers": [],
            }
        },
        {},
    )

    assert normalized["detection_types"] == []
    assert normalized["event_types"] == []


def test_normalize_face_subtype_also_updates_generic_face() -> None:
    normalized = normalize_webhook_payload(
        {},
        {
            "alarm": "Front door known face",
            "source": "known_face",
            "device": "84784828725C",
        },
    )

    assert normalized["primary_detection_type"] == "face_known"
    assert normalized["detection_types"] == ["face_known", "face"]
    assert normalized["event_types"] == [
        "unifi_protect_bridge_face_known",
        "unifi_protect_bridge_face",
    ]


def test_normalize_prefers_trigger_device_over_alarm_scope() -> None:
    normalized = normalize_webhook_payload(
        {
            "alarm": {
                "name": "Known face",
                "sources": [
                    {"device": "SCOPE1", "type": "include"},
                    {"device": "SCOPE2", "type": "include"},
                ],
                "conditions": [{"condition": {"source": "face_known"}}],
                "triggers": [{"key": "face_known", "device": "TRIGGER1"}],
            }
        },
        {},
    )

    assert normalized["device_ids"] == ["TRIGGER1"]


def test_normalize_known_face_extracts_recognized_face_name() -> None:
    normalized = normalize_webhook_payload(
        {
            "alarm": {
                "name": "Known face",
                "conditions": [{"condition": {"source": "face_known"}}],
                "triggers": [
                    {
                        "key": "face_known",
                        "device": "84784828725C",
                        "value": "Alice",
                    }
                ],
            }
        },
        {},
    )

    assert normalized["detection_types"] == ["face_known", "face"]
    assert normalized["trigger_values"] == ["Alice"]
    assert normalized["recognized_face_names"] == ["Alice"]
    assert normalized["primary_recognized_face"] == "Alice"


def test_normalize_smart_detect_event_payload() -> None:
    normalized = normalize_event_payload(
        {
            "type": "smartDetectZone",
            "camera": "586ab7c2bb6423c3fdd47e95",
            "smartDetectTypes": [
                "person",
                "vehicle",
                "face",
                "licensePlate",
                "alrmSmoke",
                "alrmBabyCry",
            ],
            "timestamp": 1763816532675,
        }
    )

    assert normalized["detection_types"] == [
        "person",
        "vehicle",
        "face",
        "license_plate_of_interest",
        "audio_alarm_smoke",
        "audio_alarm_baby_cry",
    ]
    assert normalized["device_ids"] == ["586ab7c2bb6423c3fdd47e95"]
    assert normalized["timestamp_ms"] == 1763816532675


def test_normalize_smart_detect_event_type_is_case_and_separator_tolerant() -> None:
    normalized = normalize_event_payload(
        {
            "type": "smart_detect_zone",
            "camera": "586ab7c2bb6423c3fdd47e95",
            "smartDetectTypes": ["person"],
            "timestamp": 1763816532675,
        }
    )

    assert normalized["detection_types"] == ["person"]


def test_normalize_preserves_zero_timestamp_over_fallbacks() -> None:
    normalized = normalize_event_payload(
        {
            "type": "ring",
            "camera": "1c9a2db4df6efda47a3509be",
            "timestamp": 0,
            "start": 1642971766763,
        }
    )

    assert normalized["timestamp_ms"] == 0
    assert normalized["timestamp_iso"] == "1970-01-01T00:00:00+00:00"


def test_normalize_ignores_out_of_range_timestamp() -> None:
    normalized = normalize_event_payload(
        {
            "type": "ring",
            "camera": "1c9a2db4df6efda47a3509be",
            "timestamp": 10**100,
        }
    )

    assert normalized["timestamp_ms"] == 10**100
    assert normalized["timestamp_iso"] is None


def test_normalize_ring_event_uses_start_when_timestamp_missing() -> None:
    normalized = normalize_event_payload(
        {
            "type": "ring",
            "camera": "1c9a2db4df6efda47a3509be",
            "start": 1642971766763,
            "timestamp": None,
        }
    )

    assert normalized["detection_types"] == ["ring"]
    assert normalized["device_ids"] == ["1c9a2db4df6efda47a3509be"]
    assert normalized["timestamp_ms"] == 1642971766763
