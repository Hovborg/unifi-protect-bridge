from custom_components.unifi_protect_bridge.automation_payloads import (
    build_managed_automation_payload,
)
from custom_components.unifi_protect_bridge.automation_plan import (
    build_managed_automation_plan,
    plan_delete_count,
    plan_has_missing_delete_ids,
)


def test_plan_creates_missing_managed_automation() -> None:
    plan = build_managed_automation_plan(_catalog(["person"]), [], _webhook_url())

    assert plan["summary"]["create"] == 1
    assert plan["actions"][0]["action"] == "create"
    assert plan["actions"][0]["source"] == "person"


def test_plan_keeps_current_and_deletes_legacy_duplicate() -> None:
    current = build_managed_automation_payload("person", ["84784828725C"], _webhook_url())
    current["id"] = "current"
    legacy = build_managed_automation_payload("person", ["84784828725C"], _webhook_url())
    legacy["id"] = "legacy"
    legacy["name"] = "HA Protect Bridge: person"

    plan = build_managed_automation_plan(_catalog(["person"]), [legacy, current], _webhook_url())

    assert [action["action"] for action in plan["actions"]] == ["keep", "delete_duplicate"]
    assert plan["actions"][0]["id"] == "current"
    assert plan["actions"][1]["id"] == "legacy"
    assert plan_delete_count(plan) == 1


def test_plan_replaces_mismatched_managed_automation() -> None:
    existing = build_managed_automation_payload(
        "person",
        ["84784828725C"],
        "http://old.example/api/webhook/old",
    )
    existing["id"] = "old"

    plan = build_managed_automation_plan(_catalog(["person"]), [existing], _webhook_url())

    assert plan["summary"]["replace"] == 1
    assert plan["actions"][0]["delete_ids"] == ["old"]
    assert plan_delete_count(plan) == 1


def test_plan_deletes_stale_managed_but_ignores_user_webhook() -> None:
    stale = build_managed_automation_payload("ring", ["84784828725C"], _webhook_url())
    stale["id"] = "stale"
    user_owned = {
        "id": "user",
        "name": "User managed person webhook",
        "actions": [
            {
                "type": "HTTP_REQUEST",
                "metadata": {"url": f"{_webhook_url()}?source=person"},
            }
        ],
    }

    plan = build_managed_automation_plan(_catalog(["person"]), [stale, user_owned], _webhook_url())

    assert plan["summary"]["create"] == 1
    assert plan["summary"]["delete_stale"] == 1
    assert plan["summary"]["ignored_user_owned"] == 1
    assert any(
        action["action"] == "delete_stale" and action["id"] == "stale"
        for action in plan["actions"]
    )


def test_plan_detects_missing_delete_id() -> None:
    stale = build_managed_automation_payload("ring", ["84784828725C"], _webhook_url())

    plan = build_managed_automation_plan(_catalog(["person"]), [stale], _webhook_url())

    assert plan_has_missing_delete_ids(plan) is True


def _catalog(sources: list[str]) -> dict[str, object]:
    return {
        "nvr_id": "nvr",
        "nvr_name": "Protect",
        "managed_sources": sources,
        "cameras": [
            {
                "device_mac": "84784828725C",
                "supported_sources": sources,
            }
        ],
    }


def _webhook_url() -> str:
    return "http://ha.local/api/webhook/test"
