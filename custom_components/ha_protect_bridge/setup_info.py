from __future__ import annotations

from collections.abc import Iterable

from .const import EVENT_DETECTION, EVENT_WEBHOOK, KNOWN_DETECTION_TYPES


def build_setup_message(
    webhook_url: str | None,
    webhook_path: str,
    detection_types: Iterable[str] = KNOWN_DETECTION_TYPES,
) -> str:
    destination = webhook_url or webhook_path
    lines = [
        "HA Protect Bridge is ready.",
        "",
        f"Webhook URL: `{webhook_url or 'Not currently available'}`",
        f"Webhook path: `{webhook_path}`",
        "",
        "Recommended UniFi Protect Alarm Manager setup:",
        "1. Open Alarm Manager in UniFi Protect.",
        "2. Create or edit an alarm for the camera or group you want.",
        "3. Add a Webhook action.",
        "4. Use HTTP POST when possible.",
        f"5. Set the destination URL to `{destination}`.",
        (
            "6. Create alarms for person, animal, vehicle, package, motion, "
            "or other detections you care about."
        ),
        "",
        "This integration will fire Home Assistant events:",
        f"- `{EVENT_WEBHOOK}`",
        f"- `{EVENT_DETECTION}`",
    ]
    lines.extend(f"- `ha_protect_bridge_{detection}`" for detection in detection_types)
    lines.extend(
        [
            "",
            "Official note:",
            (
                "As of 5 April 2026, the Home Assistant side can generate the webhook "
                "endpoint automatically, but UniFi Protect Alarm Manager webhook "
                "creation still appears UI-driven in the official docs."
            ),
        ]
    )
    return "\n".join(lines)
