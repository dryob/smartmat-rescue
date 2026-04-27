"""SmartMat Dashboard — per-mat inventory entities + Lovelace card."""
from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CARD_URL,
    CONF_SHORT_ID,
    CONF_WEIGHT_ENTITY,
    DOMAIN,
    PLATFORMS,
    VERSION,
)

_WEIGHT_RE = re.compile(r"^sensor\.smartmat_([a-z0-9]+)_weight$")

_LOGGER = logging.getLogger(__name__)

_CARD_REGISTERED_KEY = "_card_registered"
_LOCAL_CARD_FILE = "smartmat-card.js"


def _copy_card_to_local(src: str, dst_dir: str) -> str | None:
    """Copy smartmat-card.js into <config>/www/ so it is served at /local/...

    Runs in executor (blocking IO). Only copies if missing or content differs.
    Returns dst path on success, None on failure. Also handles the source-exists
    check so the calling async path doesn't need its own blocking stat().
    """
    src_path = Path(src)
    if not src_path.exists():
        return None
    dst_path = Path(dst_dir) / _LOCAL_CARD_FILE
    try:
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        src_bytes = src_path.read_bytes()
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
    # NOTE: existence check happens inside _copy_card_to_local (executor thread)
    # to avoid blocking the event loop on a stat() call.

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
        # Only mark registered when at least the /local/ copy succeeded; otherwise
        # we want a retry on next setup attempt rather than silently giving up.
        domain_bucket[_CARD_REGISTERED_KEY] = True
    else:
        _LOGGER.warning(
            "Could not copy smartmat-card.js to <config>/www/. Use /smartmat_dashboard/smartmat-card.js as your Lovelace Resource URL instead."
        )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration (YAML mode unused — all UI)."""
    hass.data.setdefault(DOMAIN, {})
    await _async_register_card(hass)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """v1 -> v2: replace short (last-4) id with full device id everywhere.

    v1 stored the last 4 chars of the device id in CONF_SHORT_ID, used the same
    suffix in entity unique_ids and the device-registry identifier. Devices
    sharing a 4-char suffix collided. v2 uses the full id throughout.
    """
    if entry.version >= 2:
        return True

    weight_eid = entry.data.get(CONF_WEIGHT_ENTITY)
    m = _WEIGHT_RE.match(weight_eid or "")
    if not m:
        _LOGGER.error(
            "Cannot migrate %s: weight entity %r does not match expected pattern",
            entry.entry_id, weight_eid,
        )
        return False

    full_id = m.group(1)
    old_short = entry.data.get(CONF_SHORT_ID, full_id[-4:])
    if old_short == full_id:
        # already full-form somehow; just bump the version.
        hass.config_entries.async_update_entry(entry, version=2)
        return True

    _LOGGER.info(
        "Migrating %s: CONF_SHORT_ID '%s' -> '%s'", entry.entry_id, old_short, full_id,
    )

    # Rewrite entity_registry unique_ids: {DOMAIN}_{old_short}_<suffix> -> _{full_id}_<suffix>
    ent_reg = er.async_get(hass)
    old_prefix = f"{DOMAIN}_{old_short}_"
    new_prefix = f"{DOMAIN}_{full_id}_"
    for ent in list(ent_reg.entities.values()):
        if ent.platform != DOMAIN:
            continue
        if ent.unique_id.startswith(old_prefix):
            new_uid = new_prefix + ent.unique_id[len(old_prefix):]
            ent_reg.async_update_entity(ent.entity_id, new_unique_id=new_uid)

    # Rewrite device_registry identifier: (DOMAIN, old_short) -> (DOMAIN, full_id)
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device(identifiers={(DOMAIN, old_short)})
    if device is not None:
        new_idents = {(DOMAIN, full_id)} | {
            i for i in device.identifiers if i != (DOMAIN, old_short)
        }
        dev_reg.async_update_device(device.id, new_identifiers=new_idents)

    # Update entry: data + unique_id + version.
    new_data = {**entry.data, CONF_SHORT_ID: full_id}
    hass.config_entries.async_update_entry(
        entry,
        data=new_data,
        unique_id=f"mat_{full_id}",
        version=2,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SmartMat Dashboard from a config entry (one entry = one mat)."""
    hass.data.setdefault(DOMAIN, {})
    await _async_register_card(hass)

    hass.data[DOMAIN][entry.entry_id] = {
        "weight_entity": entry.data[CONF_WEIGHT_ENTITY],
        "short_id": entry.data[CONF_SHORT_ID],
    }

    # Register device so all entities group under one card in HA UI.
    # CONF_SHORT_ID now holds the FULL device id; show only the last 4 chars
    # in the human-readable device name to keep titles tidy.
    sid = entry.data[CONF_SHORT_ID]
    short = sid[-4:]
    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, sid)},
        name=f"SmartMat {short}",
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
