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


def _short_id_from_weight(entity_id: str) -> str | None:
    """Extract last-4 sid from sensor.smartmat_XXXX_weight."""
    m = SMARTMAT_WEIGHT_RE.match(entity_id)
    if not m:
        return None
    return m.group(1)[-4:]


def _last_seen_from_weight(entity_id: str) -> str:
    """Guess the matching last_seen sensor."""
    return entity_id.replace("_weight", "_last_seen")


class SmartMatDashboardConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """One config entry per mat."""

    VERSION = 1

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
            sid = _short_id_from_weight(weight_eid)
            if sid is None:
                errors[CONF_WEIGHT_ENTITY] = "not_a_smartmat"
            else:
                await self.async_set_unique_id(f"mat_{sid}")
                self._abort_if_unique_id_configured()

                title = user_input.get(CONF_PRODUCT_NAME) or f"SmartMat {sid}"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_WEIGHT_ENTITY: weight_eid,
                        CONF_LAST_SEEN_ENTITY: _last_seen_from_weight(weight_eid),
                        CONF_SHORT_ID: sid,
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
