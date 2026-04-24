"""SmartMat Dashboard — per-mat inventory tracker with auto-dashboard."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_SHORT_ID, CONF_WEIGHT_ENTITY, DOMAIN, PLATFORMS
from .lovelace import async_rebuild_view

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration (YAML mode unused — all UI)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SmartMat Dashboard from a config entry (one entry = one mat)."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "weight_entity": entry.data[CONF_WEIGHT_ENTITY],
        "short_id": entry.data[CONF_SHORT_ID],
    }

    # Register device so all entities group under one card in HA UI
    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.data[CONF_SHORT_ID])},
        name=f"SmartMat {entry.data[CONF_SHORT_ID]}",
        manufacturer="SmartMat",
        model="Lite Inventory Tracker",
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Rebuild the dashboard view with all currently-configured mats
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    hass.async_create_task(async_rebuild_view(hass))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        hass.async_create_task(async_rebuild_view(hass))
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal — trigger dashboard rebuild so the tile disappears."""
    hass.async_create_task(async_rebuild_view(hass))


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
