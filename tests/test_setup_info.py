from custom_components.ha_protect_bridge.setup_info import build_setup_message


def test_build_setup_message_includes_webhook_url_and_events() -> None:
    message = build_setup_message(
        "https://ha.example.com/api/webhook/abc",
        "/api/webhook/abc",
        ["person", "animal"],
    )

    assert "https://ha.example.com/api/webhook/abc" in message
    assert "ha_protect_bridge_person" in message
    assert "ha_protect_bridge_animal" in message
    assert "Official note:" in message
