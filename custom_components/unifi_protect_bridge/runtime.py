from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.components import webhook
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo

from .automation_payloads import (
    automation_needs_replace,
    build_managed_automation_payload,
    group_managed_automations,
)
from .catalog import build_camera_catalog, camera_by_key, humanize_source, resolve_cameras
from .const import (
    BACKFILL_EVENT_TYPES,
    CONF_EVENT_BACKFILL_LIMIT,
    CONF_HOST,
    CONF_VERIFY_SSL,
    CONF_WEBHOOK_BASE_URL,
    CONF_WEBHOOK_ID,
    DEFAULT_EVENT_BACKFILL_LIMIT,
    DOMAIN,
    MAX_EVENT_BACKFILL_LIMIT,
    SOURCE_ICONS,
)
from .normalize import normalize_event_payload
from .protect_api import PROTECT_EVENTS_REQUEST_LIMIT, ProtectApiClient, ProtectApiError

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
        self._automation_sync_errors: dict[str, str] = {}
        self._webhook_url: str | None = None
        self._webhook_url_source: str | None = None
        self._webhook_path = webhook.async_generate_path(entry.data[CONF_WEBHOOK_ID])
        self._last_backfill_event_count = 0
        self._last_backfill_applied_count = 0
        self._last_backfill_changed_sensor_count = 0
        self._last_backfill_at: datetime | None = None
        self._last_backfill_error: str | None = None
        self._webhook_count = 0
        self._unmatched_webhook_count = 0
        self._last_unmatched_webhook_at: datetime | None = None
        self._last_webhook_detection_types: list[str] = []
        self._last_webhook_matched_camera_count = 0
        self._last_webhook_changed_sensor_count = 0
        self._pending_webhook_events: list[tuple[dict[str, Any], datetime]] = []
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
            self._remove_stale_sensor_registry_entries()
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
        self.last_webhook_at = datetime.now(UTC)
        self._webhook_count += 1
        self._last_webhook_detection_types = list(normalized.get("detection_types") or [])
        if not self._sensor_specs:
            self._pending_webhook_events.append((dict(normalized), timestamp))
            self._pending_webhook_events = self._pending_webhook_events[-50:]
            self._last_webhook_matched_camera_count = 0
            self._last_webhook_changed_sensor_count = 0
            self._notify_listeners()
            return []

        changed_sensor_count, matched_cameras = self._apply_normalized_event(normalized, timestamp)
        self._last_webhook_matched_camera_count = len(matched_cameras)
        self._last_webhook_changed_sensor_count = changed_sensor_count
        if normalized.get("device_ids") and not matched_cameras:
            self._unmatched_webhook_count += 1
            self._last_unmatched_webhook_at = self.last_webhook_at
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

    def has_sensor_spec(self, sensor_key: str) -> bool:
        return sensor_key in self._sensor_specs

    def get_sensor_state(self, sensor_key: str) -> datetime | None:
        return self._timestamps.get(sensor_key)

    def get_sensor_attributes(self, sensor_key: str) -> dict[str, Any]:
        spec = self._sensor_specs.get(sensor_key)
        if spec is None:
            return {}
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
        active_sensor_keys = set(self._sensor_specs)
        known_sensor_count = sum(1 for key in self._timestamps if key in active_sensor_keys)
        webhook_url_source = self._webhook_url_source
        if webhook_url_source is None and self.entry.data.get(CONF_WEBHOOK_BASE_URL):
            webhook_url_source = "override"
        return {
            "verify_ssl": self.entry.data[CONF_VERIFY_SSL],
            "event_backfill_limit": self._event_backfill_limit(),
            "last_backfill_event_count": self._last_backfill_event_count,
            "last_backfill_changed_event_count": self._last_backfill_applied_count,
            "last_backfill_applied_count": self._last_backfill_applied_count,
            "last_backfill_changed_sensor_count": self._last_backfill_changed_sensor_count,
            "last_backfill_at": _isoformat(self._last_backfill_at),
            "last_backfill_error": self._last_backfill_error,
            "webhook_configured": self.webhook_url is not None,
            "webhook_url_source": webhook_url_source,
            "webhook_base_url_override_configured": bool(
                self.entry.data.get(CONF_WEBHOOK_BASE_URL)
            ),
            "camera_count": len(self.catalog.get("cameras") or []),
            "managed_sources": self.managed_sources,
            "managed_automation_count": self.managed_automation_count,
            "automation_sync_error_count": len(self._automation_sync_errors),
            "automation_sync_errors": dict(sorted(self._automation_sync_errors.items())),
            "sensor_count": len(active_sensor_keys),
            "known_sensor_count": known_sensor_count,
            "unknown_sensor_count": len(active_sensor_keys) - known_sensor_count,
            "known_sensor_counts_by_source": self._sensor_counts_by_source(known=True),
            "unknown_sensor_counts_by_source": self._sensor_counts_by_source(known=False),
            "last_sync_at": _isoformat(self.last_sync_at),
            "last_sync_error": self.last_sync_error,
            "last_webhook_at": _isoformat(self.last_webhook_at),
            "webhook_count": self._webhook_count,
            "last_webhook_detection_types": list(self._last_webhook_detection_types),
            "last_webhook_matched_camera_count": self._last_webhook_matched_camera_count,
            "last_webhook_changed_sensor_count": self._last_webhook_changed_sensor_count,
            "unmatched_webhook_count": self._unmatched_webhook_count,
            "last_unmatched_webhook_at": _isoformat(self._last_unmatched_webhook_at),
            "pending_webhook_count": len(self._pending_webhook_events),
        }

    def restore_sensor_state(
        self,
        sensor_key: str,
        timestamp: datetime,
        attributes: dict[str, Any],
    ) -> bool:
        if sensor_key not in self._sensor_specs:
            return False

        existing = self._timestamps.get(sensor_key)
        if existing is not None and existing >= timestamp:
            return False

        self._timestamps[sensor_key] = timestamp
        self._event_summaries[sensor_key] = _restored_event_summary(attributes, timestamp)
        self._notify_listeners()
        return True

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
            self._webhook_url_source = "override"
            return f"{override.rstrip('/')}" + self.webhook_path

        try:
            from homeassistant.helpers import network

            base_url = network.get_url(self.hass)
        except Exception:
            base_url = None

        if base_url:
            self._webhook_url_source = "home_assistant_instance_url"
            return f"{base_url.rstrip('/')}" + self.webhook_path

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
        self._webhook_url_source = "home_assistant_generated"
        return generated

    async def _async_sync_managed_automations(self, automations: list[dict[str, Any]]) -> None:
        desired_by_source = self._desired_automations()
        existing_by_source = group_managed_automations(automations)
        managed: dict[str, dict[str, Any]] = {}
        automation_sync_errors: dict[str, str] = {}

        for source, desired in desired_by_source.items():
            existing_candidates = existing_by_source.pop(source, [])
            existing = existing_candidates[0] if existing_candidates else None
            duplicates = existing_candidates[1:]
            if existing and not automation_needs_replace(existing, desired):
                try:
                    await self._async_delete_duplicate_automations(source, duplicates)
                except ProtectApiError as err:
                    automation_sync_errors[source] = (
                        f"Could not remove duplicate automation(s): {err}"
                    )
                    _LOGGER.warning(
                        "Could not remove duplicate managed Protect automation for %s: %s",
                        source,
                        err,
                    )
                managed[source] = dict(existing)
                continue

            if existing_candidates:
                _LOGGER.info("Replacing managed Protect automation for %s", source)
            else:
                _LOGGER.info("Creating managed Protect automation for %s", source)

            try:
                created = await self._api.async_create_automation(desired)
            except ProtectApiError as err:
                automation_sync_errors[source] = str(err)
                _LOGGER.warning(
                    "Could not create managed Protect automation for %s: %s",
                    source,
                    err,
                )
                if existing:
                    managed[source] = dict(existing)
                continue

            if existing_candidates:
                try:
                    await self._async_delete_automations(source, existing_candidates)
                except ProtectApiError as err:
                    automation_sync_errors[source] = (
                        f"Created replacement but could not remove old automation(s): {err}"
                    )
                    _LOGGER.warning(
                        "Created replacement for %s but could not remove old automation(s): %s",
                        source,
                        err,
                    )
                else:
                    _LOGGER.info("Replaced managed Protect automation for %s", source)

            managed[source] = created or desired

        for source, stale_items in existing_by_source.items():
            try:
                deleted_stale = await self._async_delete_automations(source, stale_items)
            except ProtectApiError as err:
                automation_sync_errors[source] = (
                    f"Could not remove stale automation(s): {err}"
                )
                _LOGGER.warning(
                    "Could not remove stale managed Protect automation for %s: %s",
                    source,
                    err,
                )
                continue
            if deleted_stale:
                _LOGGER.info("Removed stale managed Protect automation for %s", source)

        self._managed_automations = managed
        self._automation_sync_errors = automation_sync_errors

    async def _async_delete_duplicate_automations(
        self,
        source: str,
        duplicates: list[dict[str, Any]],
    ) -> None:
        if await self._async_delete_automations(source, duplicates):
            _LOGGER.info("Removed duplicate managed Protect automation for %s", source)

    async def _async_delete_automations(
        self,
        _source: str,
        automations: list[dict[str, Any]],
    ) -> bool:
        deleted = False
        for automation in automations:
            automation_id = automation.get("id")
            if automation_id:
                await self._api.async_delete_automation(automation_id)
                deleted = True
        return deleted

    def _desired_automations(self) -> dict[str, dict[str, Any]]:
        webhook_url = self.webhook_url
        if not webhook_url:
            raise ProtectApiError(
                "Could not determine a full Home Assistant webhook URL. Set webhook_base_url."
            )
        desired: dict[str, dict[str, Any]] = {}
        for source in self.managed_sources:
            device_macs = [
                camera["device_mac"]
                for camera in self.catalog.get("cameras") or []
                if camera.get("device_mac") and source in (camera.get("supported_sources") or [])
            ]
            if not device_macs:
                continue
            try:
                desired[source] = build_managed_automation_payload(
                    source,
                    device_macs,
                    webhook_url,
                )
            except ValueError as err:
                raise ProtectApiError(f"Invalid managed automation payload: {err}") from err
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

        active_keys = set(sensor_specs)
        for stale_key in list(self._timestamps):
            if stale_key not in active_keys:
                self._timestamps.pop(stale_key, None)
                self._event_summaries.pop(stale_key, None)

        self._sensor_specs = sensor_specs

    @callback
    def _remove_stale_sensor_registry_entries(self) -> None:
        registry = er.async_get(self.hass)
        active_unique_ids = {
            f"{self.entry.entry_id}_status",
            *(spec.unique_id for spec in self._sensor_specs.values()),
        }

        for entity_entry in er.async_entries_for_config_entry(
            registry,
            self.entry.entry_id,
        ):
            if entity_entry.domain != "sensor" or entity_entry.platform != DOMAIN:
                continue
            if entity_entry.unique_id in active_unique_ids:
                continue
            registry.async_remove(entity_entry.entity_id)

    def _sensor_counts_by_source(self, *, known: bool) -> dict[str, int]:
        counts: dict[str, int] = {}
        for key, spec in self._sensor_specs.items():
            is_known = key in self._timestamps
            if is_known != known:
                continue
            counts[spec.source] = counts.get(spec.source, 0) + 1
        return dict(sorted(counts.items()))

    async def _async_backfill_recent_events(self) -> None:
        limit = self._event_backfill_limit()
        self._last_backfill_at = datetime.now(UTC)
        self._last_backfill_event_count = 0
        self._last_backfill_applied_count = 0
        self._last_backfill_changed_sensor_count = 0
        self._last_backfill_error = None
        if limit <= 0:
            _LOGGER.debug("Skipping Protect event backfill because limit is %s", limit)
            return

        remaining = limit
        offset = 0
        seen_event_ids: set[str] = set()
        while remaining > 0:
            page_limit = min(PROTECT_EVENTS_REQUEST_LIMIT, remaining)
            try:
                events = await self._api.async_get_events(
                    limit=page_limit,
                    offset=offset,
                    types=list(BACKFILL_EVENT_TYPES),
                    sorting="desc",
                )
            except ProtectApiError as err:
                self._last_backfill_error = str(err)
                _LOGGER.warning("Could not backfill Protect events: %s", err)
                return

            if not events:
                return

            for event in events:
                event_id = _event_id(event)
                if event_id and event_id in seen_event_ids:
                    continue
                if event_id:
                    seen_event_ids.add(event_id)

                self._last_backfill_event_count += 1
                normalized = normalize_event_payload(event)
                if not normalized.get("detection_types"):
                    continue
                timestamp = _timestamp_from_normalized(normalized)
                changed_sensor_count, _matched_cameras = self._apply_normalized_event(
                    normalized,
                    timestamp,
                )
                if changed_sensor_count:
                    self._last_backfill_applied_count += 1
                    self._last_backfill_changed_sensor_count += changed_sensor_count

            if len(events) < page_limit:
                return

            offset += len(events)
            remaining -= len(events)

    def _event_backfill_limit(self) -> int:
        value = self.entry.options.get(
            CONF_EVENT_BACKFILL_LIMIT,
            DEFAULT_EVENT_BACKFILL_LIMIT,
        )
        try:
            limit = int(value)
        except (TypeError, ValueError):
            return DEFAULT_EVENT_BACKFILL_LIMIT
        return max(0, min(limit, MAX_EVENT_BACKFILL_LIMIT))

    def _seed_timestamps_from_catalog(self) -> None:
        for camera in self.catalog.get("cameras") or []:
            for source, key in (("motion", "last_motion_ms"), ("ring", "last_ring_ms")):
                timestamp_ms = camera.get(key)
                if timestamp_ms is None:
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

        self._apply_pending_webhook_events()

    def _apply_pending_webhook_events(self) -> None:
        if not self._pending_webhook_events:
            return

        pending = self._pending_webhook_events
        self._pending_webhook_events = []
        for normalized, timestamp in pending:
            changed_sensor_count, matched_cameras = self._apply_normalized_event(
                normalized,
                timestamp,
            )
            self._last_webhook_detection_types = list(
                normalized.get("detection_types") or []
            )
            self._last_webhook_matched_camera_count = len(matched_cameras)
            self._last_webhook_changed_sensor_count = changed_sensor_count
            if normalized.get("device_ids") and not matched_cameras:
                self._unmatched_webhook_count += 1
                self._last_unmatched_webhook_at = datetime.now(UTC)

        self._notify_listeners()

    def _apply_normalized_event(
        self,
        normalized: dict[str, Any],
        timestamp: datetime,
    ) -> tuple[int, list[dict[str, Any]]]:
        matched_cameras = resolve_cameras(self.catalog, normalized.get("device_ids") or [])
        changed_sensor_count = 0

        for source in normalized.get("detection_types") or []:
            global_key = f"global:{source}"
            if global_key in self._sensor_specs:
                if self._update_sensor_state(global_key, timestamp, normalized):
                    changed_sensor_count += 1

            for camera in matched_cameras:
                sensor_key = f"{camera['camera_key']}:{source}"
                if sensor_key not in self._sensor_specs:
                    continue
                if self._update_sensor_state(sensor_key, timestamp, normalized):
                    changed_sensor_count += 1

        return changed_sensor_count, matched_cameras

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
    if timestamp_ms is not None and timestamp_ms != "":
        try:
            return datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=UTC)
        except (TypeError, ValueError, OSError, OverflowError):
            _LOGGER.debug("Ignoring invalid Protect event timestamp: %r", timestamp_ms)
    return datetime.now(UTC)


def _event_summary(normalized: dict[str, Any]) -> dict[str, Any]:
    return {
        "last_alarm_name": normalized.get("alarm_name"),
        "last_detection_types": list(normalized.get("detection_types") or []),
        "last_device_ids": list(normalized.get("device_ids") or []),
        "last_timestamp": normalized.get("timestamp_iso"),
    }


def _restored_event_summary(attributes: dict[str, Any], timestamp: datetime) -> dict[str, Any]:
    summary = {
        "last_alarm_name": attributes.get("last_alarm_name"),
        "last_detection_types": list(attributes.get("last_detection_types") or []),
        "last_device_ids": list(attributes.get("last_device_ids") or []),
        "last_timestamp": attributes.get("last_timestamp") or timestamp.isoformat(),
    }
    return {key: value for key, value in summary.items() if value not in (None, [], "")}


def _event_id(event: dict[str, Any]) -> str | None:
    event_id = event.get("id") or event.get("_id")
    if event_id is None:
        return None
    return str(event_id)


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
