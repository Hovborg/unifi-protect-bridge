from __future__ import annotations

from types import SimpleNamespace

from custom_components.ha_protect_bridge.entry_runtime import (
    get_entry_runtime,
    iter_entry_runtimes,
)
from custom_components.ha_protect_bridge.webhook import _runtime_for_webhook


def test_get_entry_runtime_reads_runtime_data() -> None:
    runtime = object()
    entry = SimpleNamespace(runtime_data=runtime)

    assert get_entry_runtime(entry) is runtime


def test_iter_entry_runtimes_skips_entries_without_runtime() -> None:
    runtime_a = object()
    runtime_b = object()
    entries = [
        SimpleNamespace(runtime_data=runtime_a),
        SimpleNamespace(runtime_data=None),
        SimpleNamespace(runtime_data=runtime_b),
    ]
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_entries=lambda domain: entries if domain else [])
    )

    assert iter_entry_runtimes(hass) == [runtime_a, runtime_b]


def test_runtime_for_webhook_reads_runtime_data_from_entries() -> None:
    runtime = SimpleNamespace(
        entry=SimpleNamespace(data={"webhook_id": "abc123"}),
    )
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_entries=lambda domain: [SimpleNamespace(runtime_data=runtime)] if domain else []
        )
    )

    assert _runtime_for_webhook(hass, "abc123") is runtime
    assert _runtime_for_webhook(hass, "missing") is None
