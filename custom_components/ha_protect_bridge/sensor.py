from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory

from .catalog import humanize_source
from .const import STATUS_SENSOR_NAME
from .entry_runtime import get_entry_runtime
from .runtime import BridgeSensorSpec, HaProtectBridgeRuntime


async def async_setup_entry(hass: Any, entry: Any, async_add_entities: Any) -> None:
    del hass
    runtime: HaProtectBridgeRuntime = get_entry_runtime(entry)
    known_sensor_keys: set[str] = set()
    entities = [HaProtectBridgeStatusSensor(runtime)]
    entities.extend(_build_new_timestamp_entities(runtime, known_sensor_keys))
    async_add_entities(entities)

    @callback
    def _async_add_missing_entities() -> None:
        new_entities = _build_new_timestamp_entities(runtime, known_sensor_keys)
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(runtime.async_subscribe(_async_add_missing_entities))


def _build_new_timestamp_entities(
    runtime: HaProtectBridgeRuntime,
    known_sensor_keys: set[str],
) -> list[HaProtectBridgeTimestampSensor]:
    new_entities: list[HaProtectBridgeTimestampSensor] = []
    for spec in runtime.iter_sensor_specs():
        if spec.key in known_sensor_keys:
            continue
        known_sensor_keys.add(spec.key)
        new_entities.append(HaProtectBridgeTimestampSensor(runtime, spec))
    return new_entities


class HaProtectBridgeStatusSensor(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = STATUS_SENSOR_NAME
    _attr_icon = "mdi:webhook"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, runtime: HaProtectBridgeRuntime) -> None:
        self._runtime = runtime
        self._attr_unique_id = f"{runtime.entry.entry_id}_status"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._runtime.async_subscribe(self.async_write_ha_state))

    @property
    def native_value(self) -> str:
        return self._runtime.status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._runtime.get_status_attributes()

    @property
    def device_info(self) -> Any:
        return self._runtime.bridge_device_info()


class HaProtectBridgeTimestampSensor(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, runtime: HaProtectBridgeRuntime, spec: BridgeSensorSpec) -> None:
        self._runtime = runtime
        self._spec = spec
        self._attr_unique_id = spec.unique_id
        self._attr_name = spec.name
        self._attr_icon = spec.icon

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._runtime.async_subscribe(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return self._runtime.has_sensor_spec(self._spec.key)

    @property
    def native_value(self) -> Any:
        if not self.available:
            return None
        return self._runtime.get_sensor_state(self._spec.key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.available:
            attributes = {
                "source": self._spec.source,
                "source_label": humanize_source(self._spec.source),
            }
            if self._spec.camera_key:
                attributes["camera_key"] = self._spec.camera_key
            return attributes
        return self._runtime.get_sensor_attributes(self._spec.key)

    @property
    def device_info(self) -> Any:
        if self._spec.camera_key:
            return self._runtime.camera_device_info(self._spec.camera_key)
        return self._runtime.bridge_device_info()
