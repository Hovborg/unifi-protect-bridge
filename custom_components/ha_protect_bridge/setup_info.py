from __future__ import annotations

from collections.abc import Iterable

from .catalog import humanize_source
from .const import EVENT_DETECTION, EVENT_WEBHOOK, KNOWN_DETECTION_TYPES


def build_setup_message(
    webhook_url: str | None,
    webhook_path: str,
    detection_types: Iterable[str] = KNOWN_DETECTION_TYPES,
    automation_count: int | None = None,
) -> str:
    detection_types = list(detection_types)
    lines = [
        "HA Protect Bridge is ready.",
        "",
        f"Webhook URL: `{webhook_url or 'Not currently available'}`",
        f"Webhook path: `{webhook_path}`",
        "",
        "Automatic setup completed:",
        "1. The integration logged in to UniFi Protect.",
        "2. It discovered cameras and supported detection types.",
        "3. It registered Home Assistant webhook handling.",
        "4. It provisioned managed Protect webhook automations for supported sources.",
        "",
        (
            "Managed automation count: "
            f"`{automation_count if automation_count is not None else 'unknown'}`"
        ),
        "Managed detection sources:",
    ]
    lines.extend(f"- `{detection}` ({humanize_source(detection)})" for detection in detection_types)
    lines.extend(
        [
            "",
            "Home Assistant events fired:",
            f"- `{EVENT_WEBHOOK}`",
            f"- `{EVENT_DETECTION}`",
        ]
    )
    lines.extend(f"- `ha_protect_bridge_{detection}`" for detection in detection_types)
    lines.extend(
        [
            "",
            "Operational note:",
            (
                "Managed automations are created through UniFi Protect's private "
                "`/proxy/protect/api/automations` endpoint. This enables zero-manual "
                "setup, but Protect updates could require adapter changes later."
            ),
        ]
    )
    return "\n".join(lines)
