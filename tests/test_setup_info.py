from custom_components.ha_protect_bridge.setup_info import build_setup_message


def test_build_setup_message_includes_webhook_url_and_sources() -> None:
    message = build_setup_message(
        "https://ha.example.com/api/webhook/abc",
        "/api/webhook/abc",
        ["person", "animal"],
        automation_count=2,
    )

    assert "https://ha.example.com/api/webhook/abc" in message
    assert "Managed automation count: `2`" in message
    assert "ha_protect_bridge_person" in message
    assert "ha_protect_bridge_animal" in message
    assert "Operational note:" in message
