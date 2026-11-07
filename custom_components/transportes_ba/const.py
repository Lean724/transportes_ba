"""Constantes para la integración Transportes de Buenos Aires."""
from datetime import timedelta

DOMAIN = "transportes_ba"

# Config options
CONF_ENABLE_SUBTE = "enable_subte"
CONF_ENABLE_TRENES = "enable_trenes"
CONF_SELECTED_SUBTE_LINES = "selected_subte_lines"
CONF_SELECTED_TRENES_LINES = "selected_trenes_lines"

# Intervalos de sondeo
SCAN_INTERVAL_SUBTE = timedelta(minutes=3)
SCAN_INTERVAL_TRENES = timedelta(minutes=5)

# Endpoints por defecto y APIs en vivo
URL_SUBTE_STATUS = "https://emova.com.ar/servicios/estado_lineas.json"
URL_SUBTE_SIGNALR = "https://info.emova.com.ar/EstadoLineas/signalr"
URL_TRENES_STATUS = "https://api.sofse.gob.ar/v1/estado-servicios"
URL_SOFSE_API_BASE = "https://api-servicios.sofse.gob.ar/v1"

# Líneas soportadas
SUBTE_LINES = ["A", "B", "C", "D", "E", "H", "Premetro"]
TRENES_LINES = [
    "Sarmiento",
    "Mitre",
    "Roca",
    "San Martín",
    "Belgrano Sur",
    "Belgrano Norte",
    "Urquiza",
    "Tren de la Costa",
]

# Mapeo de IDs de gerencia SOFSE a nombres de línea
SOFSE_GERENCIA_MAP = {
    1: "Sarmiento",
    5: "Mitre",
    11: "Roca",
    21: "Belgrano Sur",
    31: "San Martín",
    41: "Tren de la Costa",
    61: "Belgrano Norte",
    71: "Urquiza",
}

# Claves de coordinadores en hass.data
KEY_COORDINATOR_SUBTE = "coordinator_subte"
KEY_COORDINATOR_TRENES = "coordinator_trenes"
