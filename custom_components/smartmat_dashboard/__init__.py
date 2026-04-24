"""SmartMat Dashboard — per-mat inventory entities + Lovelace card."""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

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
_LOCAL_CARD_FILE = "smartmat-card.js"


def _copy_card_to_local(src: str, dst_dir: str) -> str | None:
    """Copy smartmat-card.js into <config>/www/ so it is served at /local/...

    Runs in executor (blocking IO). Only copies if missing or content differs.
    Returns dst path on success, None on failure.
    """
    dst_path = Path(dst_dir) / _LOCAL_CARD_FILE
    try:
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        src_bytes = Path(src).read_bytes()
        if dst_path.exists() and dst_path.read_bytes() == src_bytes:
            return str(dst_path)
        # write atomically
        tmp = dst_path.with_suffix(".js.tmp")
        tmp.write_bytes(src_bytes)
        shutil.move(str(tmp), str(dst_path))
        return str(dst_path)
    except Exception:  # noqa: BLE001
        return None


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve smartmat-card.js (both integration path + /local/)."""
    domain_bucket = hass.data.setdefault(DOMAIN, {})
    if domain_bucket.get(_CARD_REGISTERED_KEY):
        return

    js_path = os.path.join(os.path.dirname(__file__), "www", _LOCAL_CARD_FILE)
    if not os.path.exists(js_path):
        _LOGGER.warning("%s not found at %s", _LOCAL_CARD_FILE, js_path)
        domain_bucket[_CARD_REGISTERED_KEY] = True  # don't retry
        return

    # 1. 註冊 integration 自己的 static path (給手動加 Resource 用)
    try:
        from homeassistant.components.http import StaticPathConfig  # HA 2024.7+

        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, js_path, True)]
        )
    except ImportError:  # pragma: no cover — older HA
        hass.http.register_static_path(CARD_URL, js_path, cache_headers=True)

    # 2. 自動複製到 <config>/www/ 以便 /local/smartmat-card.js 能 serve
    #    — 這條路最穩，沒有 integration lifecycle / SW 快取問題
    www_dir = hass.config.path("www")
    dst = await hass.async_add_executor_job(_copy_card_to_local, js_path, www_dir)
    if dst:
        _LOGGER.info(
            "smartmat-card.js available at /smartmat_dashboard/smartmat-card.js AND /local/smartmat-card.js — add one of these via Settings -> Dashboards -> Resources"
        )
    else:
        _LOGGER.warning(
            "Could not copy smartmat-card.js to <config>/www/. Use /smartmat_dashboard/smartmat-card.js as your Lovelace Resource URL instead."
        )

    domain_bucket[_CARD_REGISTERED_KEY] = True


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
