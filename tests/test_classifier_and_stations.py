"""Pruebas unitarias para el clasificador de estados y catálogo de estaciones."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "transportes_ba"


def _load_module(name: str):
    spec = importlib.util.spec_from_file_location(
        f"custom_components.transportes_ba.{name}", ROOT / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"custom_components.transportes_ba.{name}"] = module
    spec.loader.exec_module(module)
    return module


const = _load_module("const")
classifier = _load_module("classifier")
stations = _load_module("stations")


def test_classify_normal_status():
    res = classifier.classify_service_status("Normal")
    assert res["estado"] == "Normal"
    assert res["categoria"] == const.STATUS_CATEGORY_NORMAL
    assert res["alerta_operativa"] is False


def test_classify_station_closed_shows_direct_message_without_false_alarm():
    msg = "Estación Medrano cerrada por obras. Viernes y Sábado con horario extendido."
    res = classifier.classify_service_status(msg)
    assert res["estado"] == msg
    assert res["categoria"] == const.STATUS_CATEGORY_STATION_CLOSED
    assert res["alerta_operativa"] is False


def test_classify_operational_delay_and_interruption():
    delay_res = classifier.classify_service_status("Con demoras por problemas técnicos")
    assert delay_res["estado"] == "Con demoras por problemas técnicos"
    assert delay_res["categoria"] == const.STATUS_CATEGORY_DELAY
    assert delay_res["alerta_operativa"] is True

    int_res = classifier.classify_service_status("Servicio interrumpido por manifestación")
    assert int_res["categoria"] == const.STATUS_CATEGORY_INTERRUPTED
    assert int_res["alerta_operativa"] is True


def test_truncate_state_respects_home_assistant_limit():
    long_msg = "A" * 300
    res = classifier.classify_service_status(long_msg)
    assert len(res["estado"]) <= 250
    assert res["estado"].endswith("...")
    assert len(res["mensaje"]) == 300


def test_is_station_affected_by_message():
    msg = "Estación Medrano cerrada por obras. Viernes y Sábado con horario extendido."
    assert classifier.is_station_affected_by_message("Almagro - Medrano", msg) is True
    assert classifier.is_station_affected_by_message("Federico Lacroze", msg) is False


def test_stations_catalog_and_nearby_radius():
    assert len(stations.STATIONS_CATALOG) >= 350

    # Coordenadas cercanas a Caballito (-34.6192, -58.4436)
    nearby = stations.get_nearby_station_keys(
        home_lat=-34.6192,
        home_lon=-58.4436,
        radius_km=1.2,
        subte_lines=["A"],
        trenes_lines=["Sarmiento"],
    )
    assert "tren:Sarmiento:50" in nearby  # Caballito
    assert any(k.startswith("subte:A:") for k in nearby)  # Acoyte / Primera Junta / Rio de Janeiro
