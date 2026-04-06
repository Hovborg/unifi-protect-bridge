from __future__ import annotations

import asyncio
from types import SimpleNamespace

from custom_components.ha_protect_bridge.config_flow import (
    HaProtectBridgeConfigFlow,
    HaProtectBridgeOptionsFlowHandler,
)
from custom_components.ha_protect_bridge.const import (
    CONF_EVENT_BACKFILL_LIMIT,
    DEFAULT_EVENT_BACKFILL_LIMIT,
)


def test_config_flow_exposes_options_flow_handler() -> None:
    entry = SimpleNamespace(options={})
    handler = HaProtectBridgeConfigFlow.async_get_options_flow(entry)

    assert isinstance(handler, HaProtectBridgeOptionsFlowHandler)


def test_options_flow_updates_backfill_limit() -> None:
    handler = HaProtectBridgeOptionsFlowHandler()
    handler.config_entry = SimpleNamespace(options={CONF_EVENT_BACKFILL_LIMIT: 100})

    result = asyncio.run(
        handler.async_step_init(
            {
                CONF_EVENT_BACKFILL_LIMIT: 0,
            }
        )
    )

    assert result["type"] == "create_entry"
    assert result["data"] == {CONF_EVENT_BACKFILL_LIMIT: 0}


def test_options_flow_clamps_invalid_backfill_limit() -> None:
    handler = HaProtectBridgeOptionsFlowHandler()
    handler.config_entry = SimpleNamespace(options={})

    result = asyncio.run(
        handler.async_step_init(
            {
                CONF_EVENT_BACKFILL_LIMIT: 999,
            }
        )
    )

    assert result["data"] == {CONF_EVENT_BACKFILL_LIMIT: DEFAULT_EVENT_BACKFILL_LIMIT}
