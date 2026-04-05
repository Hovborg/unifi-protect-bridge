from __future__ import annotations

import logging
from typing import Any

from .const import (
    CONF_WEBHOOK_ID,
    DOMAIN,
    NAME,
    NOTIFICATION_ID,
    PLATFORMS,
    SERVICE_RESYNC,
    SERVICE_SHOW_SETUP_INFO,
    SUPPORTED_METHODS,
)
from .setup_info import build_setup_message

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: Any, config: dict[str, Any]) -> bool:
    if not hass.services.has_service(DOMAIN, SERVICE_SHOW_SETUP_INFO):

        async def _async_handle_show_setup_info(call: Any) -> None:
            entry = _service_entry(hass, call.data.get("entry_id"))
            if entry is None:
                _LOGGER.warning("No %s config entry exists yet", DOMAIN)
                return
            runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if runtime is None:
                return
            await async_show_setup_info(hass, runtime)

        hass.services.async_register(DOMAIN, SERVICE_SHOW_SETUP_INFO, _async_handle_show_setup_info)

    if not hass.services.has_service(DOMAIN, SERVICE_RESYNC):

        async def _async_handle_resync(call: Any) -> None:
            entry = _service_entry(hass, call.data.get("entry_id"))
            if entry is None:
                _LOGGER.warning("No %s config entry exists yet", DOMAIN)
                return
            runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if runtime is None:
                return
            await runtime.async_resync()
            await async_show_setup_info(hass, runtime)

        hass.services.async_register(DOMAIN, SERVICE_RESYNC, _async_handle_resync)

    return True


async def async_setup_entry(hass: Any, entry: Any) -> bool:
    from homeassistant.components import webhook
    from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

    from .protect_api import ProtectApiError, ProtectAuthError
    from .runtime import HaProtectBridgeRuntime
    from .webhook import async_handle_protect_webhook

    runtime = HaProtectBridgeRuntime(hass, entry)
    webhook.async_register(
        hass,
        DOMAIN,
        NAME,
        entry.data[CONF_WEBHOOK_ID],
        async_handle_protect_webhook,
        local_only=False,
        allowed_methods=SUPPORTED_METHODS,
    )

    try:
        await runtime.async_initialize()
    except ProtectAuthError as err:
        webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
        await runtime.async_shutdown()
        raise ConfigEntryAuthFailed(str(err)) from err
    except ProtectApiError as err:
        webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
        await runtime.async_shutdown()
        raise ConfigEntryNotReady(str(err)) from err
    except Exception as err:
        webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
        await runtime.async_shutdown()
        raise ConfigEntryNotReady(str(err)) from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_show_setup_info(hass, runtime)
    return True


async def async_unload_entry(hass: Any, entry: Any) -> bool:
    from homeassistant.components import webhook

    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if runtime is not None:
            await runtime.async_shutdown()
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


def _service_entry(hass: Any, entry_id: str | None) -> Any | None:
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return None
    if entry_id is None:
        return entries[0]
    return next((entry for entry in entries if entry.entry_id == entry_id), None)
