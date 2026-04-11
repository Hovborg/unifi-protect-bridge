from custom_components.unifi_protect_bridge.const import (
    EVENT_DETECTION,
    EVENT_WEBHOOK,
    TYPED_DETECTION_EVENTS,
)
from custom_components.unifi_protect_bridge.setup_info import build_setup_message


def test_build_setup_message_includes_setup_status_and_sources() -> None:
    message = build_setup_message(
        "https://ha.example.com/api/webhook/abc",
        "/api/webhook/abc",
        ["person", "animal"],
        automation_count=2,
    )

    assert "api/webhook/abc" not in message
    assert "Webhook endpoint: `registered`" in message
    assert "Managed automation count: `2`" in message
    assert "unifi_protect_bridge_person" in message
    assert "unifi_protect_bridge_animal" in message
    assert "last_webhook_at" in message
    assert "Webhook base URL override" in message
    assert "Operational note:" in message


def test_build_setup_message_defaults_to_all_detection_events() -> None:
    message = build_setup_message(None, "/api/webhook/abc")

    assert EVENT_WEBHOOK in message
    assert EVENT_DETECTION in message
    for event_type in TYPED_DETECTION_EVENTS:
        assert event_type in message
