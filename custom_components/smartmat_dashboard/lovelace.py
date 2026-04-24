"""Auto-build a lovelace view inside dashboard-homio with one tile per mat."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_LAST_SEEN_ENTITY,
    CONF_PRODUCT_NAME,
    CONF_SHORT_ID,
    CONF_WEIGHT_ENTITY,
    DASHBOARD_URL,
    DOMAIN,
    FALLBACK_CRITICAL,
    FALLBACK_LOW,
    FALLBACK_MID,
    THRESHOLD_CRITICAL,
    THRESHOLD_LOW,
    THRESHOLD_MID,
    VIEW_ICON,
    VIEW_PATH,
    VIEW_TITLE,
)

_LOGGER = logging.getLogger(__name__)


def _mat_tile(sid: str, weight_eid: str, last_seen_eid: str) -> dict[str, Any]:
    """Build a single mat's vertical-stack tile."""
    pct_ent = f"sensor.smartmat_{sid}_inventory"
    name_ent = f"text.smartmat_{sid}_product"

    md_lines = [
        "{% set pct = states('" + pct_ent + "') | float(0) %}",
        "{% set c = states('" + THRESHOLD_CRITICAL + "') | float(" + str(FALLBACK_CRITICAL) + ") %}",
        "{% set l = states('" + THRESHOLD_LOW + "') | float(" + str(FALLBACK_LOW) + ") %}",
        "{% set m = states('" + THRESHOLD_MID + "') | float(" + str(FALLBACK_MID) + ") %}",
        "{% set w = states('" + weight_eid + "') %}",
        "{% set ls = states('" + last_seen_eid + "') %}",
        "{% set when = '—' %}",
        "{% if ls not in ['unknown','unavailable','none',''] %}",
        "{% set when = relative_time(ls | as_datetime) %}",
        "{% endif %}",
        "### 📦 {{ states('" + name_ent + "') }}",
        "{% if pct < c %}",
        '<ha-alert alert-type="error">🚨 {{ pct }}% · {{ w }} g · {{ when }}</ha-alert>',
        "{% elif pct < l %}",
        '<ha-alert alert-type="warning">⚠️ {{ pct }}% · {{ w }} g · {{ when }}</ha-alert>',
        "{% elif pct < m %}",
        '<ha-alert alert-type="info">🟡 {{ pct }}% · {{ w }} g · {{ when }}</ha-alert>',
        "{% else %}",
        '<ha-alert alert-type="success">✅ {{ pct }}% · {{ w }} g · {{ when }}</ha-alert>',
        "{% endif %}",
    ]
    return {
        "type": "vertical-stack",
        "cards": [
            {"type": "markdown", "content": "\n".join(md_lines)},
            {
                "type": "gauge",
                "entity": pct_ent,
                "name": " ",
                "min": 0,
                "max": 100,
                "needle": True,
            },
            {
                "type": "entities",
                "entities": [
                    {"entity": name_ent, "name": "商品名"},
                    {"entity": f"number.smartmat_{sid}_tare", "name": "空盤 g"},
                    {"entity": f"number.smartmat_{sid}_full", "name": "滿庫 g"},
                ],
            },
        ],
    }


def _build_view(entries: list[dict[str, str]]) -> dict[str, Any]:
    """Build the full view config."""
    tiles = [
        _mat_tile(e[CONF_SHORT_ID], e[CONF_WEIGHT_ENTITY], e[CONF_LAST_SEEN_ENTITY])
        for e in entries
    ]
    body_card = (
        {
            "type": "grid",
            "columns": 2,
            "square": False,
            "cards": tiles,
        }
        if tiles
        else {
            "type": "markdown",
            "content": (
                "_尚無秤被新增。到 設定 → 裝置與服務 → 新增整合 → "
                "SmartMat Dashboard_"
            ),
        }
    )
    return {
        "title": VIEW_TITLE,
        "path": VIEW_PATH,
        "icon": VIEW_ICON,
        "cards": [
            {
                "type": "markdown",
                "content": (
                    "# 📦 庫存秤\n\n"
                    "商品名・空盤・滿庫 每個秤各自填。警示閾值全域共用。"
                ),
            },
            body_card,
            {
                "type": "entities",
                "title": "⚙️ 警示閾值 (% — 共用)",
                "show_header_toggle": False,
                "entities": [
                    {"entity": THRESHOLD_CRITICAL, "name": "🚨 緊急 (紅)"},
                    {"entity": THRESHOLD_LOW, "name": "⚠️ 低 (橙)"},
                    {"entity": THRESHOLD_MID, "name": "🟡 中 (黃)"},
                ],
            },
        ],
    }


async def async_rebuild_view(hass: HomeAssistant) -> None:
    """Rebuild/patch the inventory view in dashboard-homio.

    Silent no-op if the dashboard isn't storage-mode or doesn't exist.
    """
    try:
        lovelace = hass.data.get("lovelace")
        if not lovelace:
            _LOGGER.debug("lovelace not loaded yet")
            return

        dashboards = getattr(lovelace, "dashboards", None) or {}
        dashboard = dashboards.get(DASHBOARD_URL)
        if dashboard is None:
            _LOGGER.warning(
                "Dashboard %s not found — cannot auto-patch. "
                "Create a storage-mode dashboard with that URL path.",
                DASHBOARD_URL,
            )
            return

        try:
            cfg = await dashboard.async_load(False)
        except Exception as e:  # noqa: BLE001
            _LOGGER.warning("Could not load %s: %s", DASHBOARD_URL, e)
            return

        if not isinstance(cfg, dict):
            _LOGGER.warning("Dashboard %s returned non-dict config", DASHBOARD_URL)
            return

        # Collect every configured mat
        entries_data: list[dict[str, str]] = []
        for entry in hass.config_entries.async_entries(DOMAIN):
            entries_data.append(
                {
                    CONF_SHORT_ID: entry.data[CONF_SHORT_ID],
                    CONF_WEIGHT_ENTITY: entry.data[CONF_WEIGHT_ENTITY],
                    CONF_LAST_SEEN_ENTITY: entry.data.get(
                        CONF_LAST_SEEN_ENTITY,
                        entry.data[CONF_WEIGHT_ENTITY].replace("_weight", "_last_seen"),
                    ),
                    CONF_PRODUCT_NAME: entry.data.get(CONF_PRODUCT_NAME, ""),
                }
            )
        entries_data.sort(key=lambda e: e[CONF_SHORT_ID])

        view_cfg = _build_view(entries_data)

        views = cfg.setdefault("views", [])
        # Strip any prior instance of our view
        views[:] = [v for v in views if v.get("path") != VIEW_PATH]
        views.append(view_cfg)
        cfg["views"] = views

        await dashboard.async_save(cfg)
        _LOGGER.info(
            "Patched %s -> view '%s' with %d mats",
            DASHBOARD_URL,
            VIEW_PATH,
            len(entries_data),
        )
    except Exception as e:  # noqa: BLE001
        _LOGGER.exception("Failed to rebuild dashboard view: %s", e)
