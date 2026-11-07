"""Plataforma de binary_sensor para alertas operativas directas."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .classifier import classify_service_status
from .const import (
    CONF_SELECTED_SUBTE_LINES,
    CONF_SELECTED_TRENES_LINES,
    DOMAIN,
    KEY_COORDINATOR_SUBTE,
    KEY_COORDINATOR_TRENES,
    STATUS_CATEGORY_UNKNOWN,
)


def _get_selected_lines(entry: ConfigEntry, key: str) -> list[str]:
    """Obtiene las líneas seleccionadas desde options o data."""
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, [])


def _is_operational_alert(line_data: dict[str, Any]) -> bool:
    """Evalúa si los datos de la línea representan un problema operativo activo."""
    if "alerta_operativa" in line_data:
        return bool(line_data["alerta_operativa"])
    classified = classify_service_status(
        line_data.get("estado", ""),
        line_data.get("mensaje", ""),
    )
    return bool(classified["alerta_operativa"])


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Instancia los sensores binarios de alerta seleccionados."""
    coordinators = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = []

    if KEY_COORDINATOR_SUBTE in coordinators:
        coord = coordinators[KEY_COORDINATOR_SUBTE]
        for line in _get_selected_lines(entry, CONF_SELECTED_SUBTE_LINES):
            entities.append(SubteAlertBinarySensor(coord, line))

    if KEY_COORDINATOR_TRENES in coordinators:
        coord = coordinators[KEY_COORDINATOR_TRENES]
        for line in _get_selected_lines(entry, CONF_SELECTED_TRENES_LINES):
            entities.append(TrenAlertBinarySensor(coord, line))

    async_add_entities(entities)


class SubteAlertBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representa si existe una incidencia operativa activa en la línea de Subte."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, line_code: str) -> None:
        super().__init__(coordinator)
        self.line_code = line_code
        self._attr_name = (
            "Premetro Alerta"
            if line_code.lower() == "premetro"
            else f"Subte Línea {line_code} Alerta"
        )
        self._attr_unique_id = f"transportes_ba_subte_alert_{line_code.lower()}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "subte_emova")},
            name="Red de Subte y Premetro (Emova)",
            manufacturer="Emova Movilidad S.A.",
            model="Subte de Buenos Aires",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://emova.com.ar/",
        )

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data or {}
        line_data = data.get(self.line_code, {})
        return _is_operational_alert(line_data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        line_data = data.get(self.line_code, {})
        return {
            "estado": line_data.get("estado", "Desconocido"),
            "categoria": line_data.get("categoria", STATUS_CATEGORY_UNKNOWN),
            "mensaje": line_data.get("mensaje", ""),
        }


class TrenAlertBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representa si existe una incidencia operativa activa en la línea de Tren."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, line_name: str) -> None:
        super().__init__(coordinator)
        self.line_name = line_name
        clean_id = line_name.lower().replace(" ", "_")
        self._attr_name = f"Tren {line_name} Alerta"
        self._attr_unique_id = f"transportes_ba_tren_alert_{clean_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "trenes_amba")},
            name="Trenes Metropolitanos (AMBA)",
            manufacturer="Trenes Argentinos / SOFSE",
            model="Red Ferroviaria Metropolitana",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://www.argentina.gob.ar/transporte/trenes-argentinos",
        )

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data or {}
        line_data = data.get(self.line_name, {})
        return _is_operational_alert(line_data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        line_data = data.get(self.line_name, {})
        return {
            "estado": line_data.get("estado", "Desconocido"),
            "categoria": line_data.get("categoria", STATUS_CATEGORY_UNKNOWN),
            "mensaje": line_data.get("mensaje", ""),
        }
