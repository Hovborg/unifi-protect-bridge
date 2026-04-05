from custom_components.ha_protect_bridge.automation_payloads import (
    automation_needs_replace,
    build_managed_automation_name,
    build_managed_automation_payload,
    build_webhook_target_url,
    managed_source_from_automation,
)


def test_build_webhook_target_url_preserves_existing_query() -> None:
    url = build_webhook_target_url("http://ha.local/api/webhook/test?foo=bar", "person")

    assert "foo=bar" in url
    assert "source=person" in url


def test_build_managed_automation_payload_has_expected_shape() -> None:
    payload = build_managed_automation_payload(
        "person",
        ["84784828725C", "1C6A1B0E8173"],
        "http://ha.local/api/webhook/test",
    )

    assert payload["name"] == build_managed_automation_name("person")
    assert payload["conditions"] == [{"condition": {"type": "is", "source": "person"}}]
    assert payload["actions"][0]["metadata"]["url"].endswith("source=person")
    assert payload["actions"][0]["metadata"]["useThumbnail"] is True


def test_managed_source_from_automation_reads_name_prefix() -> None:
    payload = build_managed_automation_payload(
        "audio_alarm_smoke",
        ["84784828725C"],
        "http://ha.local/api/webhook/test",
    )

    assert managed_source_from_automation(payload) == "audio_alarm_smoke"


def test_automation_needs_replace_detects_url_change() -> None:
    existing = build_managed_automation_payload(
        "person",
        ["84784828725C"],
        "http://ha.local/api/webhook/test",
    )
    desired = build_managed_automation_payload(
        "person",
        ["84784828725C"],
        "http://ha.local/api/webhook/other",
    )

    assert automation_needs_replace(existing, desired) is True
