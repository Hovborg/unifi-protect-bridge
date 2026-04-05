from __future__ import annotations

from dataclasses import dataclass
from os import getenv

from dotenv import load_dotenv


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


@dataclass(slots=True, frozen=True)
class Settings:
    ha_base_url: str | None
    ha_token: str | None
    unifi_site_manager_api_key: str | None
    unifi_network_base_url: str | None
    unifi_network_api_key: str | None
    unifi_protect_base_url: str | None
    unifi_protect_username: str | None
    unifi_protect_password: str | None
    unifi_protect_api_key: str | None

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()
        return cls(
            ha_base_url=_clean(getenv("HA_BASE_URL")),
            ha_token=_clean(getenv("HA_TOKEN")),
            unifi_site_manager_api_key=_clean(getenv("UNIFI_SITE_MANAGER_API_KEY")),
            unifi_network_base_url=_clean(getenv("UNIFI_NETWORK_BASE_URL")),
            unifi_network_api_key=_clean(getenv("UNIFI_NETWORK_API_KEY")),
            unifi_protect_base_url=_clean(getenv("UNIFI_PROTECT_BASE_URL")),
            unifi_protect_username=_clean(getenv("UNIFI_PROTECT_USERNAME")),
            unifi_protect_password=_clean(getenv("UNIFI_PROTECT_PASSWORD")),
            unifi_protect_api_key=_clean(getenv("UNIFI_PROTECT_API_KEY")),
        )
