"""Inicialización de Transportes de Buenos Aires."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ENABLE_NEARBY_STATIONS,
    CONF_ENABLE_SUBTE,
    CONF_ENABLE_TRENES,
    CONF_GCBA_CLIENT_ID,
    CONF_GCBA_CLIENT_SECRET,
    CONF_HOME_RADIUS_KM,
    CONF_SELECTED_STATIONS,
    CONF_SELECTED_SUBTE_LINES,
    CONF_SELECTED_TRENES_LINES,
    DEFAULT_HOME_RADIUS_KM,
    DOMAIN,
    KEY_COORDINATOR_STATIONS,
    KEY_COORDINATOR_SUBTE,
    KEY_COORDINATOR_TRENES,
    SUBTE_LINES,
)
from .coordinator import (
    StationsDataUpdateCoordinator,
    SubteDataUpdateCoordinator,
    TrenesDataUpdateCoordinator,
)
from .stations import get_nearby_station_keys

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


def get_config_value(entry: ConfigEntry, key: str, default=None):
    """Obtiene un valor desde options con fallback a data."""
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


def resolve_monitored_stations(hass: HomeAssistant, entry: ConfigEntry) -> list[str]:
    """Resuelve las estaciones monitoreadas (seleccionadas + detectadas por radio si no se fijaron)."""
    if not get_config_value(entry, CONF_ENABLE_NEARBY_STATIONS, False):
        return []

    explicit = get_config_value(entry, CONF_SELECTED_STATIONS, None)
    if explicit is not None:
        return list(explicit)

    home_lat = getattr(hass.config, "latitude", None)
    home_lon = getattr(hass.config, "longitude", None)
    radius_km = float(
        get_config_value(entry, CONF_HOME_RADIUS_KM, DEFAULT_HOME_RADIUS_KM)
    )
    subte_lines = (
        get_config_value(entry, CONF_SELECTED_SUBTE_LINES, SUBTE_LINES)
        if get_config_value(entry, CONF_ENABLE_SUBTE, True)
        else []
    )
    trenes_lines = (
        get_config_value(entry, CONF_SELECTED_TRENES_LINES, [])
        if get_config_value(entry, CONF_ENABLE_TRENES, True)
        else []
    )
    return get_nearby_station_keys(
        home_lat=home_lat,
        home_lon=home_lon,
        radius_km=radius_km,
        subte_lines=subte_lines,
        trenes_lines=trenes_lines,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configura la integración desde una entrada de configuración de la UI."""
    hass.data.setdefault(DOMAIN, {})
    entry_data = {}

    subte_coord: SubteDataUpdateCoordinator | None = None
    trenes_coord: TrenesDataUpdateCoordinator | None = None

    # Instanciar e inicializar Subte si está habilitado
    if get_config_value(entry, CONF_ENABLE_SUBTE, True):
        subte_coord = SubteDataUpdateCoordinator(hass)
        await subte_coord.async_config_entry_first_refresh()
        entry_data[KEY_COORDINATOR_SUBTE] = subte_coord

    # Instanciar e inicializar Trenes si está habilitado
    if get_config_value(entry, CONF_ENABLE_TRENES, True):
        trenes_coord = TrenesDataUpdateCoordinator(hass)
        await trenes_coord.async_config_entry_first_refresh()
        entry_data[KEY_COORDINATOR_TRENES] = trenes_coord

    # Instanciar e inicializar Coordinador de Estaciones Cercanas / Seleccionadas
    station_keys = resolve_monitored_stations(hass, entry)
    if station_keys:
        stations_coord = StationsDataUpdateCoordinator(
            hass=hass,
            station_keys=station_keys,
            subte_coord=subte_coord,
            trenes_coord=trenes_coord,
            gcba_client_id=get_config_value(entry, CONF_GCBA_CLIENT_ID, ""),
            gcba_client_secret=get_config_value(entry, CONF_GCBA_CLIENT_SECRET, ""),
        )
        await stations_coord.async_config_entry_first_refresh()
        entry_data[KEY_COORDINATOR_STATIONS] = stations_coord

    hass.data[DOMAIN][entry.entry_id] = entry_data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Recarga la entrada de configuración cuando cambian las opciones."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Descarga una entrada de configuración."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
