"""Constantes para la integración Transportes de Buenos Aires."""
from datetime import timedelta

DOMAIN = "transportes_ba"

# Config options - Paso 1: Redes y Líneas
CONF_ENABLE_SUBTE = "enable_subte"
CONF_ENABLE_TRENES = "enable_trenes"
CONF_SELECTED_SUBTE_LINES = "selected_subte_lines"
CONF_SELECTED_TRENES_LINES = "selected_trenes_lines"

# Config options - Paso 2: Estaciones Cercanas y API Opcional
CONF_ENABLE_NEARBY_STATIONS = "enable_nearby_stations"
CONF_HOME_RADIUS_KM = "home_radius_km"
CONF_SELECTED_STATIONS = "selected_stations"
CONF_GCBA_CLIENT_ID = "gcba_client_id"
CONF_GCBA_CLIENT_SECRET = "gcba_client_secret"

DEFAULT_HOME_RADIUS_KM = 2.0

# Intervalos de sondeo
SCAN_INTERVAL_SUBTE = timedelta(minutes=3)
SCAN_INTERVAL_TRENES = timedelta(minutes=5)
SCAN_INTERVAL_STATIONS = timedelta(seconds=60)

# Endpoints por defecto y APIs en vivo
URL_SUBTE_STATUS = "https://emova.com.ar/servicios/estado_lineas.json"
URL_SUBTE_SIGNALR = "https://info.emova.com.ar/EstadoLineas/signalr"
URL_TRENES_STATUS = "https://api.sofse.gob.ar/v1/estado-servicios"
URL_SOFSE_API_BASE = "https://api-servicios.sofse.gob.ar/v1"
URL_SOFSE_ARRIBOS = "https://api-servicios.sofse.gob.ar/v1/arribos/estacion"
URL_GCBA_SUBTE_FORECAST = "https://apitransporte.buenosaires.gob.ar/subtes/forecastGTFS"

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

# Categorías de estado e incidencia
STATUS_CATEGORY_NORMAL = "normal"
STATUS_CATEGORY_ADVISORY = "aviso"
STATUS_CATEGORY_STATION_CLOSED = "estacion_cerrada"
STATUS_CATEGORY_DELAY = "demoras"
STATUS_CATEGORY_LIMITED = "servicio_limitado"
STATUS_CATEGORY_INTERRUPTED = "interrumpido"
STATUS_CATEGORY_UNKNOWN = "desconocido"

# Categorías que representan un problema operativo real en curso (activan binary_sensor)
OPERATIONAL_PROBLEM_CATEGORIES = {
    STATUS_CATEGORY_DELAY,
    STATUS_CATEGORY_LIMITED,
    STATUS_CATEGORY_INTERRUPTED,
}

# Claves de coordinadores en hass.data
KEY_COORDINATOR_SUBTE = "coordinator_subte"
KEY_COORDINATOR_TRENES = "coordinator_trenes"
KEY_COORDINATOR_STATIONS = "coordinator_stations"
