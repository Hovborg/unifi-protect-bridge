from __future__ import annotations

DOMAIN = "ha_protect_bridge"
NAME = "HA Protect Bridge"

EVENT_WEBHOOK = f"{DOMAIN}_webhook"
EVENT_DETECTION = f"{DOMAIN}_detection"

CONF_WEBHOOK_ID = "webhook_id"
CONF_CLOUDHOOK = "cloudhook"

SERVICE_SHOW_SETUP_INFO = "show_setup_info"
NOTIFICATION_ID = f"{DOMAIN}_setup"
STATUS_SENSOR_NAME = "Bridge Status"

KNOWN_DETECTION_TYPES = (
    "person_of_interest",
    "known_face",
    "unknown_face",
    "license_plate",
    "line_crossing",
    "vehicle",
    "package",
    "animal",
    "person",
    "motion",
    "sound",
    "doorbell",
    "nfc",
    "face",
    "water_leak",
    "smoke",
    "co",
)
