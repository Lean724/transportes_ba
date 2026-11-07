"""Clasificación inteligente de estados, alertas y cierres de estación."""
from __future__ import annotations

import unicodedata

from .const import (
    OPERATIONAL_PROBLEM_CATEGORIES,
    STATUS_CATEGORY_ADVISORY,
    STATUS_CATEGORY_DELAY,
    STATUS_CATEGORY_INTERRUPTED,
    STATUS_CATEGORY_LIMITED,
    STATUS_CATEGORY_NORMAL,
    STATUS_CATEGORY_STATION_CLOSED,
    STATUS_CATEGORY_UNKNOWN,
)

MAX_STATE_LENGTH = 250


def normalize_text(text: str) -> str:
    """Normaliza texto en minúsculas y sin tildes para comparaciones."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def truncate_state(text: str, max_len: int = MAX_STATE_LENGTH) -> str:
    """Trunca un texto para cumplir con el límite de 255 caracteres de Home Assistant."""
    clean = " ".join((text or "").split())
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3].rstrip() + "..."


def classify_service_status(raw_status: str, extra_message: str = "") -> dict[str, str | bool]:
    """Clasifica el estado operativo y devuelve el estado directo y su categoría.

    Distingue entre:
    - 'normal': Servicio habitual sin novedades.
    - 'aviso': Comunicados informativos, cronogramas futuros o extensión horaria.
    - 'estacion_cerrada': Circulación normal de la línea pero con estación cerrada por obras.
    - 'demoras': Servicio funcionando con demoras o retrasos.
    - 'servicio_limitado': Servicio corto o recorrido reducido entre estaciones.
    - 'interrumpido': Servicio totalmente interrumpido, suspendido o cancelado.
    """
    status_clean = " ".join((raw_status or "").split())
    msg_clean = " ".join((extra_message or "").split())

    combined = msg_clean if msg_clean else status_clean
    if not combined:
        return {
            "estado": "Desconocido",
            "categoria": STATUS_CATEGORY_UNKNOWN,
            "mensaje": "",
            "alerta_operativa": False,
        }

    norm_status = normalize_text(status_clean)
    norm_combined = normalize_text(combined)

    if norm_combined in ("normal", "servicio normal", "a tiempo", "operativo"):
        return {
            "estado": "Normal",
            "categoria": STATUS_CATEGORY_NORMAL,
            "mensaje": "",
            "alerta_operativa": False,
        }

    # Determinar categoría según palabras clave en el mensaje completo
    if any(
        kw in norm_combined
        for kw in (
            "interrumpid",
            "suspendid",
            "sin servicio",
            "cancelad",
            "no circula",
            "paro ",
        )
    ):
        categoria = STATUS_CATEGORY_INTERRUPTED
    elif any(
        kw in norm_combined
        for kw in (
            "servicio limitad",
            "recorrido limitad",
            "recorrido reducid",
            "servicio reducid",
            "servicio corto",
            "circula entre",
            "limitado entre",
        )
    ):
        categoria = STATUS_CATEGORY_LIMITED
    elif any(kw in norm_combined for kw in ("demora", "retraso")):
        categoria = STATUS_CATEGORY_DELAY
    elif any(
        kw in norm_combined
        for kw in (
            "cerrad",
            "no se detiene",
            "sin detencion",
            "clausurad",
        )
    ):
        categoria = STATUS_CATEGORY_STATION_CLOSED
    elif norm_status in ("normal", "alertas por ramal", "alerta activa"):
        categoria = STATUS_CATEGORY_ADVISORY
    else:
        categoria = STATUS_CATEGORY_ADVISORY

    # El estado visible muestra directamente cuál es el problema (truncado a 250 chars)
    display_state = truncate_state(combined)

    return {
        "estado": display_state,
        "categoria": categoria,
        "mensaje": combined,
        "alerta_operativa": categoria in OPERATIONAL_PROBLEM_CATEGORIES,
    }


def is_station_affected_by_message(station_name: str, line_message: str) -> bool:
    """Detecta si una estación puntual es mencionada en un aviso de cierre/obra."""
    if not station_name or not line_message:
        return False
    norm_msg = normalize_text(line_message)
    if not any(
        kw in norm_msg
        for kw in ("cerrad", "no se detiene", "sin detencion", "obras")
    ):
        return False

    # Ejemplo: "Almagro - Medrano" -> chequeamos "medrano" y "almagro"
    norm_station = normalize_text(station_name)
    parts = [p.strip() for p in norm_station.split("-") if len(p.strip()) >= 4]
    if not parts:
        parts = [norm_station]
    return any(part in norm_msg for part in parts if part)
