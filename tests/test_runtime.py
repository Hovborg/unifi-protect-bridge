from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from homeassistant.components import webhook
from homeassistant.helpers import network

from custom_components.unifi_protect_bridge.const import (
    CONF_EVENT_BACKFILL_LIMIT,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    CONF_WEBHOOK_ID,
    DEFAULT_EVENT_BACKFILL_LIMIT,
    MAX_EVENT_BACKFILL_LIMIT,
)
from custom_components.unifi_protect_bridge.protect_api import ProtectApiError
from custom_components.unifi_protect_bridge.runtime import BridgeSensorSpec, HaProtectBridgeRuntime


def test_runtime_backfill_limit_uses_default_and_clamps_options() -> None:
    runtime = HaProtectBridgeRuntime(SimpleNamespace(), _mock_entry({}))
    assert runtime._event_backfill_limit() == DEFAULT_EVENT_BACKFILL_LIMIT

    runtime = HaProtectBridgeRuntime(SimpleNamespace(), _mock_entry({CONF_EVENT_BACKFILL_LIMIT: 0}))
    assert runtime._event_backfill_limit() == 0

    runtime = HaProtectBridgeRuntime(
        SimpleNamespace(),
        _mock_entry({CONF_EVENT_BACKFILL_LIMIT: MAX_EVENT_BACKFILL_LIMIT + 1}),
    )
    assert runtime._event_backfill_limit() == MAX_EVENT_BACKFILL_LIMIT


def test_runtime_backfill_skips_event_fetch_when_limit_is_zero() -> None:
    runtime = HaProtectBridgeRuntime(
        SimpleNamespace(),
        _mock_entry({CONF_EVENT_BACKFILL_LIMIT: 0}),
    )
    called = False

    async def _async_get_events(**kwargs):
        nonlocal called
        del kwargs
        called = True
        return []

    runtime._api.async_get_events = _async_get_events

    asyncio.run(runtime._async_backfill_recent_events())

    assert called is False
    assert runtime.get_status_attributes()["last_backfill_event_count"] == 0
    assert runtime.get_status_attributes()["last_backfill_applied_count"] == 0


def test_runtime_backfill_tracks_event_and_applied_counts() -> None:
    runtime = HaProtectBridgeRuntime(SimpleNamespace(), _mock_entry({}))
    runtime._sensor_specs = {
        "global:person": BridgeSensorSpec(
            key="global:person",
            unique_id="entry-1_global_person",
            name="Last person",
            icon=None,
            source="person",
        )
    }

    async def _async_get_events(**kwargs):
        del kwargs
        return [
            {
                "type": "smartDetectZone",
                "smartDetectTypes": ["person"],
                "timestamp": 1770000000000,
            },
            {
                "type": "unknownEvent",
                "timestamp": 1770000001000,
            },
        ]

    runtime._api.async_get_events = _async_get_events

    asyncio.run(runtime._async_backfill_recent_events())

    attributes = runtime.get_status_attributes()
    assert attributes["last_backfill_event_count"] == 2
    assert attributes["last_backfill_changed_event_count"] == 1
    assert attributes["last_backfill_applied_count"] == 1
    assert attributes["last_backfill_changed_sensor_count"] == 1
    assert attributes["last_backfill_at"] is not None
    assert attributes["last_backfill_error"] is None
    assert attributes["known_sensor_count"] == 1
    assert attributes["unknown_sensor_count"] == 0


def test_runtime_backfill_reports_non_fatal_errors() -> None:
    runtime = HaProtectBridgeRuntime(SimpleNamespace(), _mock_entry({}))

    async def _async_get_events(**kwargs):
        del kwargs
        raise ProtectApiError("limit rejected")

    runtime._api.async_get_events = _async_get_events

    asyncio.run(runtime._async_backfill_recent_events())

    attributes = runtime.get_status_attributes()
    assert attributes["last_backfill_event_count"] == 0
    assert attributes["last_backfill_error"] == "limit rejected"
    assert attributes["last_sync_error"] is None


def test_runtime_backfill_paginates_protect_events() -> None:
    runtime = HaProtectBridgeRuntime(
        SimpleNamespace(),
        _mock_entry({CONF_EVENT_BACKFILL_LIMIT: 250}),
    )
    calls = []

    async def _async_get_events(**kwargs):
        calls.append(dict(kwargs))
        offset = kwargs["offset"]
        limit = kwargs["limit"]
        return [
            {
                "id": f"event-{offset + index}",
                "type": "unknownEvent",
                "timestamp": 1770000000000 + index,
            }
            for index in range(limit)
        ]

    runtime._api.async_get_events = _async_get_events

    asyncio.run(runtime._async_backfill_recent_events())

    assert [call["limit"] for call in calls] == [100, 100, 50]
    assert [call["offset"] for call in calls] == [0, 100, 200]
    assert runtime.get_status_attributes()["last_backfill_event_count"] == 250


def test_runtime_build_webhook_url_prefers_home_assistant_instance_url(monkeypatch) -> None:
    runtime = HaProtectBridgeRuntime(SimpleNamespace(), _mock_entry({}))
    monkeypatch.setattr(network, "get_url", lambda _hass: "http://ha.internal:8123")

    assert runtime._build_webhook_url() == "http://ha.internal:8123/api/webhook/webhook-id"
    assert runtime.get_status_attributes()["webhook_url_source"] == "home_assistant_instance_url"


def test_runtime_build_webhook_url_falls_back_to_webhook_generated_url(monkeypatch) -> None:
    runtime = HaProtectBridgeRuntime(SimpleNamespace(), _mock_entry({}))

    def _raise_no_url(_hass):
        raise network.NoURLAvailableError

    monkeypatch.setattr(network, "get_url", _raise_no_url)
    monkeypatch.setattr(
        webhook,
        "async_generate_url",
        lambda _hass, webhook_id: f"https://external.example/api/webhook/{webhook_id}",
    )

    assert (
        runtime._build_webhook_url()
        == "https://external.example/api/webhook/webhook-id"
    )
    assert runtime.get_status_attributes()["webhook_url_source"] == "home_assistant_generated"


def test_runtime_status_attributes_do_not_expose_webhook_secret() -> None:
    runtime = HaProtectBridgeRuntime(SimpleNamespace(), _mock_entry({}))
    runtime._webhook_url = "http://ha.local/api/webhook/secret"
    runtime._webhook_url_source = "home_assistant_instance_url"

    attributes = runtime.get_status_attributes()

    assert "webhook_url" not in attributes
    assert "webhook_path" not in attributes
    assert attributes["webhook_configured"] is True
    assert attributes["webhook_url_source"] == "home_assistant_instance_url"
    assert attributes["webhook_base_url_override_configured"] is False


def test_runtime_status_attributes_report_webhook_override_source() -> None:
    runtime = HaProtectBridgeRuntime(
        SimpleNamespace(),
        _mock_entry({}, data_updates={"webhook_base_url": "http://ha.local:8123"}),
    )

    attributes = runtime.get_status_attributes()

    assert attributes["webhook_url_source"] == "override"
    assert attributes["webhook_base_url_override_configured"] is True


def test_runtime_last_webhook_at_uses_receive_time_not_event_timestamp() -> None:
    runtime = HaProtectBridgeRuntime(SimpleNamespace(), _mock_entry({}))
    normalized = {
        "alarm_name": "old_person",
        "detection_types": ["person"],
        "primary_detection_type": "person",
        "device_ids": [],
        "source_values": ["person"],
        "timestamp_ms": 946684800000,
        "timestamp_iso": "2000-01-01T00:00:00+00:00",
        "query": {},
        "raw_payload": {},
        "event_types": ["unifi_protect_bridge_person"],
    }

    before = datetime.now(UTC)
    asyncio.run(runtime.async_process_webhook(normalized))

    assert runtime.last_webhook_at is not None
    assert runtime.last_webhook_at >= before


def test_runtime_webhook_notifies_listeners_even_without_sensor_change() -> None:
    runtime = HaProtectBridgeRuntime(SimpleNamespace(), _mock_entry({}))
    calls = 0

    def _listener() -> None:
        nonlocal calls
        calls += 1

    runtime.async_subscribe(_listener)
    normalized = {
        "alarm_name": "unrecognized",
        "detection_types": [],
        "primary_detection_type": None,
        "device_ids": [],
        "source_values": [],
        "timestamp_ms": None,
        "timestamp_iso": None,
        "query": {},
        "raw_payload": {},
        "event_types": [],
    }

    asyncio.run(runtime.async_process_webhook(normalized))

    assert runtime.last_webhook_at is not None
    assert calls == 1
    attributes = runtime.get_status_attributes()
    assert attributes["webhook_count"] == 1
    assert attributes["last_webhook_detection_types"] == []


def test_runtime_webhook_tracks_unmatched_camera_ids() -> None:
    runtime = HaProtectBridgeRuntime(SimpleNamespace(), _mock_entry({}))
    runtime.catalog = {"lookup": {}, "cameras": [], "managed_sources": ["person"]}
    runtime._sensor_specs = {
        "global:person": BridgeSensorSpec(
            key="global:person",
            unique_id="entry-1_global_person",
            name="Last person",
            icon=None,
            source="person",
        )
    }
    normalized = {
        "alarm_name": "person",
        "detection_types": ["person"],
        "primary_detection_type": "person",
        "device_ids": ["unknown-camera"],
        "source_values": ["person"],
        "timestamp_ms": 1770000000000,
        "timestamp_iso": "2026-02-28T08:00:00+00:00",
        "query": {},
        "raw_payload": {},
        "event_types": ["unifi_protect_bridge_person"],
    }

    asyncio.run(runtime.async_process_webhook(normalized))

    attributes = runtime.get_status_attributes()
    assert attributes["webhook_count"] == 1
    assert attributes["unmatched_webhook_count"] == 1
    assert attributes["last_unmatched_webhook_at"] is not None
    assert attributes["last_webhook_matched_camera_count"] == 0
    assert attributes["last_webhook_changed_sensor_count"] == 1


def test_runtime_buffers_webhooks_until_sensor_specs_exist() -> None:
    runtime = HaProtectBridgeRuntime(SimpleNamespace(), _mock_entry({}))
    calls = 0

    def _listener() -> None:
        nonlocal calls
        calls += 1

    runtime.async_subscribe(_listener)
    normalized = {
        "alarm_name": "person",
        "detection_types": ["person"],
        "primary_detection_type": "person",
        "device_ids": ["cam-1"],
        "source_values": ["person"],
        "timestamp_ms": 1770000000000,
        "timestamp_iso": "2026-02-28T08:00:00+00:00",
        "query": {},
        "raw_payload": {},
        "event_types": ["unifi_protect_bridge_person"],
    }

    matched = asyncio.run(runtime.async_process_webhook(normalized))

    assert matched == []
    assert runtime.get_status_attributes()["pending_webhook_count"] == 1
    assert calls == 1

    runtime.catalog = {
        "lookup": {"CAM1": "cam-1"},
        "managed_sources": ["person"],
        "cameras": [
            {
                "camera_key": "cam-1",
                "camera_id": "cam-1",
                "device_mac": "CAM1",
                "name": "Camera",
                "supported_sources": ["person"],
            }
        ],
    }
    runtime._rebuild_sensor_specs()
    runtime._apply_pending_webhook_events()

    attributes = runtime.get_status_attributes()
    assert attributes["pending_webhook_count"] == 0
    assert attributes["known_sensor_count"] == 2
    assert calls == 2


def test_runtime_sync_removes_duplicate_managed_automations() -> None:
    runtime = HaProtectBridgeRuntime(SimpleNamespace(), _mock_entry({}))
    runtime.catalog = {
        "nvr_id": "nvr",
        "nvr_name": "Protect",
        "lookup": {},
        "managed_sources": ["person"],
        "cameras": [
            {
                "device_mac": "84784828725C",
                "supported_sources": ["person"],
            }
        ],
    }
    runtime._webhook_url = "http://ha.local/api/webhook/test"
    deleted: list[str] = []
    created: list[dict[str, object]] = []

    async def _async_delete_automation(automation_id: str) -> None:
        deleted.append(automation_id)

    async def _async_create_automation(payload: dict[str, object]) -> dict[str, object]:
        created.append(payload)
        return {"id": "created", **payload}

    runtime._api.async_delete_automation = _async_delete_automation
    runtime._api.async_create_automation = _async_create_automation

    current = {
        "id": "current",
        "name": "UniFi Protect Bridge: person",
        "enable": True,
        "sources": [{"device": "84784828725C"}],
        "conditions": [{"condition": {"type": "is", "source": "person"}}],
        "actions": [
            {
                "type": "HTTP_REQUEST",
                "metadata": {
                    "url": "http://ha.local/api/webhook/test?source=person",
                    "method": "POST",
                    "timeout": 30000,
                    "useThumbnail": True,
                    "headers": [],
                },
            }
        ],
    }
    legacy_duplicate = {**current, "id": "legacy", "name": "HA Protect Bridge: person"}
    user_automation = {
        **current,
        "id": "user",
        "name": "User managed person webhook",
    }

    asyncio.run(
        runtime._async_sync_managed_automations(
            [legacy_duplicate, user_automation, current],
        )
    )

    assert deleted == ["legacy"]
    assert created == []
    assert runtime._managed_automations["person"]["id"] == "current"


def test_runtime_sync_continues_when_one_automation_source_is_rejected() -> None:
    runtime = HaProtectBridgeRuntime(SimpleNamespace(), _mock_entry({}))
    runtime.catalog = {
        "nvr_id": "nvr",
        "nvr_name": "Protect",
        "lookup": {},
        "managed_sources": ["person", "face"],
        "cameras": [
            {
                "device_mac": "84784828725C",
                "supported_sources": ["person", "face"],
            }
        ],
    }
    runtime._webhook_url = "http://ha.local/api/webhook/test"
    created_sources: list[str] = []

    async def _async_create_automation(payload: dict[str, object]) -> dict[str, object]:
        source = payload["conditions"][0]["condition"]["source"]
        created_sources.append(source)
        if source == "face":
            raise ProtectApiError("unsupported source")
        return {"id": f"created-{source}", **payload}

    runtime._api.async_create_automation = _async_create_automation

    asyncio.run(runtime._async_sync_managed_automations([]))

    assert created_sources == ["person", "face"]
    assert sorted(runtime._managed_automations) == ["person"]
    attributes = runtime.get_status_attributes()
    assert attributes["managed_automation_count"] == 1
    assert attributes["automation_sync_error_count"] == 1
    assert attributes["automation_sync_errors"] == {"face": "unsupported source"}


def _mock_entry(
    options: dict[str, int],
    *,
    data_updates: dict[str, object] | None = None,
) -> SimpleNamespace:
    data = {
        CONF_HOST: "protect.local",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "secret",
        CONF_VERIFY_SSL: False,
        CONF_WEBHOOK_ID: "webhook-id",
    }
    if data_updates:
        data.update(data_updates)
    return SimpleNamespace(
        entry_id="entry-1",
        data=data,
        options=options,
    )
