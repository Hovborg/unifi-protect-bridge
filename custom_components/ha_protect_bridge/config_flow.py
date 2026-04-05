from __future__ import annotations

import secrets
from typing import Any

import voluptuous as vol
from homeassistant import config_entries

from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    CONF_WEBHOOK_BASE_URL,
    CONF_WEBHOOK_ID,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)
from .protect_api import ProtectApiClient, ProtectApiError, ProtectAuthError


class HaProtectBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        errors: dict[str, str] = {}

        if user_input is not None:
            cleaned = _clean_user_input(user_input)
            try:
                info = await _async_validate_input(cleaned)
            except ProtectAuthError:
                errors["base"] = "invalid_auth"
            except ProtectApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                unique_id = info.get("nvr_id") or cleaned[CONF_HOST]
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                cleaned[CONF_WEBHOOK_ID] = secrets.token_hex(32)
                return self.async_create_entry(
                    title=info.get("title") or cleaned[CONF_HOST],
                    data=cleaned,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(user_input),
            errors=errors,
        )


def _build_schema(user_input: dict[str, Any] | None) -> vol.Schema:
    user_input = user_input or {}
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=user_input.get(CONF_HOST, "192.168.1.1")): str,
            vol.Required(CONF_USERNAME, default=user_input.get(CONF_USERNAME, "")): str,
            vol.Required(CONF_PASSWORD, default=user_input.get(CONF_PASSWORD, "")): str,
            vol.Optional(
                CONF_VERIFY_SSL,
                default=user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
            ): bool,
            vol.Optional(
                CONF_WEBHOOK_BASE_URL,
                default=user_input.get(CONF_WEBHOOK_BASE_URL, ""),
            ): str,
        }
    )


def _clean_user_input(user_input: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(user_input)
    cleaned[CONF_HOST] = str(cleaned[CONF_HOST]).strip()
    cleaned[CONF_USERNAME] = str(cleaned[CONF_USERNAME]).strip()
    cleaned[CONF_PASSWORD] = str(cleaned[CONF_PASSWORD])
    webhook_base_url = str(cleaned.get(CONF_WEBHOOK_BASE_URL, "")).strip()
    if webhook_base_url:
        cleaned[CONF_WEBHOOK_BASE_URL] = webhook_base_url.rstrip("/")
    else:
        cleaned.pop(CONF_WEBHOOK_BASE_URL, None)
    cleaned[CONF_VERIFY_SSL] = bool(cleaned.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL))
    return cleaned


async def _async_validate_input(user_input: dict[str, Any]) -> dict[str, str | None]:
    client = ProtectApiClient(
        user_input[CONF_HOST],
        user_input[CONF_USERNAME],
        user_input[CONF_PASSWORD],
        user_input[CONF_VERIFY_SSL],
    )
    try:
        await client.async_setup()
        bootstrap = await client.async_get_bootstrap()
    finally:
        await client.async_close()

    nvr = bootstrap.get("nvr") or {}
    host = user_input[CONF_HOST]
    return {
        "nvr_id": nvr.get("id"),
        "title": nvr.get("name") or f"UniFi Protect @ {host}",
    }
