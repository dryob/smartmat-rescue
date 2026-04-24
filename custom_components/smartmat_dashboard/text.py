"""Product-name text entity."""
from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_PRODUCT_NAME,
    CONF_SHORT_ID,
    DEFAULT_PRODUCT_NAME,
    DOMAIN,
    UID_PRODUCT,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the product-name text entity."""
    async_add_entities([SmartMatProductText(entry)])


class SmartMatProductText(TextEntity, RestoreEntity):
    """Free-text product name, user-editable from UI."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:package-variant"
    _attr_native_max = 50
    _attr_native_min = 0
    _attr_mode = "text"

    def __init__(self, entry: ConfigEntry) -> None:
        self._sid = entry.data[CONF_SHORT_ID]
        self._initial = entry.data.get(CONF_PRODUCT_NAME, DEFAULT_PRODUCT_NAME)
        self._attr_name = "Product"
        self._attr_unique_id = f"{DOMAIN}_{self._sid}_{UID_PRODUCT}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, self._sid)})
        self._attr_native_value = self._initial

    async def async_added_to_hass(self) -> None:
        """Restore last value."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in (None, "unknown", "unavailable"):
            self._attr_native_value = last.state

    async def async_set_value(self, value: str) -> None:
        """User typed a new product name."""
        self._attr_native_value = value
        self.async_write_ha_state()
