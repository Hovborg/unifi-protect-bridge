from __future__ import annotations

import logging
import secrets
from typing import Any

import voluptuous as vol

try:
    from homeassistant.helpers import config_validation as cv
except ModuleNotFoundError:  # pragma: no cover - local unit tests do not install HA
    cv = None

from .const import (
    CONF_VERIFY_SSL,
    CONF_WEBHOOK_ID,
    CONFIG_ENTRY_VERSION,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    NAME,
    NOTIFICATION_ID,
    PLATFORMS,
    SERVICE_RESYNC,
    SERVICE_SHOW_SETUP_INFO,
    SUPPORTED_METHODS,
)
from .entry_runtime import get_entry_runtime
from .setup_info import build_setup_message

_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN) if cv else None
SERVICE_SCHEMA = vol.Schema({vol.Optional("entry_id"): str})


async def async_setup(hass: Any, config: dict[str, Any]) -> bool:
    if not hass.services.has_service(DOMAIN, SERVICE_SHOW_SETUP_INFO):

        async def _async_handle_show_setup_info(call: Any) -> None:
            entry = _service_entry(hass, call.data.get("entry_id"))
            if entry is None:
                _LOGGER.warning("No %s config entry exists yet", DOMAIN)
                return
            runtime = get_entry_runtime(entry)
            if runtime is None:
                return
            await async_show_setup_info(hass, runtime)

        hass.services.async_register(
            DOMAIN,
            SERVICE_SHOW_SETUP_INFO,
            _async_handle_show_setup_info,
            schema=SERVICE_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_RESYNC):

        async def _async_handle_resync(call: Any) -> None:
            entry = _service_entry(hass, call.data.get("entry_id"))
            if entry is None:
                _LOGGER.warning("No %s config entry exists yet", DOMAIN)
                return
            runtime = get_entry_runtime(entry)
            if runtime is None:
                return
            await runtime.async_resync()
            await async_show_setup_info(hass, runtime)

        hass.services.async_register(
            DOMAIN,
            SERVICE_RESYNC,
            _async_handle_resync,
            schema=SERVICE_SCHEMA,
        )

    return True


async def async_migrate_entry(hass: Any, entry: Any) -> bool:
    entry_version = getattr(entry, "version", 1)
    if entry_version > CONFIG_ENTRY_VERSION:
        return False

    data = dict(entry.data)
    changed = False

    if CONF_VERIFY_SSL not in data:
        data[CONF_VERIFY_SSL] = DEFAULT_VERIFY_SSL
        changed = True

    if not data.get(CONF_WEBHOOK_ID):
        data[CONF_WEBHOOK_ID] = secrets.token_hex(32)
        changed = True

    if changed or entry_version != CONFIG_ENTRY_VERSION:
        hass.config_entries.async_update_entry(
            entry,
            data=data,
            version=CONFIG_ENTRY_VERSION,
        )

    return True


async def async_setup_entry(hass: Any, entry: Any) -> bool:
    from homeassistant.components import webhook
    from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

    from .protect_api import ProtectApiError, ProtectAuthError
    from .runtime import HaProtectBridgeRuntime
    from .webhook import async_handle_protect_webhook

    runtime = None
    webhook_id = entry.data.get(CONF_WEBHOOK_ID)
    webhook_registered = False

    try:
        runtime = HaProtectBridgeRuntime(hass, entry)
        entry.runtime_data = runtime
        webhook_id = entry.data[CONF_WEBHOOK_ID]
        webhook.async_register(
            hass,
            DOMAIN,
            NAME,
            webhook_id,
            async_handle_protect_webhook,
            local_only=False,
            allowed_methods=SUPPORTED_METHODS,
        )
        webhook_registered = True
        await runtime.async_initialize()
    except ProtectAuthError as err:
        await _async_cleanup_failed_setup(
            hass,
            entry,
            runtime,
            webhook_id=webhook_id if webhook_registered else None,
        )
        raise ConfigEntryAuthFailed(str(err)) from err
    except ProtectApiError as err:
        await _async_cleanup_failed_setup(
            hass,
            entry,
            runtime,
            webhook_id=webhook_id if webhook_registered else None,
        )
        raise ConfigEntryNotReady(str(err)) from err
    except Exception as err:
        await _async_cleanup_failed_setup(
            hass,
            entry,
            runtime,
            webhook_id=webhook_id if webhook_registered else None,
        )
        raise ConfigEntryNotReady(str(err)) from err

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        await _async_cleanup_failed_setup(hass, entry, runtime, webhook_id=webhook_id)
        raise

    try:
        await async_show_setup_info(hass, runtime)
    except Exception:
        _LOGGER.warning("Failed to create UniFi Protect Bridge setup notification", exc_info=True)

    return True


async def async_unload_entry(hass: Any, entry: Any) -> bool:
    from homeassistant.components import webhook

    runtime = get_entry_runtime(entry)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
        if runtime is not None:
            await runtime.async_shutdown()
        entry.runtime_data = None
    return unload_ok


async def async_show_setup_info(hass: Any, runtime: Any) -> None:
    from homeassistant.components import persistent_notification

    persistent_notification.async_create(
        hass,
        build_setup_message(
            runtime.webhook_url,
            runtime.webhook_path,
            runtime.managed_sources,
            runtime.managed_automation_count,
        ),
        title=NAME,
        notification_id=NOTIFICATION_ID,
    )


async def _async_cleanup_failed_setup(
    hass: Any,
    entry: Any,
    runtime: Any | None,
    *,
    webhook_id: str | None,
) -> None:
    from homeassistant.components import webhook

    if webhook_id:
        webhook.async_unregister(hass, webhook_id)
    if runtime is not None:
        await runtime.async_shutdown()
    entry.runtime_data = None


def _service_entry(hass: Any, entry_id: str | None) -> Any | None:
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return None
    if entry_id is None:
        return entries[0]
    return next((entry for entry in entries if entry.entry_id == entry_id), None)
