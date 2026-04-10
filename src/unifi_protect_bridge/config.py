from __future__ import annotations

from dataclasses import dataclass
from os import getenv

from dotenv import load_dotenv

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _bool(value: str | None, *, default: bool) -> bool:
    cleaned = _clean(value)
    if cleaned is None:
        return default
    lowered = cleaned.casefold()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    return default


def _int(value: str | None, *, default: int) -> int:
    cleaned = _clean(value)
    if cleaned is None:
        return default
    try:
        parsed = int(cleaned)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


@dataclass(slots=True, frozen=True)
class Settings:
    ha_base_url: str | None
    ha_token: str | None
    unifi_protect_base_url: str | None
    unifi_protect_username: str | None
    unifi_protect_password: str | None
    verify_ssl: bool
    request_timeout_seconds: int

    @classmethod
    def load(cls) -> Settings:
        load_dotenv()
        return cls(
            ha_base_url=_clean(getenv("HA_BASE_URL")),
            ha_token=_clean(getenv("HA_TOKEN")),
            unifi_protect_base_url=_clean(getenv("UNIFI_PROTECT_BASE_URL")),
            unifi_protect_username=_clean(getenv("UNIFI_PROTECT_USERNAME")),
            unifi_protect_password=_clean(getenv("UNIFI_PROTECT_PASSWORD")),
            verify_ssl=_bool(getenv("VERIFY_SSL"), default=True),
            request_timeout_seconds=_int(getenv("REQUEST_TIMEOUT_SECONDS"), default=20),
        )
