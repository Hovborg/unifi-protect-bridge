from __future__ import annotations

import secrets
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    CONF_EVENT_BACKFILL_LIMIT,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    CONF_WEBHOOK_BASE_URL,
    CONF_WEBHOOK_ID,
    CONFIG_ENTRY_VERSION,
    DEFAULT_EVENT_BACKFILL_LIMIT,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    MAX_EVENT_BACKFILL_LIMIT,
)
from .protect_api import ProtectApiClient, ProtectApiError, ProtectAuthError


class HaProtectBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = CONFIG_ENTRY_VERSION

    @staticmethod
    @callback
    def async_get_options_flow(_config_entry: Any) -> HaProtectBridgeOptionsFlowHandler:
        return HaProtectBridgeOptionsFlowHandler()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        return await self._async_step_configure_user(user_input)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> Any:
        entry = self._get_reconfigure_entry()
        return await self._async_step_configure_existing(
            step_id="reconfigure",
            entry=entry,
            user_input=user_input,
            schema=_build_full_schema(_form_defaults(entry.data, user_input)),
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> Any:
        del entry_data
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> Any:
        entry = self._get_reauth_entry()
        return await self._async_step_configure_existing(
            step_id="reauth_confirm",
            entry=entry,
            user_input=user_input,
            schema=_build_reauth_schema(_reauth_form_defaults(entry.data, user_input)),
            description_placeholders={"host": entry.data[CONF_HOST]},
        )

    async def _async_step_configure_user(self, user_input: dict[str, Any] | None) -> Any:
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
            data_schema=_build_full_schema(_form_defaults({}, user_input), require_password=True),
            errors=errors,
        )

    async def _async_step_configure_existing(
        self,
        *,
        step_id: str,
        entry: Any,
        user_input: dict[str, Any] | None,
        schema: vol.Schema,
        description_placeholders: dict[str, str] | None = None,
    ) -> Any:
        errors: dict[str, str] = {}

        if user_input is not None:
            cleaned = _clean_user_input(user_input, existing_data=entry.data)
            updated_data = _build_updated_entry_data(
                entry.data,
                cleaned,
                clear_webhook_base_url=_clear_webhook_base_url(user_input),
            )
            try:
                info = await _async_validate_input(updated_data)
            except ProtectAuthError:
                errors["base"] = "invalid_auth"
            except ProtectApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                unique_id = info.get("nvr_id") or updated_data[CONF_HOST]
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=unique_id,
                    title=info.get("title") or updated_data[CONF_HOST],
                    data=updated_data,
                )

        return self.async_show_form(
            step_id=step_id,
            data_schema=schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )


def _build_full_schema(
    defaults: Mapping[str, Any] | None,
    *,
    require_password: bool = False,
) -> vol.Schema:
    defaults = defaults or {}
    password_field = vol.Required if require_password else vol.Optional
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
            password_field(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): str,
            vol.Optional(
                CONF_VERIFY_SSL,
                default=defaults.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
            ): bool,
            vol.Optional(
                CONF_WEBHOOK_BASE_URL,
                default=defaults.get(CONF_WEBHOOK_BASE_URL, ""),
            ): _validate_webhook_base_url,
        }
    )


def _build_reauth_schema(defaults: Mapping[str, Any] | None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
            vol.Optional(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): str,
        }
    )


def _clean_user_input(
    user_input: dict[str, Any],
    *,
    existing_data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cleaned = dict(user_input)
    if CONF_HOST in cleaned:
        cleaned[CONF_HOST] = str(cleaned[CONF_HOST]).strip()
    if CONF_USERNAME in cleaned:
        cleaned[CONF_USERNAME] = str(cleaned[CONF_USERNAME]).strip()

    if CONF_PASSWORD in cleaned:
        password = str(cleaned[CONF_PASSWORD])
        if password or existing_data is None:
            cleaned[CONF_PASSWORD] = password
        else:
            cleaned[CONF_PASSWORD] = str(existing_data.get(CONF_PASSWORD, ""))
    elif existing_data is not None and CONF_PASSWORD in existing_data:
        cleaned[CONF_PASSWORD] = str(existing_data[CONF_PASSWORD])

    if CONF_WEBHOOK_BASE_URL in cleaned:
        webhook_base_url = str(cleaned.get(CONF_WEBHOOK_BASE_URL, "")).strip()
        if webhook_base_url:
            cleaned[CONF_WEBHOOK_BASE_URL] = webhook_base_url.rstrip("/")
        else:
            cleaned.pop(CONF_WEBHOOK_BASE_URL, None)

    if CONF_VERIFY_SSL in cleaned or existing_data is None:
        cleaned[CONF_VERIFY_SSL] = bool(
            cleaned.get(
                CONF_VERIFY_SSL,
                existing_data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
                if existing_data
                else DEFAULT_VERIFY_SSL,
            )
        )
    return cleaned


def _form_defaults(
    existing_data: Mapping[str, Any] | None,
    user_input: Mapping[str, Any] | None,
) -> dict[str, Any]:
    defaults = {
        CONF_HOST: "",
        CONF_USERNAME: "",
        CONF_PASSWORD: "",
        CONF_VERIFY_SSL: DEFAULT_VERIFY_SSL,
        CONF_WEBHOOK_BASE_URL: "",
    }
    if existing_data:
        defaults.update(existing_data)
    defaults[CONF_PASSWORD] = ""
    if existing_data and CONF_WEBHOOK_BASE_URL not in existing_data:
        defaults[CONF_WEBHOOK_BASE_URL] = ""
    if user_input:
        defaults.update(user_input)
    return defaults


def _reauth_form_defaults(
    existing_data: Mapping[str, Any],
    user_input: Mapping[str, Any] | None,
) -> dict[str, Any]:
    defaults = {
        CONF_USERNAME: str(existing_data.get(CONF_USERNAME, "")),
        CONF_PASSWORD: "",
    }
    if user_input:
        defaults.update(user_input)
    return defaults


def _build_updated_entry_data(
    existing_data: Mapping[str, Any],
    updates: Mapping[str, Any],
    *,
    clear_webhook_base_url: bool = False,
) -> dict[str, Any]:
    data = dict(existing_data)
    data.update(updates)
    if clear_webhook_base_url:
        data.pop(CONF_WEBHOOK_BASE_URL, None)
    return data


def _clear_webhook_base_url(user_input: Mapping[str, Any]) -> bool:
    return CONF_WEBHOOK_BASE_URL in user_input and not str(
        user_input[CONF_WEBHOOK_BASE_URL]
    ).strip()


class HaProtectBridgeOptionsFlowHandler(config_entries.OptionsFlowWithReload):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_EVENT_BACKFILL_LIMIT: _clean_backfill_limit(
                        user_input.get(CONF_EVENT_BACKFILL_LIMIT)
                    )
                },
            )

        defaults = {
            CONF_EVENT_BACKFILL_LIMIT: self.config_entry.options.get(
                CONF_EVENT_BACKFILL_LIMIT,
                DEFAULT_EVENT_BACKFILL_LIMIT,
            )
        }
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                _build_options_schema(),
                defaults,
            ),
        )


def _build_options_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                CONF_EVENT_BACKFILL_LIMIT,
                description={"suggested_value": DEFAULT_EVENT_BACKFILL_LIMIT},
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_EVENT_BACKFILL_LIMIT)),
        }
    )


def _clean_backfill_limit(value: Any) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return DEFAULT_EVENT_BACKFILL_LIMIT
    return max(0, min(limit, MAX_EVENT_BACKFILL_LIMIT))


def _validate_webhook_base_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise vol.Invalid("webhook_base_url")
    return text.rstrip("/")


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
