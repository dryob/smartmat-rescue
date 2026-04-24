"""Tare + Full calibration numbers."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_SHORT_ID,
    DEFAULT_FULL,
    DEFAULT_TARE,
    DOMAIN,
    UID_FULL,
    UID_TARE,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the two calibration numbers."""
    async_add_entities([MatTare(entry), MatFull(entry)])


class _BaseCalibNumber(NumberEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = "g"
    _attr_native_step = 1

    def __init__(self, entry: ConfigEntry, *, suffix: str, default: float) -> None:
        self._sid = entry.data[CONF_SHORT_ID]
        self._default = default
        self._attr_unique_id = f"{DOMAIN}_{self._sid}_{suffix}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, self._sid)})
        self._attr_native_value = default

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in (None, "unknown", "unavailable"):
            try:
                self._attr_native_value = float(last.state)
            except (TypeError, ValueError):
                self._attr_native_value = self._default

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()


class MatTare(_BaseCalibNumber):
    """Empty-tray weight in grams."""

    _attr_name = "Tare"
    _attr_icon = "mdi:scale-balance"
    _attr_native_min_value = 0
    _attr_native_max_value = 10000

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry, suffix=UID_TARE, default=DEFAULT_TARE)


class MatFull(_BaseCalibNumber):
    """Full-tray weight in grams."""

    _attr_name = "Full"
    _attr_icon = "mdi:scale"
    _attr_native_min_value = 0
    _attr_native_max_value = 20000

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry, suffix=UID_FULL, default=DEFAULT_FULL)
