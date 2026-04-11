from __future__ import annotations

DOMAIN = "unifi_protect_bridge"
NAME = "UniFi Protect Bridge"

PLATFORMS = ("sensor",)
CONFIG_ENTRY_VERSION = 2

EVENT_WEBHOOK = f"{DOMAIN}_webhook"
EVENT_DETECTION = f"{DOMAIN}_detection"

CONF_HOST = "host"
CONF_PASSWORD = "password"
CONF_USERNAME = "username"
CONF_VERIFY_SSL = "verify_ssl"
CONF_EVENT_BACKFILL_LIMIT = "event_backfill_limit"
CONF_WEBHOOK_BASE_URL = "webhook_base_url"
CONF_WEBHOOK_ID = "webhook_id"

DEFAULT_VERIFY_SSL = False
DEFAULT_TIMEOUT_SECONDS = 20
SUPPORTED_METHODS = ("POST", "PUT")
DEFAULT_EVENT_BACKFILL_LIMIT = 500
MAX_EVENT_BACKFILL_LIMIT = 1000
BACKFILL_EVENT_TYPES = (
    "motion",
    "ring",
    "smartDetectZone",
    "smartDetectLine",
    "smartAudioDetect",
)

SERVICE_SHOW_SETUP_INFO = "show_setup_info"
SERVICE_RESYNC = "resync"
NOTIFICATION_ID = f"{DOMAIN}_setup"
STATUS_SENSOR_NAME = "Bridge Status"
# Keep recognizing the old managed automation prefix after the public rename.
LEGACY_MANAGED_AUTOMATION_PREFIX = "HA Protect Bridge:"
MANAGED_AUTOMATION_PREFIX = "UniFi Protect Bridge:"
MANAGED_AUTOMATION_TIMEOUT_MS = 30000

KNOWN_DETECTION_TYPES = (
    "motion",
    "person",
    "vehicle",
    "animal",
    "package",
    "license_plate_of_interest",
    "ring",
    "face",
    "face_unknown",
    "face_known",
    "face_of_interest",
    "audio_alarm_baby_cry",
    "audio_alarm_bark",
    "audio_alarm_burglar",
    "audio_alarm_car_horn",
    "audio_alarm_co",
    "audio_alarm_glass_break",
    "audio_alarm_siren",
    "audio_alarm_smoke",
    "audio_alarm_speak",
)

TYPED_DETECTION_EVENTS = tuple(f"{DOMAIN}_{detection}" for detection in KNOWN_DETECTION_TYPES)
SELECTABLE_DETECTION_EVENTS = (EVENT_DETECTION, *TYPED_DETECTION_EVENTS)

AUDIO_DETECTION_TYPES = (
    "audio_alarm_baby_cry",
    "audio_alarm_bark",
    "audio_alarm_burglar",
    "audio_alarm_car_horn",
    "audio_alarm_co",
    "audio_alarm_glass_break",
    "audio_alarm_siren",
    "audio_alarm_smoke",
    "audio_alarm_speak",
)

SOURCE_LABELS = {
    "motion": "motion",
    "person": "person",
    "vehicle": "vehicle",
    "animal": "animal",
    "package": "package",
    "license_plate_of_interest": "license plate of interest",
    "ring": "doorbell ring",
    "face": "face",
    "face_unknown": "unknown face",
    "face_known": "known face",
    "face_of_interest": "face of interest",
    "audio_alarm_baby_cry": "baby cry alarm",
    "audio_alarm_bark": "bark alarm",
    "audio_alarm_burglar": "burglar alarm",
    "audio_alarm_car_horn": "car horn alarm",
    "audio_alarm_co": "carbon monoxide alarm",
    "audio_alarm_glass_break": "glass-break alarm",
    "audio_alarm_siren": "siren alarm",
    "audio_alarm_smoke": "smoke alarm",
    "audio_alarm_speak": "speech alarm",
}

SOURCE_ICONS = {
    "motion": "mdi:motion-sensor",
    "person": "mdi:account",
    "vehicle": "mdi:car",
    "animal": "mdi:paw",
    "package": "mdi:package-variant-closed",
    "license_plate_of_interest": "mdi:card-text-outline",
    "ring": "mdi:bell-ring",
    "face": "mdi:face-recognition",
    "face_unknown": "mdi:face-recognition",
    "face_known": "mdi:face-recognition",
    "face_of_interest": "mdi:face-man-profile",
    "audio_alarm_baby_cry": "mdi:baby-face-outline",
    "audio_alarm_bark": "mdi:dog-side",
    "audio_alarm_burglar": "mdi:shield-alert",
    "audio_alarm_car_horn": "mdi:bullhorn",
    "audio_alarm_co": "mdi:molecule-co",
    "audio_alarm_glass_break": "mdi:window-shutter-alert",
    "audio_alarm_siren": "mdi:alarm-light",
    "audio_alarm_smoke": "mdi:smoke-detector-variant-alert",
    "audio_alarm_speak": "mdi:account-voice",
}
