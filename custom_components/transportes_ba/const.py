"""Constantes para la integración Transportes de Buenos Aires."""
from datetime import timedelta

DOMAIN = "transportes_ba"

# Opciones de configuración en español - Paso 1: Redes, Líneas y Radio
CONF_HABILITAR_SUBTE = "habilitar_subte"
CONF_HABILITAR_TRENES = "habilitar_trenes"
CONF_LINEAS_SUBTE_SELECCIONADAS = "lineas_subte_seleccionadas"
CONF_LINEAS_TRENES_SELECCIONADAS = "lineas_trenes_seleccionadas"
CONF_HABILITAR_ESTACIONES_CERCANAS = "habilitar_estaciones_cercanas"
CONF_RADIO_HOGAR_KM = "radio_hogar_km"

# Opciones de configuración en español - Paso 2: Estaciones y API GCBA
CONF_ESTACIONES_SELECCIONADAS = "estaciones_seleccionadas"
CONF_GCBA_CLIENT_ID = "gcba_client_id"
CONF_GCBA_CLIENT_SECRET = "gcba_client_secret"

# Compatibilidad con claves anteriores
CONF_ENABLE_SUBTE = CONF_HABILITAR_SUBTE
CONF_ENABLE_TRENES = CONF_HABILITAR_TRENES
CONF_SELECTED_SUBTE_LINES = CONF_LINEAS_SUBTE_SELECCIONADAS
CONF_SELECTED_TRENES_LINES = CONF_LINEAS_TRENES_SELECCIONADAS
CONF_ENABLE_NEARBY_STATIONS = CONF_HABILITAR_ESTACIONES_CERCANAS
CONF_HOME_RADIUS_KM = CONF_RADIO_HOGAR_KM
CONF_SELECTED_STATIONS = CONF_ESTACIONES_SELECCIONADAS

DEFAULT_RADIO_HOGAR_KM = 2.0
DEFAULT_HOME_RADIUS_KM = DEFAULT_RADIO_HOGAR_KM

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
