"""SmartMat Dashboard — per-mat inventory entities + Lovelace card."""
from __future__ import annotations

import logging
import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import (
    CARD_URL,
    CONF_SHORT_ID,
    CONF_WEIGHT_ENTITY,
    DOMAIN,
    PLATFORMS,
    VERSION,
)

_LOGGER = logging.getLogger(__name__)

_CARD_REGISTERED_KEY = "_card_registered"


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve smartmat-card.js and add it to Lovelace's extra JS URLs (once)."""
    domain_bucket = hass.data.setdefault(DOMAIN, {})
    if domain_bucket.get(_CARD_REGISTERED_KEY):
        return

    js_path = os.path.join(os.path.dirname(__file__), "www", "smartmat-card.js")
    if not os.path.exists(js_path):
        _LOGGER.warning("smartmat-card.js not found at %s", js_path)
        domain_bucket[_CARD_REGISTERED_KEY] = True  # don't retry
        return

    try:
        from homeassistant.components.http import StaticPathConfig  # HA 2024.7+

        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, js_path, True)]
        )
    except ImportError:  # pragma: no cover — older HA
        hass.http.register_static_path(CARD_URL, js_path, cache_headers=True)

    # 只 serve 靜態檔, 不再 add_extra_js_url — 改由使用者手動加 Lovelace Resource
    # 原因: 行動裝置 Service Worker 快取時, add_extra_js_url + Resource 兩條路會打架
    # 導致刷新後 "Custom element doesn't exist" 間歇性發生
    domain_bucket[_CARD_REGISTERED_KEY] = True
    _LOGGER.info("smartmat-card.js static path registered at %s (add via Lovelace Resources)", CARD_URL)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration (YAML mode unused — all UI)."""
    hass.data.setdefault(DOMAIN, {})
    await _async_register_card(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SmartMat Dashboard from a config entry (one entry = one mat)."""
    hass.data.setdefault(DOMAIN, {})
    await _async_register_card(hass)

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
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
