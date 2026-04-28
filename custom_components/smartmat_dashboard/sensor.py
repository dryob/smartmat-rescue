"""Computed inventory-% sensor."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_LAST_SEEN_ENTITY,
    CONF_SHORT_ID,
    CONF_WEIGHT_ENTITY,
    DOMAIN,
    UID_INVENTORY,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the inventory sensor."""
    async_add_entities([MatInventorySensor(hass, entry)])


def _f(state_obj) -> float | None:
    """Safe float conversion from a State."""
    if state_obj is None:
        return None
    try:
        v = float(state_obj.state)
        if v != v:  # NaN guard
            return None
        return v
    except (TypeError, ValueError):
        return None


class MatInventorySensor(SensorEntity):
    """Percent inventory = clamp((weight - tare) / (full - tare) * 100, 0, 100)."""

    _attr_has_entity_name = True
    _attr_name = "Inventory"
    _attr_icon = "mdi:gauge"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    # No device_class — "battery" was wrong (this is inventory %, not a battery
    # remaining %). HA has no semantic class for "% of full" so leave it off.
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._sid = entry.data[CONF_SHORT_ID]
        # Companion entities (tare/full/product) are auto-named by HA from the
        # device's display name "SmartMat <last-4>" → entity_id slug uses last-4.
        # unique_id uses full sid (collision-safe), entity_id uses short.
        short = self._sid[-4:]
        self._weight_eid = entry.data[CONF_WEIGHT_ENTITY]
        self._last_seen_eid = entry.data.get(
            CONF_LAST_SEEN_ENTITY,
            self._weight_eid.replace("_weight", "_last_seen"),
        )
        self._tare_eid = f"number.smartmat_{short}_tare"
        self._full_eid = f"number.smartmat_{short}_full"
        self._product_eid = f"text.smartmat_{short}_product"
        self._attr_unique_id = f"{DOMAIN}_{self._sid}_{UID_INVENTORY}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, self._sid)})
        self._attr_native_value = None

    @property
    def extra_state_attributes(self) -> dict:
        """Expose related entities so the custom card can auto-wire."""
        return {
            "short_id": self._sid,
            "weight_entity": self._weight_eid,
            "tare_entity": self._tare_eid,
            "full_entity": self._full_eid,
            "product_entity": self._product_eid,
            "last_seen_entity": self._last_seen_eid,
        }

    async def async_added_to_hass(self) -> None:
        """Track changes to any of the three inputs."""
        self._recalc()
        self.async_on_remove(
            async_track_state_change_event(
                self._hass,
                [self._weight_eid, self._tare_eid, self._full_eid],
                self._on_source_changed,
            )
        )

    @callback
    def _on_source_changed(self, _event) -> None:
        self._recalc()
        self.async_write_ha_state()

    def _recalc(self) -> None:
        w = _f(self._hass.states.get(self._weight_eid))
        tare = _f(self._hass.states.get(self._tare_eid))
        full = _f(self._hass.states.get(self._full_eid))
        if w is None or tare is None or full is None or full <= tare:
            self._attr_native_value = None
            return
        pct = (w - tare) / (full - tare) * 100.0
        # 不再封頂 100% — 比設定的 full 多裝就如實顯示 (e.g. 120%).
        # 只擋負值 (秤面比 tare 還輕通常是裝置誤差).
        self._attr_native_value = max(0.0, round(pct, 0))
