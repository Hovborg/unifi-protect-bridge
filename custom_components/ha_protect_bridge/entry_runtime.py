from __future__ import annotations

from typing import Any

from .const import DOMAIN


def get_entry_runtime(entry: Any) -> Any | None:
    return getattr(entry, "runtime_data", None)


def iter_entry_runtimes(hass: Any) -> list[Any]:
    runtimes: list[Any] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        runtime = get_entry_runtime(entry)
        if runtime is not None:
            runtimes.append(runtime)
    return runtimes
