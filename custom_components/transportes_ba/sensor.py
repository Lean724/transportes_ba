"""Plataforma de sensores para Transportes de Buenos Aires."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_SELECTED_SUBTE_LINES,
    CONF_SELECTED_TRENES_LINES,
    DOMAIN,
    KEY_COORDINATOR_STATIONS,
    KEY_COORDINATOR_SUBTE,
    KEY_COORDINATOR_TRENES,
    STATUS_CATEGORY_UNKNOWN,
)
from .stations import get_station_by_key


def _get_selected_lines(entry: ConfigEntry, key: str) -> list[str]:
    """Obtiene las líneas seleccionadas desde options o data."""
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, [])


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Instancia los sensores de líneas y de estaciones cercanas/seleccionadas."""
    coordinators = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []

    # 1. Sensores de estado de red de Subte
    if KEY_COORDINATOR_SUBTE in coordinators:
        coord = coordinators[KEY_COORDINATOR_SUBTE]
        selected_lines = _get_selected_lines(entry, CONF_SELECTED_SUBTE_LINES)
        for line in selected_lines:
            entities.append(SubteLineSensor(coord, line))

    # 2. Sensores de estado de red de Trenes
    if KEY_COORDINATOR_TRENES in coordinators:
        coord = coordinators[KEY_COORDINATOR_TRENES]
        selected_lines = _get_selected_lines(entry, CONF_SELECTED_TRENES_LINES)
        for line in selected_lines:
            entities.append(TrenLineSensor(coord, line))

    # 3. Sensores de estaciones cercanas / seleccionadas (Próximos arribos)
    if KEY_COORDINATOR_STATIONS in coordinators:
        st_coord = coordinators[KEY_COORDINATOR_STATIONS]
        for st_key in st_coord.station_keys:
            st_meta = get_station_by_key(st_key)
            if st_meta:
                entities.append(StationArrivalSensor(st_coord, st_meta))

    async_add_entities(entities)


class SubteLineSensor(CoordinatorEntity, SensorEntity):
    """Sensor que reporta el estado detallado de una línea de Subte."""

    def __init__(self, coordinator, line_code: str) -> None:
        super().__init__(coordinator)
        self.line_code = line_code
        self._attr_name = (
            "Premetro" if line_code.lower() == "premetro" else f"Subte Línea {line_code}"
        )
        self._attr_unique_id = f"transportes_ba_subte_{line_code.lower()}"
        self._attr_icon = "mdi:subway-variant"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "subte_emova")},
            name="Red de Subte y Premetro (Emova)",
            manufacturer="Emova Movilidad S.A.",
            model="Subte de Buenos Aires",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://emova.com.ar/",
        )

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data or {}
        line_data = data.get(self.line_code, {})
        return line_data.get("estado", "Desconocido")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        line_data = data.get(self.line_code, {})
        attrs: dict[str, Any] = {
            "categoria": line_data.get("categoria", STATUS_CATEGORY_UNKNOWN),
            "alerta_operativa": line_data.get("alerta_operativa", False),
            "mensaje": line_data.get("mensaje", ""),
            "frecuencia": line_data.get("frecuencia"),
        }
        if "actualizado" in line_data and line_data["actualizado"]:
            attrs["actualizado"] = line_data["actualizado"]
        return attrs


class TrenLineSensor(CoordinatorEntity, SensorEntity):
    """Sensor que reporta el estado detallado de una línea de Tren."""

    def __init__(self, coordinator, line_name: str) -> None:
        super().__init__(coordinator)
        self.line_name = line_name
        self._attr_name = f"Tren {line_name}"
        clean_id = line_name.lower().replace(" ", "_")
        self._attr_unique_id = f"transportes_ba_tren_{clean_id}"
        self._attr_icon = "mdi:train"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "trenes_amba")},
            name="Trenes Metropolitanos (AMBA)",
            manufacturer="Trenes Argentinos / SOFSE",
            model="Red Ferroviaria Metropolitana",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://www.argentina.gob.ar/transporte/trenes-argentinos",
        )

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data or {}
        line_data = data.get(self.line_name, {})
        return line_data.get("estado", "Desconocido")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        line_data = data.get(self.line_name, {})
        return {
            "categoria": line_data.get("categoria", STATUS_CATEGORY_UNKNOWN),
            "alerta_operativa": line_data.get("alerta_operativa", False),
            "mensaje": line_data.get("mensaje", ""),
            "ramales": line_data.get("ramales", []),
        }


class StationArrivalSensor(CoordinatorEntity, SensorEntity):
    """Sensor de próximos arribos y estado operativo de una estación específica."""

    def __init__(self, coordinator, station_meta: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self.station_meta = station_meta
        self.station_key = station_meta["key"]
        network = station_meta["network"]
        line = station_meta["line"]
        name = station_meta["name"]
        st_id = str(station_meta["id"]).lower().replace(" ", "_")
        clean_line = line.lower().replace(" ", "_")

        if network == "tren":
            self._attr_name = f"Estación {name} ({line})"
            self._attr_unique_id = f"transportes_ba_estacion_tren_{clean_line}_{st_id}"
            self._attr_icon = "mdi:train-clock"
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, "trenes_amba")},
                name="Trenes Metropolitanos (AMBA)",
                manufacturer="Trenes Argentinos / SOFSE",
                model="Red Ferroviaria Metropolitana",
                entry_type=DeviceEntryType.SERVICE,
                configuration_url="https://www.argentina.gob.ar/transporte/trenes-argentinos",
            )
        else:
            line_label = line if line.lower() == "premetro" else f"Subte {line}"
            self._attr_name = f"Estación {name} ({line_label})"
            self._attr_unique_id = f"transportes_ba_estacion_subte_{clean_line}_{st_id}"
            self._attr_icon = "mdi:subway"
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, "subte_emova")},
                name="Red de Subte y Premetro (Emova)",
                manufacturer="Emova Movilidad S.A.",
                model="Subte de Buenos Aires",
                entry_type=DeviceEntryType.SERVICE,
                configuration_url="https://emova.com.ar/",
            )

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data or {}
        st_data = data.get(self.station_key, {})
        return st_data.get("estado", "Desconocido")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        st_data = data.get(self.station_key, {})
        arribos = st_data.get("arribos", [])
        attrs: dict[str, Any] = {
            "red": self.station_meta["network"],
            "linea": self.station_meta["line"],
            "estacion": self.station_meta["name"],
            "id_estacion": self.station_meta["id"],
            "latitud": self.station_meta["lat"],
            "longitud": self.station_meta["lon"],
            "distancia_casa_km": st_data.get("distancia_km"),
            "estacion_cerrada": st_data.get("estacion_cerrada", False),
            "proximo_servicio": arribos[0] if arribos else None,
            "arribos": arribos,
            "alerta_linea": st_data.get("alerta_linea", ""),
        }
        if "frecuencia_linea" in st_data:
            attrs["frecuencia_linea"] = st_data.get("frecuencia_linea")
        return attrs
