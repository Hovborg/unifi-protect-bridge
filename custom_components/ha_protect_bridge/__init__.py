from __future__ import annotations

import logging
from typing import Any

from .const import (
    CONF_WEBHOOK_ID,
    DOMAIN,
    NAME,
    NOTIFICATION_ID,
    SERVICE_SHOW_SETUP_INFO,
)
from .setup_info import build_setup_message

_LOGGER = logging.getLogger(__name__)
_ALLOWED_METHODS = ("GET", "POST", "PUT")
_PLATFORMS = ["sensor"]


async def async_setup(hass: Any, config: dict[str, Any]) -> bool:
    if not hass.services.has_service(DOMAIN, SERVICE_SHOW_SETUP_INFO):

        async def _async_handle_show_setup_info_service(call: Any) -> None:
            entries = hass.config_entries.async_entries(DOMAIN)
            if not entries:
                _LOGGER.warning("No %s config entry exists yet", DOMAIN)
                return
            await async_show_setup_info(hass, entries[0])

        hass.services.async_register(
            DOMAIN,
            SERVICE_SHOW_SETUP_INFO,
            _async_handle_show_setup_info_service,
        )
    return True


async def async_setup_entry(hass: Any, entry: Any) -> bool:
    from homeassistant.components import webhook

    from .webhook import async_handle_protect_webhook

    webhook_id = entry.data[CONF_WEBHOOK_ID]
    webhook.async_register(
        hass,
        DOMAIN,
        NAME,
        webhook_id,
        async_handle_protect_webhook,
        local_only=False,
        allowed_methods=_ALLOWED_METHODS,
    )
    _LOGGER.info(
        "Registered HA Protect Bridge webhook at %s",
        webhook.async_generate_path(webhook_id),
    )
    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)
    await async_show_setup_info(hass, entry)
    return True


async def async_unload_entry(hass: Any, entry: Any) -> bool:
    from homeassistant.components import webhook

    unload_ok = await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
    if unload_ok:
        webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])

    return unload_ok


async def async_show_setup_info(hass: Any, entry: Any) -> None:
    from homeassistant.components import persistent_notification, webhook

    webhook_id = entry.data[CONF_WEBHOOK_ID]
    webhook_path = webhook.async_generate_path(webhook_id)
    webhook_url = _safe_generate_url(hass, webhook_id)
    persistent_notification.async_create(
        hass,
        build_setup_message(webhook_url, webhook_path),
        title=NAME,
        notification_id=NOTIFICATION_ID,
    )


def _safe_generate_url(hass: Any, webhook_id: str) -> str | None:
    from homeassistant.components import webhook

    try:
        return webhook.async_generate_url(hass, webhook_id)
    except Exception:
        _LOGGER.debug("Could not generate full webhook URL for %s", webhook_id, exc_info=True)
        return None
