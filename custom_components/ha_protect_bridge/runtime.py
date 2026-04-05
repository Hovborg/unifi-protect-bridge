from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.components import webhook
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo

from .automation_payloads import (
    automation_needs_replace,
    build_managed_automation_payload,
    map_managed_automations,
)
from .catalog import build_camera_catalog, camera_by_key, humanize_source, resolve_cameras
from .const import (
    BACKFILL_EVENT_TYPES,
    CONF_HOST,
    CONF_VERIFY_SSL,
    CONF_WEBHOOK_BASE_URL,
    CONF_WEBHOOK_ID,
    DOMAIN,
    INITIAL_EVENT_BACKFILL_LIMIT,
    SOURCE_ICONS,
)
from .normalize import normalize_event_payload
from .protect_api import ProtectApiClient, ProtectApiError

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class BridgeSensorSpec:
    key: str
    unique_id: str
    name: str
    icon: str | None
    source: str
    camera_key: str | None = None


class HaProtectBridgeRuntime:
    def __init__(self, hass: HomeAssistant, entry: Any) -> None:
        self.hass = hass
        self.entry = entry
        self.catalog: dict[str, Any] = {
            "nvr_id": None,
            "nvr_name": "UniFi Protect",
            "cameras": [],
            "lookup": {},
            "managed_sources": [],
        }
        self._api = ProtectApiClient(
            entry.data[CONF_HOST],
            entry.data["username"],
            entry.data["password"],
            entry.data[CONF_VERIFY_SSL],
        )
        self._listeners: list[CALLBACK_TYPE] = []
        self._sensor_specs: dict[str, BridgeSensorSpec] = {}
        self._timestamps: dict[str, datetime] = {}
        self._event_summaries: dict[str, dict[str, Any]] = {}
        self._managed_automations: dict[str, dict[str, Any]] = {}
        self._webhook_url: str | None = None
        self._webhook_path = webhook.async_generate_path(entry.data[CONF_WEBHOOK_ID])
        self.last_sync_at: datetime | None = None
        self.last_sync_error: str | None = None
        self.last_webhook_at: datetime | None = None

    @property
    def webhook_url(self) -> str | None:
        return self._webhook_url

    @property
    def webhook_path(self) -> str:
        return self._webhook_path

    @property
    def managed_sources(self) -> list[str]:
        return list(self.catalog.get("managed_sources") or [])

    @property
    def managed_automation_count(self) -> int:
        return len(self._managed_automations)

    @property
    def status(self) -> str:
        return "error" if self.last_sync_error else "ready"

    async def async_initialize(self) -> None:
        await self._api.async_setup()
        await self.async_resync()

    async def async_resync(self) -> None:
        try:
            bootstrap = await self._api.async_get_bootstrap()
            self.catalog = build_camera_catalog(bootstrap)
            self._webhook_url = self._build_webhook_url()
            automations = await self._api.async_get_automations()
            await self._async_sync_managed_automations(automations)
            self._rebuild_sensor_specs()
            self._seed_timestamps_from_catalog()
            await self._async_backfill_recent_events()
            self.last_sync_at = datetime.now(UTC)
            self.last_sync_error = None
            self._notify_listeners()
        except Exception as err:
            self.last_sync_error = str(err)
            self._notify_listeners()
            raise

    async def async_shutdown(self) -> None:
        await self._api.async_close()

    async def async_process_webhook(self, normalized: dict[str, Any]) -> list[dict[str, Any]]:
        timestamp = _timestamp_from_normalized(normalized)
        self.last_webhook_at = timestamp
        changed, matched_cameras = self._apply_normalized_event(normalized, timestamp)

        if changed:
            self._notify_listeners()

        return matched_cameras

    @callback
    def async_subscribe(self, listener: CALLBACK_TYPE) -> CALLBACK_TYPE:
        self._listeners.append(listener)

        @callback
        def _unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _unsubscribe

    def iter_sensor_specs(self) -> list[BridgeSensorSpec]:
        return list(self._sensor_specs.values())

    def get_sensor_state(self, sensor_key: str) -> datetime | None:
        return self._timestamps.get(sensor_key)

    def get_sensor_attributes(self, sensor_key: str) -> dict[str, Any]:
        spec = self._sensor_specs[sensor_key]
        attributes: dict[str, Any] = {
            "source": spec.source,
            "source_label": humanize_source(spec.source),
        }
        if spec.camera_key:
            camera = camera_by_key(self.catalog, spec.camera_key)
            if camera:
                attributes.update(
                    {
                        "camera_name": camera["name"],
                        "camera_id": camera["camera_id"],
                        "camera_mac": camera["device_mac"],
                    }
                )
        summary = self._event_summaries.get(sensor_key)
        if summary:
            attributes.update(summary)
        return attributes

    def get_status_attributes(self) -> dict[str, Any]:
        return {
            "host": self.entry.data[CONF_HOST],
            "verify_ssl": self.entry.data[CONF_VERIFY_SSL],
            "webhook_path": self.webhook_path,
            "webhook_url": self.webhook_url,
            "webhook_base_url_override": self.entry.data.get(CONF_WEBHOOK_BASE_URL),
            "nvr_id": self.catalog.get("nvr_id"),
            "nvr_name": self.catalog.get("nvr_name"),
            "camera_count": len(self.catalog.get("cameras") or []),
            "managed_sources": self.managed_sources,
            "managed_automation_count": self.managed_automation_count,
            "last_sync_at": _isoformat(self.last_sync_at),
            "last_sync_error": self.last_sync_error,
            "last_webhook_at": _isoformat(self.last_webhook_at),
        }

    def bridge_device_info(self) -> DeviceInfo:
        host = self.entry.data[CONF_HOST]
        configuration_url = host if "://" in host else f"https://{host}"
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            manufacturer="Ubiquiti",
            model="UniFi Protect Bridge",
            name=f"{self.catalog.get('nvr_name') or 'UniFi Protect'} Bridge",
            configuration_url=configuration_url,
        )

    def camera_device_info(self, camera_key: str) -> DeviceInfo:
        camera = camera_by_key(self.catalog, camera_key) or {"name": camera_key, "model": "Camera"}
        return DeviceInfo(
            identifiers={(DOMAIN, camera_key)},
            manufacturer="Ubiquiti",
            model=camera.get("model") or "UniFi Protect Camera",
            name=camera.get("name") or camera_key,
            via_device=(DOMAIN, self.entry.entry_id),
        )

    def _build_webhook_url(self) -> str:
        override = (self.entry.data.get(CONF_WEBHOOK_BASE_URL) or "").strip()
        if override:
            return f"{override.rstrip('/')}" + self.webhook_path

        try:
            generated = webhook.async_generate_url(self.hass, self.entry.data[CONF_WEBHOOK_ID])
        except Exception as err:
            raise ProtectApiError(
                "Could not determine a full Home Assistant webhook URL. Set webhook_base_url."
            ) from err

        if not generated:
            raise ProtectApiError(
                "Home Assistant returned an empty webhook URL. Set webhook_base_url."
            )
        return generated

    async def _async_sync_managed_automations(self, automations: list[dict[str, Any]]) -> None:
        desired_by_source = self._desired_automations()
        existing_by_source = map_managed_automations(automations)
        managed: dict[str, dict[str, Any]] = {}

        for source, desired in desired_by_source.items():
            existing = existing_by_source.pop(source, None)
            if existing and not automation_needs_replace(existing, desired):
                managed[source] = dict(existing)
                continue

            if existing and existing.get("id"):
                await self._api.async_delete_automation(existing["id"])
                _LOGGER.info("Replaced managed Protect automation for %s", source)
            else:
                _LOGGER.info("Creating managed Protect automation for %s", source)

            created = await self._api.async_create_automation(desired)
            managed[source] = created or desired

        for source, stale in existing_by_source.items():
            stale_id = stale.get("id")
            if stale_id:
                await self._api.async_delete_automation(stale_id)
                _LOGGER.info("Removed stale managed Protect automation for %s", source)

        self._managed_automations = managed

    def _desired_automations(self) -> dict[str, dict[str, Any]]:
        desired: dict[str, dict[str, Any]] = {}
        for source in self.managed_sources:
            device_macs = [
                camera["device_mac"]
                for camera in self.catalog.get("cameras") or []
                if camera.get("device_mac") and source in (camera.get("supported_sources") or [])
            ]
            if not device_macs:
                continue
            desired[source] = build_managed_automation_payload(
                source,
                device_macs,
                self.webhook_url or "",
            )
        return desired

    def _rebuild_sensor_specs(self) -> None:
        sensor_specs: dict[str, BridgeSensorSpec] = {}

        for source in self.managed_sources:
            key = f"global:{source}"
            sensor_specs[key] = BridgeSensorSpec(
                key=key,
                unique_id=f"{self.entry.entry_id}_global_{source}",
                name=f"Last {humanize_source(source)}",
                icon=SOURCE_ICONS.get(source),
                source=source,
            )

        for camera in self.catalog.get("cameras") or []:
            for source in camera.get("supported_sources") or []:
                key = f"{camera['camera_key']}:{source}"
                sensor_specs[key] = BridgeSensorSpec(
                    key=key,
                    unique_id=f"{self.entry.entry_id}_{camera['camera_key']}_{source}",
                    name=f"Last {humanize_source(source)}",
                    icon=SOURCE_ICONS.get(source),
                    source=source,
                    camera_key=camera["camera_key"],
                )

        self._sensor_specs = sensor_specs

    async def _async_backfill_recent_events(self) -> None:
        try:
            events = await self._api.async_get_events(
                limit=INITIAL_EVENT_BACKFILL_LIMIT,
                types=list(BACKFILL_EVENT_TYPES),
                sorting="desc",
            )
        except ProtectApiError as err:
            _LOGGER.warning("Could not backfill Protect events: %s", err)
            return

        for event in events:
            normalized = normalize_event_payload(event)
            if not normalized.get("detection_types"):
                continue
            timestamp = _timestamp_from_normalized(normalized)
            self._apply_normalized_event(normalized, timestamp)

    def _seed_timestamps_from_catalog(self) -> None:
        for camera in self.catalog.get("cameras") or []:
            for source, key in (("motion", "last_motion_ms"), ("ring", "last_ring_ms")):
                timestamp_ms = camera.get(key)
                if not timestamp_ms:
                    continue
                device_id = (
                    camera.get("camera_id")
                    or camera.get("device_mac")
                    or camera["camera_key"]
                )
                normalized = {
                    "alarm_name": f"bootstrap_{source}",
                    "detection_types": [source],
                    "primary_detection_type": source,
                    "device_ids": [device_id],
                    "source_values": [source],
                    "timestamp_ms": timestamp_ms,
                    "timestamp_iso": None,
                    "query": {},
                    "raw_payload": {"source": "bootstrap"},
                    "event_types": [],
                }
                timestamp = _timestamp_from_normalized(normalized)
                self._apply_normalized_event(normalized, timestamp)

    def _apply_normalized_event(
        self,
        normalized: dict[str, Any],
        timestamp: datetime,
    ) -> tuple[bool, list[dict[str, Any]]]:
        matched_cameras = resolve_cameras(self.catalog, normalized.get("device_ids") or [])
        changed = False

        for source in normalized.get("detection_types") or []:
            global_key = f"global:{source}"
            if global_key in self._sensor_specs:
                changed |= self._update_sensor_state(global_key, timestamp, normalized)

            for camera in matched_cameras:
                sensor_key = f"{camera['camera_key']}:{source}"
                if sensor_key not in self._sensor_specs:
                    continue
                changed |= self._update_sensor_state(sensor_key, timestamp, normalized)

        return changed, matched_cameras

    def _update_sensor_state(
        self,
        sensor_key: str,
        timestamp: datetime,
        normalized: dict[str, Any],
    ) -> bool:
        existing = self._timestamps.get(sensor_key)
        if existing is not None and existing >= timestamp:
            return False

        self._timestamps[sensor_key] = timestamp
        self._event_summaries[sensor_key] = _event_summary(normalized)
        return True

    @callback
    def _notify_listeners(self) -> None:
        for listener in list(self._listeners):
            listener()


def _timestamp_from_normalized(normalized: dict[str, Any]) -> datetime:
    timestamp_ms = normalized.get("timestamp_ms")
    if timestamp_ms:
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
    return datetime.now(UTC)


def _event_summary(normalized: dict[str, Any]) -> dict[str, Any]:
    return {
        "last_alarm_name": normalized.get("alarm_name"),
        "last_detection_types": list(normalized.get("detection_types") or []),
        "last_device_ids": list(normalized.get("device_ids") or []),
        "last_timestamp": normalized.get("timestamp_iso"),
    }


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
