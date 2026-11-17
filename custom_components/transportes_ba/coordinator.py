"""Coordinadores de actualización para Transportes de Buenos Aires."""
from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timedelta, timezone
import json
import logging
import time
from typing import Any
from urllib.parse import quote

from aiohttp import ClientError, ClientResponseError, ClientTimeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .classifier import (
    classify_service_status,
    is_station_affected_by_message,
    normalize_text,
    truncate_state,
)
from .const import (
    DOMAIN,
    SCAN_INTERVAL_STATIONS,
    SCAN_INTERVAL_SUBTE,
    SCAN_INTERVAL_TRENES,
    SOFSE_GERENCIA_MAP,
    STATUS_CATEGORY_INTERRUPTED,
    STATUS_CATEGORY_NORMAL,
    TRENES_LINES,
    URL_GCBA_SUBTE_FORECAST,
    URL_SOFSE_API_BASE,
    URL_SOFSE_ARRIBOS,
    URL_SUBTE_SIGNALR,
    URL_SUBTE_STATUS,
    URL_TRENES_STATUS,
)
from .stations import get_station_by_key, haversine_km

_LOGGER = logging.getLogger(__name__)
REQUEST_TIMEOUT = ClientTimeout(total=15)

SIGNALR_CONNECTION_DATA = '[{"name":"mobileemova"}]'

# Encabezados HTTP estándar para evitar bloqueos de User-Agent genéricos
HEADERS_SUBTE = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://emova.com.ar/",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}

HEADERS_SOFSE = {
    "User-Agent": "okhttp/4.9.2",
    "Accept": "application/json",
    "Referer": "https://api-servicios.sofse.gob.ar/",
    "Accept-Language": "es-AR,es;q=0.9",
}

HEADERS_GCBA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

_SOFSE_CIPHER_STEP_0 = (
    ("a", "#t"),
    ("e", "#x"),
    ("i", "#f"),
    ("o", "#l"),
    ("u", "#7"),
    ("=", "#g"),
)
_SOFSE_CIPHER_STEP_1 = (
    ("a", "#j"),
    ("e", "#p"),
    ("i", "#w"),
    ("o", "#8"),
    ("u", "#0"),
    ("=", "#v"),
)


def _format_frequency(raw_freq: Any) -> str | int | None:
    """Normaliza la frecuencia reportada en segundos."""
    if raw_freq in (None, ""):
        return None
    try:
        secs = int(raw_freq)
        if secs <= 0:
            return None
        mins, rem = divmod(secs, 60)
        if rem == 0:
            return f"{mins} min"
        return f"{mins} min {rem} s"
    except (ValueError, TypeError):
        return str(raw_freq)


def _generate_sofse_credentials() -> dict[str, str]:
    """Genera las credenciales temporales requeridas por la API de SOFSE."""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d") + "sofse"
    username = base64.b64encode(date_str.encode("utf-8")).decode("utf-8")

    step1 = base64.b64encode(username.encode("utf-8")).decode("utf-8")
    for src, dst in _SOFSE_CIPHER_STEP_0:
        step1 = step1.replace(src, dst)
    step1 = step1[::-1]

    step2 = base64.b64encode(step1.encode("utf-8")).decode("utf-8")
    for src, dst in _SOFSE_CIPHER_STEP_1:
        step2 = step2.replace(src, dst)
    step2 = quote(step2[::-1], safe="-_.!~*'()")

    return {"username": username, "password": step2}


class SubteDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinador para la red de Subte y Premetro (Emova)."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_subte",
            update_interval=SCAN_INTERVAL_SUBTE,
        )
        self.session = async_get_clientsession(hass)
        self._base_interval: timedelta = SCAN_INTERVAL_SUBTE
        self._max_interval: timedelta = timedelta(minutes=15)
        self._consecutive_errors: int = 0

    def _apply_backoff(self, is_rate_limit: bool = False) -> None:
        """Incrementa progresivamente el intervalo de sondeo ante errores o 429."""
        self._consecutive_errors += 1
        if is_rate_limit or self._consecutive_errors >= 2:
            multiplier = min(2 ** (self._consecutive_errors - 1), 5)
            new_interval = min(self._base_interval * multiplier, self._max_interval)
            if self.update_interval != new_interval:
                self.update_interval = new_interval
                _LOGGER.warning(
                    "%s: Servidor con alta carga o límite de tasa (%s fallos consecutivos). "
                    "Próximo sondeo en %s",
                    self.name,
                    self._consecutive_errors,
                    new_interval,
                )

    def _reset_backoff(self) -> None:
        """Restaura el intervalo habitual tras una consulta exitosa."""
        if self._consecutive_errors > 0 or self.update_interval != self._base_interval:
            self._consecutive_errors = 0
            self.update_interval = self._base_interval

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            data = await self._fetch_from_signalr()
            self._reset_backoff()
            return data
        except (ClientError, TimeoutError, UpdateFailed, ValueError, KeyError) as signalr_err:
            _LOGGER.debug(
                "SignalR Emova no disponible (%s), intentando endpoint JSON directo",
                signalr_err,
            )
            try:
                data = await self._fetch_from_json_endpoint()
                self._reset_backoff()
                return data
            except UpdateFailed as err:
                is_429 = "429" in str(err)
                self._apply_backoff(is_rate_limit=is_429)
                raise
            except (ClientError, TimeoutError) as net_err:
                self._apply_backoff(is_rate_limit=False)
                raise UpdateFailed(f"Fallo de conexión al consultar Subte: {net_err}") from net_err

    async def _fetch_from_signalr(self) -> dict[str, dict[str, Any]]:
        """Obtiene el estado en tiempo real desde el hub SignalR de Emova."""
        params_base = {
            "clientProtocol": "2.1",
            "connectionData": SIGNALR_CONNECTION_DATA,
        }
        async with self.session.get(
            f"{URL_SUBTE_SIGNALR}/negotiate",
            headers=HEADERS_SUBTE,
            params=params_base,
            timeout=REQUEST_TIMEOUT,
        ) as resp:
            if resp.status == 429:
                raise UpdateFailed("Error HTTP 429 (Too Many Requests) en negotiate de Subte")
            if resp.status != 200:
                raise UpdateFailed(f"Error HTTP {resp.status} en negotiate de Subte")
            neg_data = await resp.json(content_type=None)

        token = neg_data.get("ConnectionToken")
        if not token:
            raise UpdateFailed("Token de conexión SignalR no recibido")

        lp_params = {
            **params_base,
            "transport": "longPolling",
            "connectionToken": token,
        }
        async with self.session.get(
            f"{URL_SUBTE_SIGNALR}/connect",
            headers=HEADERS_SUBTE,
            params=lp_params,
            timeout=REQUEST_TIMEOUT,
        ) as resp:
            if resp.status == 429:
                raise UpdateFailed("Error HTTP 429 (Too Many Requests) en connect de Subte")
            if resp.status != 200:
                raise UpdateFailed(f"Error HTTP {resp.status} en connect de Subte")
            conn_data = await resp.json(content_type=None)

        messages = conn_data.get("M", [])
        if not messages:
            msg_id = conn_data.get("C", "")
            async with self.session.get(
                f"{URL_SUBTE_SIGNALR}/start",
                headers=HEADERS_SUBTE,
                params=lp_params,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status == 429:
                    raise UpdateFailed("Error HTTP 429 (Too Many Requests) en start de Subte")
                if resp.status != 200:
                    raise UpdateFailed(f"Error HTTP {resp.status} en start de Subte")

            poll_params = {**lp_params, "messageId": msg_id}
            async with self.session.get(
                f"{URL_SUBTE_SIGNALR}/poll",
                headers=HEADERS_SUBTE,
                params=poll_params,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status == 429:
                    raise UpdateFailed("Error HTTP 429 (Too Many Requests) en poll de Subte")
                if resp.status != 200:
                    raise UpdateFailed(f"Error HTTP {resp.status} en poll de Subte")
                poll_data = await resp.json(content_type=None)
                messages = poll_data.get("M", [])

        for msg in messages:
            if msg.get("M") == "estadoLineasMobile":
                args = msg.get("A", [])
                if args:
                    payload = json.loads(args[0]) if isinstance(args[0], str) else args[0]
                    return self._normalize_emova_payload(payload)

        raise UpdateFailed("No se recibió payload estadoLineasMobile desde Emova")

    async def _fetch_from_json_endpoint(self) -> dict[str, dict[str, Any]]:
        """Obtiene y normaliza datos desde el endpoint JSON estándar."""
        async with self.session.get(
            URL_SUBTE_STATUS,
            headers=HEADERS_SUBTE,
            timeout=REQUEST_TIMEOUT,
        ) as resp:
            if resp.status == 429:
                raise UpdateFailed("Error HTTP 429 (Too Many Requests) al consultar Subte")
            if resp.status != 200:
                raise UpdateFailed(f"Error HTTP {resp.status} al consultar Subte")
            data = await resp.json(content_type=None)
            return self._normalize_emova_payload(data)

    def _normalize_emova_payload(self, data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Normaliza tanto el formato SignalR ('lines') como el JSON ('lineas')."""
        normalized: dict[str, dict[str, Any]] = {}

        if "lines" in data:
            for item in data.get("lines", []):
                raw_name = str(item.get("LineName", "")).strip().upper()
                line_id = "Premetro" if raw_name in ("P", "PREMETRO") else raw_name
                if raw_name == "U":
                    line_id = "Urquiza"
                classified = classify_service_status(item.get("LineStatus", ""))
                normalized[line_id] = {
                    "estado": classified["estado"],
                    "categoria": classified["categoria"],
                    "alerta_operativa": classified["alerta_operativa"],
                    "mensaje": classified["mensaje"],
                    "frecuencia": _format_frequency(item.get("LineFrequency")),
                    "actualizado": f"{data.get('date', '')} {data.get('time', '')}".strip(),
                }
            return normalized

        for item in data.get("lineas", []):
            raw_name = str(item.get("nombre", "")).strip()
            line_id = "Premetro" if raw_name.upper() in ("P", "PREMETRO") else raw_name.upper()
            classified = classify_service_status(
                item.get("estado", "Desconocido"),
                item.get("mensaje", ""),
            )
            normalized[line_id] = {
                "estado": classified["estado"],
                "categoria": classified["categoria"],
                "alerta_operativa": classified["alerta_operativa"],
                "mensaje": classified["mensaje"],
                "frecuencia": item.get("frecuencia", None),
            }
        return normalized


class TrenesDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinador para Trenes Argentinos / SOFSE."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_trenes",
            update_interval=SCAN_INTERVAL_TRENES,
        )
        self.session = async_get_clientsession(hass)
        self._token: str | None = None
        self._token_exp: float = 0.0
        self._base_interval: timedelta = SCAN_INTERVAL_TRENES
        self._max_interval: timedelta = timedelta(minutes=20)
        self._consecutive_errors: int = 0

    def _apply_backoff(self, is_rate_limit: bool = False) -> None:
        """Incrementa progresivamente el intervalo de sondeo ante errores o 429."""
        self._consecutive_errors += 1
        if is_rate_limit or self._consecutive_errors >= 2:
            multiplier = min(2 ** (self._consecutive_errors - 1), 4)
            new_interval = min(self._base_interval * multiplier, self._max_interval)
            if self.update_interval != new_interval:
                self.update_interval = new_interval
                _LOGGER.warning(
                    "%s: Servidor con alta carga o límite de tasa (%s fallos consecutivos). "
                    "Próximo sondeo en %s",
                    self.name,
                    self._consecutive_errors,
                    new_interval,
                )

    def _reset_backoff(self) -> None:
        """Restaura el intervalo habitual tras una consulta exitosa."""
        if self._consecutive_errors > 0 or self.update_interval != self._base_interval:
            self._consecutive_errors = 0
            self.update_interval = self._base_interval

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            data = await self._fetch_from_sofse_api()
            self._reset_backoff()
            return data
        except (ClientError, TimeoutError, UpdateFailed, ValueError, KeyError) as sofse_err:
            _LOGGER.debug(
                "API SOFSE v1 con autenticación falló (%s), intentando endpoint alternativo",
                sofse_err,
            )
            try:
                data = await self._fetch_from_fallback_endpoint()
                self._reset_backoff()
                return data
            except UpdateFailed as err:
                is_429 = "429" in str(err)
                self._apply_backoff(is_rate_limit=is_429)
                raise
            except (ClientError, TimeoutError) as net_err:
                self._apply_backoff(is_rate_limit=False)
                raise UpdateFailed(f"Fallo de conexión al consultar Trenes: {net_err}") from net_err

    async def _ensure_sofse_token(self, force_refresh: bool = False) -> str:
        """Obtiene o renueva el token JWT de SOFSE."""
        now = time.time()
        if not force_refresh and self._token and now < (self._token_exp - 60):
            return self._token

        creds = _generate_sofse_credentials()
        headers = {**HEADERS_SOFSE, "Content-Type": "application/json"}
        async with self.session.post(
            f"{URL_SOFSE_API_BASE}/auth/authorize",
            headers=headers,
            json=creds,
            timeout=REQUEST_TIMEOUT,
        ) as resp:
            if resp.status == 429:
                self._apply_backoff(is_rate_limit=True)
                raise UpdateFailed("Error HTTP 429 (Too Many Requests) al autenticar con SOFSE")
            if resp.status != 200:
                raise UpdateFailed(f"Error HTTP {resp.status} al autenticar con SOFSE")
            auth_data = await resp.json(content_type=None)

        token = auth_data.get("token")
        if not token:
            raise UpdateFailed("No se recibió token desde SOFSE")

        self._token = token
        try:
            payload_b64 = token.split(".")[1]
            padding = "=" * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
            self._token_exp = float(payload.get("exp", now + 3600))
        except (IndexError, ValueError, TypeError):
            self._token_exp = now + 3600

        return token

    async def _sofse_get(self, path: str) -> Any:
        """Realiza un GET autenticado contra la API de SOFSE."""
        token = await self._ensure_sofse_token()
        headers = {**HEADERS_SOFSE, "Authorization": token}
        async with self.session.get(
            f"{URL_SOFSE_API_BASE}{path}",
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        ) as resp:
            if resp.status in (401, 403):
                # Token expirado o rechazado: forzar renovación y reintentar una única vez
                self._token = None
                token = await self._ensure_sofse_token(force_refresh=True)
                retry_headers = {**HEADERS_SOFSE, "Authorization": token}
                async with self.session.get(
                    f"{URL_SOFSE_API_BASE}{path}",
                    headers=retry_headers,
                    timeout=REQUEST_TIMEOUT,
                ) as retry_resp:
                    if retry_resp.status == 429:
                        self._apply_backoff(is_rate_limit=True)
                        raise UpdateFailed(f"Error HTTP 429 (Too Many Requests) en {path}")
                    if retry_resp.status != 200:
                        raise UpdateFailed(
                            f"Error HTTP {retry_resp.status} al reintentar {path}"
                        )
                    return await retry_resp.json(content_type=None)

            if resp.status == 429:
                self._apply_backoff(is_rate_limit=True)
                raise UpdateFailed(f"Error HTTP 429 (Too Many Requests) al consultar {path}")
            if resp.status != 200:
                raise UpdateFailed(f"Error HTTP {resp.status} al consultar {path}")
            return await resp.json(content_type=None)

    async def _fetch_from_sofse_api(self) -> dict[str, dict[str, Any]]:
        """Consulta gerencias y ramales de SOFSE y construye el estado por línea."""
        gerencias = await self._sofse_get("/infraestructura/gerencias")
        ramales = await self._sofse_get("/infraestructura/ramales")

        normalized: dict[str, dict[str, Any]] = {
            line_name: {
                "estado": "Normal",
                "categoria": STATUS_CATEGORY_NORMAL,
                "alerta_operativa": False,
                "mensaje": "",
                "ramales": [],
            }
            for line_name in TRENES_LINES
        }

        raw_status_by_line: dict[str, str] = {}

        if isinstance(gerencias, list):
            for ger in gerencias:
                ger_id = ger.get("id")
                line_name = SOFSE_GERENCIA_MAP.get(ger_id) or str(ger.get("nombre", "")).strip()
                if not line_name:
                    continue

                alertas_ger = [
                    a.get("contenido", "").strip()
                    for a in (ger.get("alerta") or [])
                    if isinstance(a, dict) and a.get("habilitado", 1) and a.get("contenido")
                ]
                estado_obj = ger.get("estado") or {}
                estado_msg = (
                    estado_obj.get("mensaje", "Normal")
                    if isinstance(estado_obj, dict)
                    else str(estado_obj)
                )
                raw_status_by_line[line_name] = estado_msg

                normalized.setdefault(
                    line_name,
                    {
                        "estado": "Normal",
                        "categoria": STATUS_CATEGORY_NORMAL,
                        "alerta_operativa": False,
                        "mensaje": "",
                        "ramales": [],
                    },
                )
                if alertas_ger:
                    normalized[line_name]["mensaje"] = " | ".join(alertas_ger)

        if isinstance(ramales, list):
            for ramal in ramales:
                if not ramal.get("publico", True):
                    continue
                ger_id = ramal.get("id_gerencia")
                line_name = SOFSE_GERENCIA_MAP.get(ger_id)
                if not line_name:
                    continue

                operativo = ramal.get("operativo", 1) == 1
                alertas_ramal = [
                    a.get("contenido", "").strip()
                    for a in (ramal.get("alerta") or [])
                    if isinstance(a, dict) and a.get("habilitado", 1) and a.get("contenido")
                ]
                ramal_estado = "Normal" if operativo else "Sin servicio"
                if alertas_ramal and operativo:
                    ramal_estado = truncate_state(" | ".join(alertas_ramal), 120)

                ramal_info = {
                    "nombre": ramal.get("nombre", ""),
                    "estado": ramal_estado,
                    "operativo": operativo,
                    "es_electrico": bool(ramal.get("es_electrico", 0)),
                    "alerta": " | ".join(alertas_ramal) if alertas_ramal else "",
                }
                normalized.setdefault(
                    line_name,
                    {
                        "estado": "Normal",
                        "categoria": STATUS_CATEGORY_NORMAL,
                        "alerta_operativa": False,
                        "mensaje": "",
                        "ramales": [],
                    },
                )
                normalized[line_name]["ramales"].append(ramal_info)

                if alertas_ramal and not normalized[line_name]["mensaje"]:
                    normalized[line_name]["mensaje"] = (
                        f"{ramal_info['nombre']}: {ramal_info['alerta']}"
                    )

        # Clasificar el estado general y mostrar el motivo directo en "estado"
        for line_name, info in normalized.items():
            ramales_list = info["ramales"]
            if ramales_list and all(not r["operativo"] for r in ramales_list):
                info["estado"] = (
                    truncate_state(f"Sin servicio: {info['mensaje']}")
                    if info["mensaje"]
                    else "Interrumpido"
                )
                info["categoria"] = STATUS_CATEGORY_INTERRUPTED
                info["alerta_operativa"] = True
            else:
                raw_st = raw_status_by_line.get(line_name, "Normal")
                classified = classify_service_status(raw_st, info["mensaje"])
                info["estado"] = classified["estado"]
                info["categoria"] = classified["categoria"]
                info["alerta_operativa"] = classified["alerta_operativa"]

        return normalized

    async def _fetch_from_fallback_endpoint(self) -> dict[str, dict[str, Any]]:
        """Obtiene datos desde el endpoint JSON directo (formato de especificación)."""
        async with self.session.get(
            URL_TRENES_STATUS,
            headers=HEADERS_SOFSE,
            timeout=REQUEST_TIMEOUT,
        ) as resp:
            if resp.status == 429:
                raise UpdateFailed("Error HTTP 429 (Too Many Requests) al consultar Trenes")
            if resp.status != 200:
                raise UpdateFailed(f"Error HTTP {resp.status} al consultar Trenes")
            data = await resp.json(content_type=None)

            normalized: dict[str, dict[str, Any]] = {}
            for linea in data.get("lineas", []):
                nombre = linea.get("nombre", "").strip()
                classified = classify_service_status(
                    linea.get("estado", "Desconocido"),
                    linea.get("mensaje", ""),
                )
                normalized[nombre] = {
                    "estado": classified["estado"],
                    "categoria": classified["categoria"],
                    "alerta_operativa": classified["alerta_operativa"],
                    "mensaje": classified["mensaje"],
                    "ramales": linea.get("ramales", []),
                }
            return normalized


class StationsDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinador para próximos arribos y estado de estaciones cercanas/seleccionadas."""

    def __init__(
        self,
        hass: HomeAssistant,
        station_keys: list[str],
        subte_coord: SubteDataUpdateCoordinator | None = None,
        trenes_coord: TrenesDataUpdateCoordinator | None = None,
        gcba_client_id: str | None = None,
        gcba_client_secret: str | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_stations",
            update_interval=SCAN_INTERVAL_STATIONS,
        )
        self.session = async_get_clientsession(hass)
        self.station_keys = station_keys
        self.subte_coord = subte_coord
        self.trenes_coord = trenes_coord
        self.gcba_client_id = (gcba_client_id or "").strip()
        self.gcba_client_secret = (gcba_client_secret or "").strip()
        self._base_interval: timedelta = SCAN_INTERVAL_STATIONS
        self._max_interval: timedelta = timedelta(minutes=5)
        self._consecutive_errors: int = 0

    def _apply_backoff(self, is_rate_limit: bool = False) -> None:
        """Incrementa progresivamente el intervalo de sondeo ante errores o 429."""
        self._consecutive_errors += 1
        if is_rate_limit or self._consecutive_errors >= 2:
            multiplier = min(2 ** (self._consecutive_errors - 1), 5)
            new_interval = min(self._base_interval * multiplier, self._max_interval)
            if self.update_interval != new_interval:
                self.update_interval = new_interval
                _LOGGER.warning(
                    "%s: Servidor con alta carga o límite de tasa (%s fallos consecutivos). "
                    "Próximo sondeo en %s",
                    self.name,
                    self._consecutive_errors,
                    new_interval,
                )

    def _reset_backoff(self) -> None:
        """Restaura el intervalo habitual tras una consulta exitosa."""
        if self._consecutive_errors > 0 or self.update_interval != self._base_interval:
            self._consecutive_errors = 0
            self.update_interval = self._base_interval

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        if not self.station_keys:
            return results

        home_lat = getattr(self.hass.config, "latitude", None)
        home_lon = getattr(self.hass.config, "longitude", None)

        tren_stations: list[dict[str, Any]] = []
        subte_stations: list[dict[str, Any]] = []

        for key in self.station_keys:
            st = get_station_by_key(key)
            if not st:
                continue
            if st["network"] == "tren":
                tren_stations.append(st)
            elif st["network"] == "subte":
                subte_stations.append(st)

        had_rate_limit = False
        any_success = False

        # 1. Consultar arribos de estaciones de Tren en paralelo
        if tren_stations:
            tasks = [
                self._fetch_tren_station(st, home_lat, home_lon)
                for st in tren_stations
            ]
            tren_outcomes = await asyncio.gather(*tasks, return_exceptions=True)
            for st, outcome in zip(tren_stations, tren_outcomes):
                if isinstance(outcome, dict):
                    results[st["key"]] = outcome
                    any_success = True
                else:
                    if "429" in str(outcome):
                        had_rate_limit = True
                    _LOGGER.debug(
                        "Error al consultar arribos de estación %s: %s",
                        st["name"],
                        outcome,
                    )
                    results[st["key"]] = {
                        "estado": "Sin datos de arribos",
                        "arribos": [],
                        "estacion_cerrada": False,
                        "distancia_km": (
                            haversine_km(home_lat, home_lon, st["lat"], st["lon"])
                            if home_lat is not None and home_lon is not None
                            else None
                        ),
                    }

        # 2. Consultar estaciones de Subte (con API GCBA opcional o cruce con Emova)
        gcba_forecast: dict[str, Any] | None = None
        if subte_stations and self.gcba_client_id and self.gcba_client_secret:
            gcba_forecast = await self._fetch_gcba_subte_forecast()

        for st in subte_stations:
            results[st["key"]] = self._build_subte_station_status(
                st, home_lat, home_lon, gcba_forecast
            )
            any_success = True

        if had_rate_limit:
            self._apply_backoff(is_rate_limit=True)
        elif any_success:
            self._reset_backoff()

        return results

    async def _fetch_tren_station(
        self,
        station: dict[str, Any],
        home_lat: float | None,
        home_lon: float | None,
    ) -> dict[str, Any]:
        """Consulta /v1/arribos/estacion/{id} en SOFSE y resume próximos trenes."""
        dist_km = (
            haversine_km(home_lat, home_lon, station["lat"], station["lon"])
            if home_lat is not None and home_lon is not None
            else None
        )

        line_data = (
            (self.trenes_coord.data or {}).get(station["line"], {})
            if self.trenes_coord
            else {}
        )
        line_msg = line_data.get("mensaje", "")
        closed = is_station_affected_by_message(station["name"], line_msg)

        url = f"{URL_SOFSE_ARRIBOS}/{station['id']}"
        async with self.session.get(
            url,
            headers=HEADERS_SOFSE,
            timeout=REQUEST_TIMEOUT,
        ) as resp:
            if resp.status == 429:
                raise UpdateFailed(f"HTTP 429 (Too Many Requests) en arribos de estación {station['id']}")
            if resp.status != 200:
                raise UpdateFailed(
                    f"HTTP {resp.status} en arribos de estación {station['id']}"
                )
            data = await resp.json(content_type=None)

        upcoming: list[dict[str, Any]] = []
        for item in data.get("results") or []:
            arribo = item.get("arribo") or {}
            servicio = item.get("servicio") or {}
            if servicio.get("cancelacion"):
                continue

            segundos = arribo.get("segundos")
            if segundos is None:
                continue
            try:
                sec_int = int(segundos)
            except (ValueError, TypeError):
                continue

            if sec_int < -30:
                continue

            mins = max(0, round(sec_int / 60))
            hasta_est = ((servicio.get("hasta") or {}).get("estacion") or {}).get(
                "nombre"
            )
            cab_final = ((servicio.get("ramal") or {}).get("cabeceraFinal") or {}).get(
                "nombre"
            )
            destino = (hasta_est or cab_final or "Destino").strip()
            ramal_nombre = ((servicio.get("ramal") or {}).get("nombre") or "").strip()
            anden = ((arribo.get("anden") or {}).get("nombre") or "").strip()
            estado_form = (
                ((servicio.get("desde") or {}).get("estado") or {}).get("nombre")
                or "En circulación"
            )
            llegada = arribo.get("llegada") or {}
            salida = arribo.get("salida") or {}
            hora_iso = (
                llegada.get("estimada")
                or salida.get("estimada")
                or llegada.get("programada")
                or salida.get("programada")
            )

            upcoming.append(
                {
                    "destino": destino,
                    "ramal": ramal_nombre,
                    "minutos": mins,
                    "segundos": sec_int,
                    "anden": anden or None,
                    "estado_formacion": estado_form,
                    "hora_estimada": hora_iso,
                }
            )

        upcoming.sort(key=lambda x: x["segundos"])

        # Agrupar los próximos tiempos por destino para mostrar un resumen claro
        by_dest: dict[str, list[str]] = {}
        for arr in upcoming:
            dest = arr["destino"]
            by_dest.setdefault(dest, [])
            if len(by_dest[dest]) < 2:
                label = "En andén" if arr["minutos"] == 0 else f"{arr['minutos']} min"
                by_dest[dest].append(label)

        if closed:
            summary_state = truncate_state(f"Estación cerrada / obras: {line_msg}")
        elif by_dest:
            parts = [
                f"{dest}: {', '.join(times)}" for dest, times in by_dest.items()
            ]
            summary_state = truncate_state(" | ".join(parts))
        else:
            summary_state = "Sin próximos arribos"

        return {
            "estado": summary_state,
            "arribos": upcoming[:8],
            "estacion_cerrada": closed,
            "distancia_km": dist_km,
            "alerta_linea": line_msg,
        }

    async def _fetch_gcba_subte_forecast(self) -> dict[str, Any] | None:
        """Consulta opcionalmente el endpoint GTFS-RT de Subtes de GCBA."""
        params = {
            "client_id": self.gcba_client_id,
            "client_secret": self.gcba_client_secret,
        }
        try:
            async with self.session.get(
                URL_GCBA_SUBTE_FORECAST,
                headers=HEADERS_GCBA,
                params=params,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status == 429:
                    self._apply_backoff(is_rate_limit=True)
                    return None
                if resp.status != 200:
                    _LOGGER.debug(
                        "API GCBA Subte devolvió HTTP %s", resp.status
                    )
                    return None
                return await resp.json(content_type=None)
        except (ClientError, TimeoutError, ValueError) as err:
            _LOGGER.debug("No se pudo consultar API GCBA Subte: %s", err)
            return None

    def _build_subte_station_status(
        self,
        station: dict[str, Any],
        home_lat: float | None,
        home_lon: float | None,
        gcba_forecast: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Construye el estado de una estación de Subte (cruce con Emova + GCBA opcional)."""
        dist_km = (
            haversine_km(home_lat, home_lon, station["lat"], station["lon"])
            if home_lat is not None and home_lon is not None
            else None
        )
        line_data = (
            (self.subte_coord.data or {}).get(station["line"], {})
            if self.subte_coord
            else {}
        )
        line_state = line_data.get("estado", "Normal")
        line_msg = line_data.get("mensaje", "")
        freq = line_data.get("frecuencia")
        closed = is_station_affected_by_message(station["name"], line_msg)

        arribos_gcba: list[dict[str, Any]] = []
        if gcba_forecast and isinstance(gcba_forecast, dict):
            arribos_gcba = self._extract_gcba_arrivals_for_station(
                station, gcba_forecast
            )

        if closed:
            state_str = truncate_state(f"Cerrada: {line_msg}")
        elif arribos_gcba:
            parts = [f"{a['destino']}: {a['minutos']} min" for a in arribos_gcba[:2]]
            state_str = truncate_state(" | ".join(parts))
        elif line_data.get("alerta_operativa"):
            state_str = truncate_state(line_state)
        elif freq:
            state_str = f"Operativa (cada {freq})"
        else:
            state_str = "Operativa"

        return {
            "estado": state_str,
            "arribos": arribos_gcba,
            "estacion_cerrada": closed,
            "frecuencia_linea": freq,
            "alerta_linea": line_msg,
            "distancia_km": dist_km,
        }

    def _extract_gcba_arrivals_for_station(
        self, station: dict[str, Any], forecast: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Extrae los próximos subtes de la respuesta forecastGTFS de GCBA para una estación."""
        arrivals: list[dict[str, Any]] = []
        norm_st_name = normalize_text(station["name"])
        target_line = f"Linea{station['line']}".lower()
        now = time.time()

        entities = forecast.get("Entity") or forecast.get("entity") or []
        for ent in entities:
            linea_obj = ent.get("Linea") or ent.get("linea") or {}
            route_id = str(
                linea_obj.get("Route_Id") or linea_obj.get("route_id") or ""
            ).lower()
            if target_line not in route_id:
                continue

            dest_name = str(
                linea_obj.get("Direction_Name")
                or linea_obj.get("direction_name")
                or f"Sentido {linea_obj.get('Direction_Id', '')}"
            ).strip()
            estaciones = linea_obj.get("Estaciones") or linea_obj.get("estaciones") or []
            for est in estaciones:
                stop_name = normalize_text(
                    str(est.get("stop_name") or est.get("Stop_Name") or "")
                )
                if not stop_name or (
                    stop_name not in norm_st_name and norm_st_name not in stop_name
                ):
                    continue
                arr_obj = est.get("arrival") or est.get("Arrival") or {}
                arr_time = arr_obj.get("time")
                delay = arr_obj.get("delay", 0)
                if arr_time:
                    try:
                        secs = int(float(arr_time) - now)
                        if secs >= -20:
                            arrivals.append(
                                {
                                    "destino": dest_name,
                                    "minutos": max(0, round(secs / 60)),
                                    "segundos": secs,
                                    "demora_s": delay,
                                }
                            )
                    except (ValueError, TypeError):
                        continue

        arrivals.sort(key=lambda x: x["segundos"])
        return arrivals
