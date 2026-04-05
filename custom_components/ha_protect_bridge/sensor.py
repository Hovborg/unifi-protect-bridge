from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import EntityCategory

from .const import (
    CONF_CLOUDHOOK,
    CONF_WEBHOOK_ID,
    DOMAIN,
    KNOWN_DETECTION_TYPES,
    STATUS_SENSOR_NAME,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: Any, entry: Any, async_add_entities: Any) -> None:
    async_add_entities([HaProtectBridgeStatusSensor(hass, entry)])


class HaProtectBridgeStatusSensor(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = STATUS_SENSOR_NAME
    _attr_native_value = "configured"
    _attr_icon = "mdi:webhook"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: Any, entry: Any) -> None:
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_status"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        from homeassistant.components import webhook

        webhook_id = self._entry.data[CONF_WEBHOOK_ID]
        webhook_path = webhook.async_generate_path(webhook_id)
        webhook_url = None
        try:
            webhook_url = webhook.async_generate_url(self.hass, webhook_id)
        except Exception:
            _LOGGER.debug(
                "Could not generate full webhook URL for sensor attributes",
                exc_info=True,
            )

        return {
            "domain": DOMAIN,
            "webhook_id": webhook_id,
            "webhook_path": webhook_path,
            "webhook_url": webhook_url,
            "cloudhook": self._entry.data.get(CONF_CLOUDHOOK, False),
            "recommended_method": "POST",
            "supported_methods": ["GET", "POST", "PUT"],
            "known_detection_types": list(KNOWN_DETECTION_TYPES),
        }
