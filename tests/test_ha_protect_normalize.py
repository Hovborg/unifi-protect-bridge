from custom_components.ha_protect_bridge.normalize import normalize_webhook_payload


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
    assert normalized["event_types"] == ["ha_protect_bridge_person"]


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
