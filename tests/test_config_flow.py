from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from homeassistant import config_entries

from custom_components.unifi_protect_bridge import config_flow
from custom_components.unifi_protect_bridge.config_flow import HaProtectBridgeConfigFlow
from custom_components.unifi_protect_bridge.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    CONF_WEBHOOK_BASE_URL,
    CONF_WEBHOOK_ID,
)


def test_user_flow_creates_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _async_validate_input(user_input: dict[str, Any]) -> dict[str, str]:
        assert user_input[CONF_HOST] == "protect.local"
        assert user_input[CONF_WEBHOOK_BASE_URL] == "https://ha.example"
        return {"nvr_id": "nvr-1", "title": "UDM SE"}

    monkeypatch.setattr(config_flow, "_async_validate_input", _async_validate_input)
    monkeypatch.setattr(config_flow.secrets, "token_hex", lambda _size: "webhook-token")

    flow = HaProtectBridgeConfigFlow()
    flow.context = {"source": config_entries.SOURCE_USER}

    result = asyncio.run(
        flow.async_step_user(
            {
                CONF_HOST: " protect.local ",
                CONF_USERNAME: " admin ",
                CONF_PASSWORD: "secret",
                CONF_VERIFY_SSL: True,
                CONF_WEBHOOK_BASE_URL: "https://ha.example/",
            }
        )
    )

    assert result["type"] == "create_entry"
    assert result["title"] == "UDM SE"
    assert result["data"] == {
        CONF_HOST: "protect.local",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "secret",
        CONF_VERIFY_SSL: True,
        CONF_WEBHOOK_BASE_URL: "https://ha.example",
        CONF_WEBHOOK_ID: "webhook-token",
    }


def test_reconfigure_flow_keeps_existing_password_and_clears_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _mock_entry()

    async def _async_validate_input(user_input: dict[str, Any]) -> dict[str, str]:
        assert user_input[CONF_PASSWORD] == "existing-secret"
        assert user_input[CONF_HOST] == "new-protect.local"
        assert CONF_WEBHOOK_BASE_URL not in user_input
        assert user_input[CONF_WEBHOOK_ID] == "existing-webhook"
        return {"nvr_id": "nvr-1", "title": "Updated NVR"}

    monkeypatch.setattr(config_flow, "_async_validate_input", _async_validate_input)

    flow = HaProtectBridgeConfigFlow()
    flow.context = {"source": config_entries.SOURCE_RECONFIGURE}
    flow._reconfigure_entry = entry

    result = asyncio.run(
        flow.async_step_reconfigure(
            {
                CONF_HOST: " new-protect.local ",
                CONF_USERNAME: " updated-user ",
                CONF_PASSWORD: "",
                CONF_VERIFY_SSL: True,
                CONF_WEBHOOK_BASE_URL: " ",
            }
        )
    )

    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert result["title"] == "Updated NVR"
    assert result["data"] == {
        CONF_HOST: "new-protect.local",
        CONF_USERNAME: "updated-user",
        CONF_PASSWORD: "existing-secret",
        CONF_VERIFY_SSL: True,
        CONF_WEBHOOK_ID: "existing-webhook",
    }


def test_reauth_flow_keeps_existing_password_when_left_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _mock_entry()

    async def _async_validate_input(user_input: dict[str, Any]) -> dict[str, str]:
        assert user_input[CONF_HOST] == "protect.local"
        assert user_input[CONF_USERNAME] == "updated-user"
        assert user_input[CONF_PASSWORD] == "existing-secret"
        return {"nvr_id": "nvr-1", "title": "UDM SE"}

    monkeypatch.setattr(config_flow, "_async_validate_input", _async_validate_input)

    flow = HaProtectBridgeConfigFlow()
    flow.context = {"source": config_entries.SOURCE_REAUTH}
    flow._reauth_entry = entry

    form = asyncio.run(flow.async_step_reauth(entry.data))
    assert form["type"] == "form"
    assert form["step_id"] == "reauth_confirm"
    assert form["description_placeholders"] == {"host": "protect.local"}

    result = asyncio.run(
        flow.async_step_reauth_confirm(
            {
                CONF_USERNAME: " updated-user ",
                CONF_PASSWORD: "",
            }
        )
    )

    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert result["data"] == {
        CONF_HOST: "protect.local",
        CONF_USERNAME: "updated-user",
        CONF_PASSWORD: "existing-secret",
        CONF_VERIFY_SSL: False,
        CONF_WEBHOOK_ID: "existing-webhook",
        CONF_WEBHOOK_BASE_URL: "https://ha.example",
    }


def test_reconfigure_flow_rejects_different_nvr(monkeypatch: pytest.MonkeyPatch) -> None:
    entry = _mock_entry()

    async def _async_validate_input(_user_input: dict[str, Any]) -> dict[str, str]:
        return {"nvr_id": "different-nvr", "title": "Other NVR"}

    monkeypatch.setattr(config_flow, "_async_validate_input", _async_validate_input)

    flow = HaProtectBridgeConfigFlow()
    flow.context = {"source": config_entries.SOURCE_RECONFIGURE}
    flow._reconfigure_entry = entry

    with pytest.raises(RuntimeError, match="wrong_account"):
        asyncio.run(
            flow.async_step_reconfigure(
                {
                    CONF_HOST: "protect.local",
                    CONF_USERNAME: "admin",
                    CONF_PASSWORD: "",
                    CONF_VERIFY_SSL: False,
                    CONF_WEBHOOK_BASE_URL: "https://ha.example",
                }
            )
        )


def test_webhook_base_url_validator_requires_absolute_http_url() -> None:
    assert config_flow._validate_webhook_base_url(" http://ha.local:8123/ ") == (
        "http://ha.local:8123"
    )
    assert config_flow._validate_webhook_base_url("") == ""

    with pytest.raises(config_flow.vol.Invalid):
        config_flow._validate_webhook_base_url("ha.local:8123")

    with pytest.raises(config_flow.vol.Invalid):
        config_flow._validate_webhook_base_url("http://ha.local:8123/api/webhook/token")

    with pytest.raises(config_flow.vol.Invalid):
        config_flow._validate_webhook_base_url("http://ha.local:8123?token=secret")


def _mock_entry() -> Any:
    return SimpleNamespace(
        entry_id="entry-1",
        unique_id="nvr-1",
        title="UDM SE",
        data={
            CONF_HOST: "protect.local",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "existing-secret",
            CONF_VERIFY_SSL: False,
            CONF_WEBHOOK_ID: "existing-webhook",
            CONF_WEBHOOK_BASE_URL: "https://ha.example",
        },
    )
