from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.restore_state import RestoreEntity

from custom_components.unifi_protect_bridge.runtime import BridgeSensorSpec
from custom_components.unifi_protect_bridge.sensor import (
    HaProtectBridgeTimestampSensor,
    async_setup_entry,
)


class FakeRuntime:
    def __init__(self, specs: list[BridgeSensorSpec]) -> None:
        self.entry = SimpleNamespace(entry_id="entry-1")
        self._specs = {spec.key: spec for spec in specs}
        self._states = {}
        self._restored = []
        self._listeners = []

    def iter_sensor_specs(self) -> list[BridgeSensorSpec]:
        return list(self._specs.values())

    def has_sensor_spec(self, sensor_key: str) -> bool:
        return sensor_key in self._specs

    def get_sensor_state(self, sensor_key: str):
        return self._states.get(sensor_key)

    def restore_sensor_state(self, sensor_key: str, timestamp, attributes: dict) -> bool:
        self._states[sensor_key] = timestamp
        self._restored.append((sensor_key, timestamp, attributes))
        return True

    def get_sensor_attributes(self, sensor_key: str) -> dict[str, str]:
        spec = self._specs[sensor_key]
        return {
            "source": spec.source,
            "source_label": spec.source,
        }

    def bridge_device_info(self) -> dict[str, str]:
        return {}

    def camera_device_info(self, camera_key: str) -> dict[str, str]:
        return {}

    def async_subscribe(self, listener):
        self._listeners.append(listener)

        def _unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _unsubscribe

    def set_specs(self, specs: list[BridgeSensorSpec]) -> None:
        self._specs = {spec.key: spec for spec in specs}

    def emit_update(self) -> None:
        for listener in list(self._listeners):
            listener()


class FakeEntry:
    def __init__(self, entry_id: str, runtime) -> None:
        self.entry_id = entry_id
        self.runtime_data = runtime
        self.unloaders = []

    def async_on_unload(self, callback) -> None:
        self.unloaders.append(callback)


def test_async_setup_entry_adds_new_timestamp_entities_on_runtime_update() -> None:
    motion = BridgeSensorSpec(
        key="global:motion",
        unique_id="entry-1_global_motion",
        name="Last motion",
        icon=None,
        source="motion",
    )
    person = BridgeSensorSpec(
        key="camera-1:person",
        unique_id="entry-1_camera-1_person",
        name="Last person",
        icon=None,
        source="person",
        camera_key="camera-1",
    )
    runtime = FakeRuntime([motion])
    entry = FakeEntry(runtime.entry.entry_id, runtime)
    hass = SimpleNamespace()
    add_calls: list[list[str | None]] = []

    def async_add_entities(entities) -> None:
        add_calls.append([entity.unique_id for entity in entities])

    asyncio.run(async_setup_entry(hass, entry, async_add_entities))

    assert add_calls == [["entry-1_status", "entry-1_global_motion"]]

    runtime.set_specs([motion, person])
    runtime.emit_update()

    assert add_calls[-1] == ["entry-1_camera-1_person"]


def test_timestamp_sensor_restore_mixin_precedes_sensor_entity() -> None:
    mro = HaProtectBridgeTimestampSensor.mro()

    assert mro.index(RestoreEntity) < mro.index(SensorEntity)


def test_timestamp_sensor_becomes_unavailable_when_spec_is_removed() -> None:
    spec = BridgeSensorSpec(
        key="camera-1:person",
        unique_id="entry-1_camera-1_person",
        name="Last person",
        icon=None,
        source="person",
        camera_key="camera-1",
    )
    runtime = FakeRuntime([spec])
    entity = HaProtectBridgeTimestampSensor(runtime, spec)

    assert entity.available is True

    runtime.set_specs([])

    assert entity.available is False
    assert entity.native_value is None
    assert entity.extra_state_attributes == {
        "source": "person",
        "source_label": "person",
        "camera_key": "camera-1",
    }


def test_timestamp_sensor_restores_last_state() -> None:
    spec = BridgeSensorSpec(
        key="camera-1:person",
        unique_id="entry-1_camera-1_person",
        name="Last person",
        icon=None,
        source="person",
        camera_key="camera-1",
    )
    runtime = FakeRuntime([spec])
    entity = HaProtectBridgeTimestampSensor(runtime, spec)
    last_state = SimpleNamespace(
        state="2026-04-11T01:02:03+00:00",
        attributes={
            "last_alarm_name": "smartDetectZone",
            "last_detection_types": ["person"],
            "last_device_ids": ["camera-id"],
            "last_timestamp": "2026-04-11T01:02:03+00:00",
        },
    )

    async def _async_get_last_state():
        return last_state

    entity.async_get_last_state = _async_get_last_state

    asyncio.run(entity.async_added_to_hass())

    assert runtime._restored == [
        (
            "camera-1:person",
            datetime(2026, 4, 11, 1, 2, 3, tzinfo=UTC),
            last_state.attributes,
        )
    ]
    assert entity.native_value == datetime(2026, 4, 11, 1, 2, 3, tzinfo=UTC)
