from __future__ import annotations

import sys
from types import ModuleType


def _install_homeassistant_stubs() -> None:
    if "homeassistant" in sys.modules:
        return

    homeassistant = ModuleType("homeassistant")
    components = ModuleType("homeassistant.components")
    diagnostics_module = ModuleType("homeassistant.components.diagnostics")
    persistent_notification = ModuleType("homeassistant.components.persistent_notification")
    webhook = ModuleType("homeassistant.components.webhook")
    sensor_module = ModuleType("homeassistant.components.sensor")
    config_entries = ModuleType("homeassistant.config_entries")
    core = ModuleType("homeassistant.core")
    exceptions = ModuleType("homeassistant.exceptions")
    helpers = ModuleType("homeassistant.helpers")
    config_validation = ModuleType("homeassistant.helpers.config_validation")
    device_registry = ModuleType("homeassistant.helpers.device_registry")
    entity = ModuleType("homeassistant.helpers.entity")

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs) -> None:
            super().__init_subclass__()

        def __init__(self) -> None:
            self.context: dict[str, str] = {}
            self.hass = None
            self._reconfigure_entry = None
            self._reauth_entry = None
            self._unique_id = None

        @property
        def source(self) -> str | None:
            return self.context.get("source")

        async def async_set_unique_id(self, unique_id=None, *, raise_on_progress=True):
            del raise_on_progress
            self._unique_id = unique_id
            return None

        def _abort_if_unique_id_configured(self) -> None:
            return None

        def _abort_if_unique_id_mismatch(self, reason="wrong_account") -> None:
            if self.source == "reauth":
                entry = self._reauth_entry
            elif self.source == "reconfigure":
                entry = self._reconfigure_entry
            else:
                entry = None
            if entry is None:
                return
            if getattr(entry, "unique_id", None) not in (None, self._unique_id):
                raise RuntimeError(reason)

        def _get_reauth_entry(self):
            return self._reauth_entry

        def _get_reconfigure_entry(self):
            return self._reconfigure_entry

        def async_show_form(
            self,
            *,
            step_id=None,
            data_schema=None,
            errors=None,
            description_placeholders=None,
            last_step=None,
            preview=None,
        ):
            del last_step, preview
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors or {},
                "description_placeholders": description_placeholders,
            }

        def async_create_entry(self, *, title, data):
            return {"type": "create_entry", "title": title, "data": data}

        def async_update_reload_and_abort(
            self,
            entry,
            *,
            unique_id=None,
            title=None,
            data=None,
            data_updates=None,
            options=None,
            reason=None,
            reload_even_if_entry_is_unchanged=True,
        ):
            del options, reload_even_if_entry_is_unchanged
            if reason is None:
                if self.source == "reauth":
                    reason = "reauth_successful"
                elif self.source == "reconfigure":
                    reason = "reconfigure_successful"
                else:
                    reason = "updated"
            return {
                "type": "abort",
                "reason": reason,
                "entry": entry,
                "unique_id": unique_id,
                "title": title,
                "data": data,
                "data_updates": data_updates,
            }

    class SensorEntity:
        def async_on_remove(self, _remove_callback) -> None:
            return None

        @property
        def unique_id(self) -> str | None:
            return getattr(self, "_attr_unique_id", None)

    class SensorDeviceClass:
        TIMESTAMP = "timestamp"

    class EntityCategory:
        DIAGNOSTIC = "diagnostic"

    class DeviceInfo(dict):
        pass

    class OptionsFlow:
        def __init__(self) -> None:
            self.config_entry = None

        def add_suggested_values_to_schema(self, schema, suggested_values):
            del suggested_values
            return schema

        def async_show_form(
            self,
            *,
            step_id=None,
            data_schema=None,
            errors=None,
            description_placeholders=None,
            last_step=None,
            preview=None,
        ):
            del last_step, preview
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors or {},
                "description_placeholders": description_placeholders,
            }

        def async_create_entry(self, *, title="", data=None):
            return {"type": "create_entry", "title": title, "data": data or {}}

    class OptionsFlowWithReload(OptionsFlow):
        automatic_reload = True

    def callback(func):
        return func

    def async_redact_data(data, to_redact):
        if isinstance(data, dict):
            return {
                key: ("REDACTED" if key in to_redact else async_redact_data(value, to_redact))
                for key, value in data.items()
            }
        if isinstance(data, list):
            return [async_redact_data(value, to_redact) for value in data]
        return data

    webhook.async_generate_path = lambda webhook_id: f"/api/webhook/{webhook_id}"
    webhook.async_generate_url = lambda _hass, webhook_id: f"http://ha.local/api/webhook/{webhook_id}"
    webhook.async_register = lambda *args, **kwargs: None
    webhook.async_unregister = lambda *args, **kwargs: None
    persistent_notification.async_create = lambda *args, **kwargs: None
    diagnostics_module.async_redact_data = async_redact_data
    config_entries.ConfigFlow = ConfigFlow
    config_entries.OptionsFlow = OptionsFlow
    config_entries.OptionsFlowWithReload = OptionsFlowWithReload
    config_entries.SOURCE_REAUTH = "reauth"
    config_entries.SOURCE_RECONFIGURE = "reconfigure"
    config_entries.SOURCE_USER = "user"
    sensor_module.SensorDeviceClass = SensorDeviceClass
    sensor_module.SensorEntity = SensorEntity
    core.CALLBACK_TYPE = object
    core.HomeAssistant = object
    core.callback = callback

    class ConfigEntryAuthFailed(Exception):
        pass

    class ConfigEntryNotReady(Exception):
        pass

    exceptions.ConfigEntryAuthFailed = ConfigEntryAuthFailed
    exceptions.ConfigEntryNotReady = ConfigEntryNotReady
    config_validation.config_entry_only_config_schema = lambda domain: {"domain": domain}
    device_registry.DeviceInfo = DeviceInfo
    entity.EntityCategory = EntityCategory

    components.webhook = webhook
    components.persistent_notification = persistent_notification
    components.diagnostics = diagnostics_module
    components.sensor = sensor_module
    helpers.config_validation = config_validation
    helpers.device_registry = device_registry
    helpers.entity = entity
    homeassistant.components = components
    homeassistant.config_entries = config_entries
    homeassistant.core = core
    homeassistant.exceptions = exceptions
    homeassistant.helpers = helpers

    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.components"] = components
    sys.modules["homeassistant.components.diagnostics"] = diagnostics_module
    sys.modules["homeassistant.components.persistent_notification"] = persistent_notification
    sys.modules["homeassistant.components.webhook"] = webhook
    sys.modules["homeassistant.components.sensor"] = sensor_module
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.exceptions"] = exceptions
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.config_validation"] = config_validation
    sys.modules["homeassistant.helpers.device_registry"] = device_registry
    sys.modules["homeassistant.helpers.entity"] = entity


_install_homeassistant_stubs()
