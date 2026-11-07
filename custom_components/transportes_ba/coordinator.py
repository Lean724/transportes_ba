"""Coordinadores de actualización para Transportes de Buenos Aires."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import logging
import time
from typing import Any
from urllib.parse import quote

from aiohttp import ClientError, ClientTimeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    SCAN_INTERVAL_SUBTE,
    SCAN_INTERVAL_TRENES,
    SOFSE_GERENCIA_MAP,
    TRENES_LINES,
    URL_SOFSE_API_BASE,
    URL_SUBTE_SIGNALR,
    URL_SUBTE_STATUS,
    URL_TRENES_STATUS,
)

_LOGGER = logging.getLogger(__name__)
REQUEST_TIMEOUT = ClientTimeout(total=15)

SIGNALR_CONNECTION_DATA = '[{"name":"mobileemova"}]'

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


def _classify_subte_status(raw_status: str) -> tuple[str, str]:
    """Separa el estado operativo corto y el mensaje detallado de Subte."""
    text = (raw_status or "").strip()
    if not text:
        return "Desconocido", ""
    lower = text.lower()
    if lower in ("normal", "servicio normal", "a tiempo"):
        return "Normal", ""
    if any(k in lower for k in ("interrumpid", "suspendid", "sin servicio", "cancelad")):
        return "Interrumpido", text
    if any(k in lower for k in ("limitad", "recorrido reducido", "servicio corto")):
        return "Servicio limitado", text
    if "demora" in lower:
        return "Demoras", text
    return "Con modificaciones", text


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

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            return await self._fetch_from_signalr()
        except (ClientError, TimeoutError, UpdateFailed, ValueError, KeyError) as signalr_err:
            _LOGGER.debug(
                "SignalR Emova no disponible (%s), intentando endpoint JSON directo",
                signalr_err,
            )
            return await self._fetch_from_json_endpoint()

    async def _fetch_from_signalr(self) -> dict[str, dict[str, Any]]:
        """Obtiene el estado en tiempo real desde el hub SignalR de Emova."""
        params_base = {
            "clientProtocol": "2.1",
            "connectionData": SIGNALR_CONNECTION_DATA,
        }
        async with self.session.get(
            f"{URL_SUBTE_SIGNALR}/negotiate",
            params=params_base,
            timeout=REQUEST_TIMEOUT,
        ) as resp:
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
            params=lp_params,
            timeout=REQUEST_TIMEOUT,
        ) as resp:
            if resp.status != 200:
                raise UpdateFailed(f"Error HTTP {resp.status} en connect de Subte")
            conn_data = await resp.json(content_type=None)

        messages = conn_data.get("M", [])
        if not messages:
            msg_id = conn_data.get("C", "")
            async with self.session.get(
                f"{URL_SUBTE_SIGNALR}/start",
                params=lp_params,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"Error HTTP {resp.status} en start de Subte")

            poll_params = {**lp_params, "messageId": msg_id}
            async with self.session.get(
                f"{URL_SUBTE_SIGNALR}/poll",
                params=poll_params,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
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
        try:
            async with self.session.get(URL_SUBTE_STATUS, timeout=REQUEST_TIMEOUT) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"Error HTTP {resp.status} al consultar Subte")
                data = await resp.json(content_type=None)
                return self._normalize_emova_payload(data)
        except (ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Fallo de conexión al consultar Subte: {err}") from err

    def _normalize_emova_payload(self, data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Normaliza tanto el formato SignalR ('lines') como el JSON ('lineas')."""
        normalized: dict[str, dict[str, Any]] = {}

        if "lines" in data:
            for item in data.get("lines", []):
                raw_name = str(item.get("LineName", "")).strip().upper()
                line_id = "Premetro" if raw_name in ("P", "PREMETRO") else raw_name
                if raw_name == "U":
                    line_id = "Urquiza"
                estado, mensaje = _classify_subte_status(item.get("LineStatus", ""))
                normalized[line_id] = {
                    "estado": estado,
                    "mensaje": mensaje,
                    "frecuencia": _format_frequency(item.get("LineFrequency")),
                    "actualizado": f"{data.get('date', '')} {data.get('time', '')}".strip(),
                }
            return normalized

        for item in data.get("lineas", []):
            raw_name = str(item.get("nombre", "")).strip()
            line_id = "Premetro" if raw_name.upper() in ("P", "PREMETRO") else raw_name.upper()
            normalized[line_id] = {
                "estado": item.get("estado", "Desconocido"),
                "mensaje": item.get("mensaje", ""),
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

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            return await self._fetch_from_sofse_api()
        except (ClientError, TimeoutError, UpdateFailed, ValueError, KeyError) as sofse_err:
            _LOGGER.debug(
                "API SOFSE v1 con autenticación falló (%s), intentando endpoint alternativo",
                sofse_err,
            )
            return await self._fetch_from_fallback_endpoint()

    async def _ensure_sofse_token(self, force_refresh: bool = False) -> str:
        """Obtiene o renueva el token JWT de SOFSE."""
        now = time.time()
        if not force_refresh and self._token and now < (self._token_exp - 60):
            return self._token

        creds = _generate_sofse_credentials()
        async with self.session.post(
            f"{URL_SOFSE_API_BASE}/auth/authorize",
            json=creds,
            timeout=REQUEST_TIMEOUT,
        ) as resp:
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
        headers = {"Authorization": token, "Accept": "application/json"}
        async with self.session.get(
            f"{URL_SOFSE_API_BASE}{path}",
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        ) as resp:
            if resp.status in (401, 403):
                token = await self._ensure_sofse_token(force_refresh=True)
                headers["Authorization"] = token
                async with self.session.get(
                    f"{URL_SOFSE_API_BASE}{path}",
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                ) as retry_resp:
                    if retry_resp.status != 200:
                        raise UpdateFailed(
                            f"Error HTTP {retry_resp.status} al consultar {path}"
                        )
                    return await retry_resp.json(content_type=None)
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
                "mensaje": "",
                "ramales": [],
            }
            for line_name in TRENES_LINES
        }

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

                normalized.setdefault(
                    line_name,
                    {"estado": "Normal", "mensaje": "", "ramales": []},
                )
                if alertas_ger:
                    normalized[line_name]["mensaje"] = " | ".join(alertas_ger)
                if estado_msg and estado_msg.lower() not in ("alertas por ramal", "normal"):
                    normalized[line_name]["estado"] = estado_msg

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
                    ramal_estado = "Con alerta"

                ramal_info = {
                    "nombre": ramal.get("nombre", ""),
                    "estado": ramal_estado,
                    "operativo": operativo,
                    "es_electrico": bool(ramal.get("es_electrico", 0)),
                    "alerta": " | ".join(alertas_ramal) if alertas_ramal else "",
                }
                normalized.setdefault(
                    line_name,
                    {"estado": "Normal", "mensaje": "", "ramales": []},
                )
                normalized[line_name]["ramales"].append(ramal_info)

                if alertas_ramal and not normalized[line_name]["mensaje"]:
                    normalized[line_name]["mensaje"] = (
                        f"{ramal_info['nombre']}: {ramal_info['alerta']}"
                    )

        # Determinar el estado general de cada línea a partir de alertas/ramales
        for line_name, info in normalized.items():
            ramales_list = info["ramales"]
            if ramales_list and all(not r["operativo"] for r in ramales_list):
                info["estado"] = "Interrumpido"
            elif any(r["alerta"] for r in ramales_list) or info["mensaje"]:
                msg_lower = info["mensaje"].lower()
                if any(k in msg_lower for k in ("interrumpid", "suspendid", "cancelad")):
                    info["estado"] = "Interrumpido"
                elif any(k in msg_lower for k in ("limitad", "reducid", "corto")):
                    info["estado"] = "Servicio limitado"
                elif "demora" in msg_lower:
                    info["estado"] = "Demoras"
                elif info["estado"] == "Normal":
                    info["estado"] = "Alerta activa"

        return normalized

    async def _fetch_from_fallback_endpoint(self) -> dict[str, dict[str, Any]]:
        """Obtiene datos desde el endpoint JSON directo (formato de especificación)."""
        try:
            async with self.session.get(URL_TRENES_STATUS, timeout=REQUEST_TIMEOUT) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"Error HTTP {resp.status} al consultar Trenes")
                data = await resp.json(content_type=None)

                normalized: dict[str, dict[str, Any]] = {}
                for linea in data.get("lineas", []):
                    nombre = linea.get("nombre", "").strip()
                    normalized[nombre] = {
                        "estado": linea.get("estado", "Desconocido"),
                        "mensaje": linea.get("mensaje", ""),
                        "ramales": linea.get("ramales", []),
                    }
                return normalized
        except (ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Fallo de conexión al consultar Trenes: {err}") from err
