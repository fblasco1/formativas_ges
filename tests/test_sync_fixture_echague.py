# -*- coding: utf-8 -*-
"""Tests del mapper CM Pedro Echagüe (sin red ni Google)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.sync_fixture_echague_sheets import (
    es_equipo_echague,
    mapear_fila,
    split_fecha_hora,
    tira_desde_nombre,
)


def test_es_equipo_echague():
    assert es_equipo_echague("PEDRO ECHAGUE AZUL")
    assert es_equipo_echague("Pedro Echagüe Amarillo")
    assert not es_equipo_echague("FERROCARRIL OESTE VERDE")


def test_tira_y_fecha():
    assert tira_desde_nombre("PEDRO ECHAGUE AZUL") == "AZUL"
    assert tira_desde_nombre("PEDRO ECHAGUE AMARILLO") == "AMARILLO"
    assert tira_desde_nombre("PEDRO ECHAGUE FLEX") == "FLEX"
    assert tira_desde_nombre("PEDRO ECHAGUE B") == "B"
    assert tira_desde_nombre("PEDRO ECHAGUE") == "—"
    assert split_fecha_hora("15/03/2026 12:30") == ("15/03/2026", "12:30")
    assert split_fecha_hora("15/03/2026") == ("15/03/2026", "")


def test_fuentes_incluye_competencias_pedidas():
    from analysis.sync_fixture_echague_sheets import FUENTES, COMPETENCIA_LABEL

    comps = {f[0] for f in FUENTES}
    assert comps >= {2015, 2013, 2018, 2019, 2028}
    labels = {f[1] for f in FUENTES}
    assert "U21" in labels
    assert "SUP" in labels
    assert "U17 Flex" in labels
    assert "SUP Flex" in labels
    assert "U15 Fem" in labels
    assert COMPETENCIA_LABEL[2018] == "Flex formativas"


def test_debe_actualizar_celda_preserva_direccion_manual():
    from analysis.sync_fixture_echague_sheets import debe_actualizar_celda

    assert debe_actualizar_celda("RESULTADO", "1-2", "3-4") is True
    assert debe_actualizar_celda("DIRECCION", "", "Calle Nueva 1") is True
    assert (
        debe_actualizar_celda("DIRECCION", "Calle Manual 10", "Calle Auto 99")
        is False
    )
    assert debe_actualizar_celda("DIRECCION", "Calle Manual 10", "Calle Manual 10") is False


def test_scopes_a_consultar_incremental():
    from analysis.sync_fixture_echague_sheets import scopes_a_consultar

    fases = {"FASE A": "10", "FASE B": "20"}
    grupos = {
        "FASE A": {"ZONA 1": "100", "ZONA 2": "101"},
        "FASE B": {"ZONA X": "200"},
    }
    cache = {
        "2015|5077|10|100": {
            "id_competencia": 2015,
            "id_categoria": 5077,
            "id_fase": "10",
            "id_grupo": "100",
        }
    }
    # Incremental: FASE A solo grupo 100; FASE B (nueva) todos
    got = scopes_a_consultar(
        id_comp=2015,
        id_cat=5077,
        fases=fases,
        grupos_por_fase=grupos,
        cache=cache,
        full=False,
    )
    assert ("FASE A", "10", "ZONA 1", "100") in got
    assert ("FASE A", "10", "ZONA 2", "101") not in got
    assert ("FASE B", "20", "ZONA X", "200") in got

    # Full: todo
    got_full = scopes_a_consultar(
        id_comp=2015,
        id_cat=5077,
        fases=fases,
        grupos_por_fase=grupos,
        cache=cache,
        full=True,
    )
    assert len(got_full) == 3


def test_mapear_fila_local_con_resultado():
    fila = mapear_fila(
        {
            "edad": "U15",
            "local": "PEDRO ECHAGUE AZUL",
            "visitante": "FERROCARRIL OESTE BLANCO",
            "pts_local": 72,
            "pts_visit": 65,
            "fecha": "15/03/2026 12:30",
            "estado": "COMPLETO",
            "id_partido": "abc123",
        },
        indice_dir={"FERROCARRIL OESTE BLANCO": "Calle Falsa 123"},
    )
    assert fila["FECHA"] == "15/03/2026"
    assert fila["HORA"] == "12:30"
    assert fila["TIRA"] == "AZUL"
    assert fila["CATEGORIA"] == "U15"
    assert fila["RIVAL"] == "FERROCARRIL OESTE BLANCO"
    assert fila["LOCALIA"] == "Local"
    assert "Portela" in fila["DIRECCION"]
    assert fila["RESULTADO"] == "72-65"
    assert fila["ID_PARTIDO"] == "abc123"


def test_mapear_fila_visitante_usa_dir_rival():
    fila = mapear_fila(
        {
            "edad": "U13",
            "local": "RIVAL FC",
            "visitante": "PEDRO ECHAGUE AMARILLO",
            "pts_local": None,
            "pts_visit": None,
            "fecha": "20/07/2026 18:00",
            "estado": "PENDIENTE",
            "id_partido": "xyz",
        },
        indice_dir={"RIVAL FC": "Av Siempre Viva 742"},
    )
    assert fila["TIRA"] == "AMARILLO"
    assert fila["LOCALIA"] == "Visitante"
    assert fila["DIRECCION"] == "Av Siempre Viva 742"
    assert fila["RESULTADO"] == ""
