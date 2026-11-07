"""Flujo de configuración interactivo para Transportes de Buenos Aires."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_ENABLE_NEARBY_STATIONS,
    CONF_ENABLE_SUBTE,
    CONF_ENABLE_TRENES,
    CONF_ESTACIONES_SELECCIONADAS,
    CONF_GCBA_CLIENT_ID,
    CONF_GCBA_CLIENT_SECRET,
    CONF_HABILITAR_ESTACIONES_CERCANAS,
    CONF_HABILITAR_SUBTE,
    CONF_HABILITAR_TRENES,
    CONF_HOME_RADIUS_KM,
    CONF_LINEAS_SUBTE_SELECCIONADAS,
    CONF_LINEAS_TRENES_SELECCIONADAS,
    CONF_RADIO_HOGAR_KM,
    CONF_SELECTED_STATIONS,
    CONF_SELECTED_SUBTE_LINES,
    CONF_SELECTED_TRENES_LINES,
    DEFAULT_RADIO_HOGAR_KM,
    DOMAIN,
    SUBTE_LINES,
    TRENES_LINES,
)
from .stations import get_nearby_station_keys, get_stations_for_lines

DEFAULT_TRENES_SELECTION = ["Sarmiento", "Mitre", "Roca"]

LEGACY_KEY_MAP = {
    CONF_HABILITAR_SUBTE: "enable_subte",
    CONF_HABILITAR_TRENES: "enable_trenes",
    CONF_LINEAS_SUBTE_SELECCIONADAS: "selected_subte_lines",
    CONF_LINEAS_TRENES_SELECCIONADAS: "selected_trenes_lines",
    CONF_HABILITAR_ESTACIONES_CERCANAS: "enable_nearby_stations",
    CONF_RADIO_HOGAR_KM: "home_radius_km",
    CONF_ESTACIONES_SELECCIONADAS: "selected_stations",
}


def _build_step1_schema(
    habilitar_subte: bool = True,
    lineas_subte: list[str] | None = None,
    habilitar_trenes: bool = True,
    lineas_trenes: list[str] | None = None,
    habilitar_cercanas: bool = True,
    radio_km: float = DEFAULT_RADIO_HOGAR_KM,
) -> vol.Schema:
    """Construye el esquema del Paso 1 (Redes, Líneas y Radio del Hogar)."""
    return vol.Schema(
        {
            vol.Required(CONF_HABILITAR_SUBTE, default=habilitar_subte): bool,
            vol.Optional(
                CONF_LINEAS_SUBTE_SELECCIONADAS,
                default=SUBTE_LINES if lineas_subte is None else lineas_subte,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=SUBTE_LINES,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(CONF_HABILITAR_TRENES, default=habilitar_trenes): bool,
            vol.Optional(
                CONF_LINEAS_TRENES_SELECCIONADAS,
                default=(
                    DEFAULT_TRENES_SELECTION
                    if lineas_trenes is None
                    else lineas_trenes
                ),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=TRENES_LINES,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_HABILITAR_ESTACIONES_CERCANAS, default=habilitar_cercanas
            ): bool,
            vol.Optional(
                CONF_RADIO_HOGAR_KM, default=radio_km
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.2,
                    max=15.0,
                    step=0.1,
                    unit_of_measurement="km",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


def _build_step2_stations_schema(
    hass: HomeAssistant,
    step1_data: dict[str, Any],
    existing_stations: list[str] | None = None,
    gcba_client_id: str = "",
    gcba_client_secret: str = "",
) -> vol.Schema:
    """Construye el esquema del Paso 2 (Estaciones detectadas por radio + API opcional)."""
    home_lat = getattr(hass.config, "latitude", None)
    home_lon = getattr(hass.config, "longitude", None)
    radius_km = float(
        step1_data.get(
            CONF_RADIO_HOGAR_KM,
            step1_data.get(CONF_HOME_RADIUS_KM, DEFAULT_RADIO_HOGAR_KM),
        )
    )

    enable_subte = step1_data.get(
        CONF_HABILITAR_SUBTE, step1_data.get(CONF_ENABLE_SUBTE, True)
    )
    subte_lines = (
        step1_data.get(
            CONF_LINEAS_SUBTE_SELECCIONADAS,
            step1_data.get(CONF_SELECTED_SUBTE_LINES, []),
        )
        if enable_subte
        else []
    )

    enable_trenes = step1_data.get(
        CONF_HABILITAR_TRENES, step1_data.get(CONF_ENABLE_TRENES, True)
    )
    trenes_lines = (
        step1_data.get(
            CONF_LINEAS_TRENES_SELECCIONADAS,
            step1_data.get(CONF_SELECTED_TRENES_LINES, []),
        )
        if enable_trenes
        else []
    )

    available_stations = get_stations_for_lines(
        subte_lines=subte_lines,
        trenes_lines=trenes_lines,
        home_lat=home_lat,
        home_lon=home_lon,
    )
    options: list[selector.SelectOptionDict] = []
    valid_keys: set[str] = set()

    for st in available_stations:
        valid_keys.add(st["key"])
        prefix = "Tren" if st["network"] == "tren" else "Subte"
        dist_km = st.get("distancia_km", st.get("distance_km"))
        dist_str = f" ({dist_km:.1f} km)" if dist_km is not None else ""
        label = f"{prefix} {st['line']} - {st['name']}{dist_str}"
        options.append(selector.SelectOptionDict(value=st["key"], label=label))

    nearby_keys = get_nearby_station_keys(
        home_lat=home_lat,
        home_lon=home_lon,
        radius_km=radius_km,
        subte_lines=subte_lines,
        trenes_lines=trenes_lines,
    )

    if existing_stations is not None:
        filtered = [k for k in existing_stations if k in valid_keys]
        default_stations = filtered if filtered else nearby_keys
    else:
        default_stations = nearby_keys

    return vol.Schema(
        {
            vol.Optional(
                CONF_ESTACIONES_SELECCIONADAS,
                default=default_stations,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_GCBA_CLIENT_ID,
                default=gcba_client_id,
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Optional(
                CONF_GCBA_CLIENT_SECRET,
                default=gcba_client_secret,
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        }
    )


class TransportesBAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Manejo del Config Flow en 2 pasos."""

    VERSION = 1

    def __init__(self) -> None:
        self._step1_data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Paso 1: Selección de redes, líneas y radio de proximidad."""
        if user_input is not None:
            await self.async_set_unique_id("transportes_ba_amba")
            self._abort_if_unique_id_configured()

            self._step1_data = dict(user_input)
            if self._step1_data.get(
                CONF_HABILITAR_ESTACIONES_CERCANAS,
                self._step1_data.get(CONF_ENABLE_NEARBY_STATIONS, False),
            ):
                return await self.async_step_stations()

            return self.async_create_entry(
                title="Transportes de Buenos Aires",
                data=self._step1_data,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_step1_schema(),
            errors={},
        )

    async def async_step_stations(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Paso 2: Confirmación de estaciones cercanas/manuales y credenciales opcionales."""
        if user_input is not None:
            combined_data = {**self._step1_data, **user_input}
            return self.async_create_entry(
                title="Transportes de Buenos Aires",
                data=combined_data,
            )

        return self.async_show_form(
            step_id="stations",
            data_schema=_build_step2_stations_schema(self.hass, self._step1_data),
            errors={},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TransportesBAOptionsFlowHandler:
        """Devuelve el manejador de opciones para reconfigurar líneas y estaciones."""
        return TransportesBAOptionsFlowHandler(config_entry)


class TransportesBAOptionsFlowHandler(config_entries.OptionsFlow):
    """Permite modificar líneas, radio de estaciones y API GCBA desde la UI."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        self._step1_data: dict[str, Any] = {}

    def _current(self, key: str, default: Any) -> Any:
        legacy_key = LEGACY_KEY_MAP.get(key)
        for store in (self._config_entry.options, self._config_entry.data):
            if key in store:
                return store[key]
            if legacy_key and legacy_key in store:
                return store[legacy_key]
        return default

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Paso 1 de opciones: Redes, líneas y radio."""
        if user_input is not None:
            self._step1_data = dict(user_input)
            if self._step1_data.get(
                CONF_HABILITAR_ESTACIONES_CERCANAS,
                self._step1_data.get(CONF_ENABLE_NEARBY_STATIONS, False),
            ):
                return await self.async_step_stations()

            self._step1_data[CONF_ESTACIONES_SELECCIONADAS] = []
            return self.async_create_entry(title="", data=self._step1_data)

        schema = _build_step1_schema(
            habilitar_subte=self._current(CONF_HABILITAR_SUBTE, True),
            lineas_subte=self._current(CONF_LINEAS_SUBTE_SELECCIONADAS, SUBTE_LINES),
            habilitar_trenes=self._current(CONF_HABILITAR_TRENES, True),
            lineas_trenes=self._current(
                CONF_LINEAS_TRENES_SELECCIONADAS, DEFAULT_TRENES_SELECTION
            ),
            habilitar_cercanas=self._current(
                CONF_HABILITAR_ESTACIONES_CERCANAS, True
            ),
            radio_km=float(
                self._current(CONF_RADIO_HOGAR_KM, DEFAULT_RADIO_HOGAR_KM)
            ),
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_stations(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Paso 2 de opciones: Selección de estaciones y parámetros API."""
        if user_input is not None:
            combined = {**self._step1_data, **user_input}
            return self.async_create_entry(title="", data=combined)

        schema = _build_step2_stations_schema(
            hass=self.hass,
            step1_data=self._step1_data,
            existing_stations=self._current(CONF_ESTACIONES_SELECCIONADAS, None),
            gcba_client_id=self._current(CONF_GCBA_CLIENT_ID, ""),
            gcba_client_secret=self._current(CONF_GCBA_CLIENT_SECRET, ""),
        )
        return self.async_show_form(step_id="stations", data_schema=schema)
