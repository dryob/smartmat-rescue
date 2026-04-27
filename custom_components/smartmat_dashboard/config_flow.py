"""Config flow for SmartMat Dashboard."""
from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
)

from .const import (
    CONF_LAST_SEEN_ENTITY,
    CONF_PRODUCT_NAME,
    CONF_SHORT_ID,
    CONF_WEIGHT_ENTITY,
    DEFAULT_PRODUCT_NAME,
    DOMAIN,
)

SMARTMAT_WEIGHT_RE = re.compile(r"^sensor\.smartmat_([a-z0-9]+)_weight$")


def _device_id_from_weight(entity_id: str) -> str | None:
    """Extract the full device id from sensor.smartmat_XXXX_weight.

    The full id (e.g. 'w42200500161') guarantees uniqueness — using last-4
    chars caused config-entry collisions when two devices shared a suffix.
    """
    m = SMARTMAT_WEIGHT_RE.match(entity_id)
    if not m:
        return None
    return m.group(1)


# Backwards-compat alias for any existing imports.
_short_id_from_weight = _device_id_from_weight


def _last_seen_from_weight(entity_id: str) -> str:
    """Guess the matching last_seen sensor."""
    return entity_id.replace("_weight", "_last_seen")


class SmartMatDashboardConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """One config entry per mat."""

    # v2: CONF_SHORT_ID holds the FULL device id (was last-4 chars in v1, which
    # caused unique_id collisions for devices that share a suffix).
    VERSION = 2

    def _available_weight_sensors(self) -> list[str]:
        """Smartmat weight sensors currently in state machine, minus already-configured ones."""
        matching = [
            eid
            for eid in self.hass.states.async_entity_ids("sensor")
            if SMARTMAT_WEIGHT_RE.match(eid)
        ]
        taken = {
            e.data.get(CONF_WEIGHT_ENTITY)
            for e in self._async_current_entries(include_ignore=False)
        }
        return sorted(eid for eid in matching if eid not in taken)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask the user to pick a smartmat weight sensor."""
        errors: dict[str, str] = {}

        available = self._available_weight_sensors()

        if user_input is not None:
            weight_eid = user_input[CONF_WEIGHT_ENTITY]
            device_id = _device_id_from_weight(weight_eid)
            if device_id is None:
                errors[CONF_WEIGHT_ENTITY] = "not_a_smartmat"
            else:
                # unique_id uses the FULL device id — distinct devices that
                # share a 4-char suffix would otherwise collide.
                await self.async_set_unique_id(f"mat_{device_id}")
                self._abort_if_unique_id_configured()

                # Display: short suffix is friendlier in titles. Stored
                # CONF_SHORT_ID keeps the FULL id so all entity unique_ids
                # downstream are collision-free.
                short = device_id[-4:]
                title = user_input.get(CONF_PRODUCT_NAME) or f"SmartMat {short}"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_WEIGHT_ENTITY: weight_eid,
                        CONF_LAST_SEEN_ENTITY: _last_seen_from_weight(weight_eid),
                        CONF_SHORT_ID: device_id,
                        CONF_PRODUCT_NAME: user_input.get(
                            CONF_PRODUCT_NAME, DEFAULT_PRODUCT_NAME
                        ),
                    },
                )

        if not available:
            return self.async_abort(reason="no_weight_sensors")

        schema = vol.Schema(
            {
                vol.Required(CONF_WEIGHT_ENTITY): EntitySelector(
                    EntitySelectorConfig(
                        include_entities=available,
                    )
                ),
                vol.Optional(
                    CONF_PRODUCT_NAME, default=DEFAULT_PRODUCT_NAME
                ): TextSelector(),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={"count": str(len(available))},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """No options for now (user edits via entity UI)."""
        return SmartMatDashboardOptionsFlow(config_entry)


class SmartMatDashboardOptionsFlow(config_entries.OptionsFlow):
    """Empty options flow (placeholder for future)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=vol.Schema({}))
