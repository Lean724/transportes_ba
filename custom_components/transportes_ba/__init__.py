"""Inicialización de Transportes de Buenos Aires."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ENABLE_SUBTE,
    CONF_ENABLE_TRENES,
    DOMAIN,
    KEY_COORDINATOR_SUBTE,
    KEY_COORDINATOR_TRENES,
)
from .coordinator import SubteDataUpdateCoordinator, TrenesDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


def _get_config_value(entry: ConfigEntry, key: str, default):
    """Obtiene un valor desde options con fallback a data."""
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configura la integración desde una entrada de configuración de la UI."""
    hass.data.setdefault(DOMAIN, {})
    entry_data = {}

    # Instanciar e inicializar Subte si está habilitado
    if _get_config_value(entry, CONF_ENABLE_SUBTE, True):
        subte_coord = SubteDataUpdateCoordinator(hass)
        await subte_coord.async_config_entry_first_refresh()
        entry_data[KEY_COORDINATOR_SUBTE] = subte_coord

    # Instanciar e inicializar Trenes si está habilitado
    if _get_config_value(entry, CONF_ENABLE_TRENES, True):
        trenes_coord = TrenesDataUpdateCoordinator(hass)
        await trenes_coord.async_config_entry_first_refresh()
        entry_data[KEY_COORDINATOR_TRENES] = trenes_coord

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
