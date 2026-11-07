"""Flujo de configuración interactivo para Transportes de Buenos Aires."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_ENABLE_SUBTE,
    CONF_ENABLE_TRENES,
    CONF_SELECTED_SUBTE_LINES,
    CONF_SELECTED_TRENES_LINES,
    DOMAIN,
    SUBTE_LINES,
    TRENES_LINES,
)

DEFAULT_TRENES_SELECTION = ["Sarmiento", "Mitre", "Roca"]


def _build_schema(
    enable_subte: bool = True,
    selected_subte: list[str] | None = None,
    enable_trenes: bool = True,
    selected_trenes: list[str] | None = None,
) -> vol.Schema:
    """Construye el esquema de formulario compartido entre ConfigFlow y OptionsFlow."""
    return vol.Schema(
        {
            vol.Required(CONF_ENABLE_SUBTE, default=enable_subte): bool,
            vol.Optional(
                CONF_SELECTED_SUBTE_LINES,
                default=SUBTE_LINES if selected_subte is None else selected_subte,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=SUBTE_LINES,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(CONF_ENABLE_TRENES, default=enable_trenes): bool,
            vol.Optional(
                CONF_SELECTED_TRENES_LINES,
                default=(
                    DEFAULT_TRENES_SELECTION
                    if selected_trenes is None
                    else selected_trenes
                ),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=TRENES_LINES,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


class TransportesBAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Manejo del Config Flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Paso inicial: configuración de medios y líneas."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Evita crear entradas duplicadas
            await self.async_set_unique_id("transportes_ba_amba")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title="Transportes de Buenos Aires",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TransportesBAOptionsFlowHandler:
        """Devuelve el manejador de opciones para reconfigurar líneas."""
        return TransportesBAOptionsFlowHandler(config_entry)


class TransportesBAOptionsFlowHandler(config_entries.OptionsFlow):
    """Permite modificar medios y líneas monitoreadas desde la UI."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    def _current(self, key: str, default: Any) -> Any:
        if key in self._config_entry.options:
            return self._config_entry.options[key]
        return self._config_entry.data.get(key, default)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Gestiona las opciones de configuración."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = _build_schema(
            enable_subte=self._current(CONF_ENABLE_SUBTE, True),
            selected_subte=self._current(CONF_SELECTED_SUBTE_LINES, SUBTE_LINES),
            enable_trenes=self._current(CONF_ENABLE_TRENES, True),
            selected_trenes=self._current(
                CONF_SELECTED_TRENES_LINES, DEFAULT_TRENES_SELECTION
            ),
        )

        return self.async_show_form(step_id="init", data_schema=schema)
