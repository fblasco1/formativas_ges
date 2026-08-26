# -*- coding: utf-8 -*-
"""Tests del mapper CM Pedro Echagüe (sin red ni Google)."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.sync_fixture_echague_sheets import (
    TZ_ART,
    es_equipo_echague,
    construir_payload_json,
    escribir_json,
    fecha_a_iso,
    fila_a_partido_json,
    mapear_fila,
    split_fecha_hora,
    timestamp_art,
    tira_desde_nombre,
)


def test_es_equipo_echague():
    assert es_equipo_echague("PEDRO ECHAGUE AZUL")
    assert es_equipo_echague("Pedro Echagüe Amarillo")
    assert es_equipo_echague("INSTITUCION CULTURAL y DEPORTIVA PEDRO ECHAGUE")
    assert not es_equipo_echague("FERROCARRIL OESTE VERDE")
    assert not es_equipo_echague("CLUB SOCIAL DEPORTIVO Y CULTURAL ARGENTINO DE CASTELAR")


def test_tira_y_fecha():
    assert tira_desde_nombre("PEDRO ECHAGUE AZUL") == "AZUL"
    assert tira_desde_nombre("PEDRO ECHAGUE AMARILLO") == "AMARILLO"
    assert tira_desde_nombre("PEDRO ECHAGUE FLEX") == "FLEX"
    assert tira_desde_nombre("PEDRO ECHAGUE B") == "B"
    assert tira_desde_nombre("PEDRO ECHAGUE") == "—"
    assert tira_desde_nombre("PEDRO ECHAGUE", "SUP") == "A"
    assert tira_desde_nombre("PEDRO ECHAGUE B", "SUP") == "B"
    assert tira_desde_nombre("PEDRO ECHAGUE", "SUP Flex") == "C"
    assert (
        tira_desde_nombre(
            "INSTITUCION CULTURAL y DEPORTIVA PEDRO ECHAGUE", "Liga Metro"
        )
        == "A"
    )
    assert split_fecha_hora("15/03/2026 12:30") == ("15/03/2026", "12:30")
    assert split_fecha_hora("15/03/2026") == ("15/03/2026", "")


def test_fuentes_incluye_competencias_pedidas():
    from analysis.sync_fixture_echague_sheets import FUENTES, COMPETENCIA_LABEL

    comps = {f[0] for f in FUENTES}
    assert comps >= {2015, 2013, 2310, 2018, 2019, 2028}
    labels = {f[1] for f in FUENTES}
    assert "U21" in labels
    assert "SUP" in labels
    assert "Liga Metro" in labels
    assert "U17 Flex" in labels
    assert "SUP Flex" in labels
    assert "U15 Fem" in labels
    assert COMPETENCIA_LABEL[2018] == "Flex formativas"
    assert COMPETENCIA_LABEL[2310] == "Liga Metropolitana"
    assert any(f == (2310, "Liga Metro", 6290) for f in FUENTES)


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


def test_fecha_a_iso():
    assert fecha_a_iso("06/09/2026") == "2026-09-06"
    assert fecha_a_iso("6/9/2026") == "2026-09-06"
    assert fecha_a_iso("2026-09-06") == "2026-09-06"
    assert fecha_a_iso("") == ""
    assert fecha_a_iso("20 A 22") == "20 A 22"


def test_timestamp_art_offset():
    ts = timestamp_art(datetime(2026, 8, 26, 20, 0, 0, tzinfo=TZ_ART))
    assert ts == "2026-08-26T20:00:00-03:00"
    naive = timestamp_art(datetime(2026, 8, 26, 20, 0, 0))
    assert naive.endswith("-03:00")


def test_fila_a_partido_json_contrato_siclub():
    partido = fila_a_partido_json(
        {
            "FECHA": "06/09/2026",
            "HORA": "20:00",
            "TIRA": "AZUL",
            "CATEGORIA": "U17",
            "RIVAL": "Club Visitante",
            "LOCALIA": "Local",
            "DIRECCION": "Portela 836, CABA (CP 1406)",
            "RESULTADO": "",
            "ID_PARTIDO": "abc-123",
        }
    )
    assert partido == {
        "source": "febamba_ges",
        "external_id": "abc-123",
        "fecha": "2026-09-06",
        "hora": "20:00",
        "tira": "AZUL",
        "categoria": "U17",
        "rival": "Club Visitante",
        "localia": "Local",
        "direccion": "Portela 836, CABA (CP 1406)",
        "resultado": "",
        "espacio": None,
    }


def test_construir_payload_json_incluye_local_y_visitante():
    filas = [
        {
            "FECHA": "06/09/2026",
            "HORA": "20:00",
            "TIRA": "AZUL",
            "CATEGORIA": "U17",
            "RIVAL": "Rival Local",
            "LOCALIA": "Local",
            "DIRECCION": "Portela 836, CABA (CP 1406)",
            "RESULTADO": "72-65",
            "ID_PARTIDO": "loc-1",
        },
        {
            "FECHA": "07/09/2026",
            "HORA": "20 A 22",
            "TIRA": "AMARILLO",
            "CATEGORIA": "U15",
            "RIVAL": "Ñuñorco",
            "LOCALIA": "Visitante",
            "DIRECCION": "Calle Falsa 123",
            "RESULTADO": "",
            "ID_PARTIDO": "vis-2",
        },
        {
            "FECHA": "08/09/2026",
            "HORA": "18:00",
            "TIRA": "AZUL",
            "CATEGORIA": "U13",
            "RIVAL": "Sin ID",
            "LOCALIA": "Local",
            "DIRECCION": "",
            "RESULTADO": "",
            "ID_PARTIDO": "",
        },
    ]
    payload = construir_payload_json(
        filas, generated_at="2026-08-26T20:00:00-03:00"
    )
    assert payload["version"] == 1
    assert payload["source"] == "febamba_ges"
    assert payload["generated_at"] == "2026-08-26T20:00:00-03:00"
    assert payload["club"] == "PEDRO ECHAGUE"
    assert [p["external_id"] for p in payload["partidos"]] == ["loc-1", "vis-2"]
    assert payload["partidos"][0]["localia"] == "Local"
    assert payload["partidos"][1]["localia"] == "Visitante"
    assert payload["partidos"][1]["hora"] == "20 A 22"
    assert payload["partidos"][1]["rival"] == "Ñuñorco"
    assert payload["partidos"][0]["espacio"] is None
    assert payload["partidos"][1]["espacio"] is None


def test_escribir_json_utf8_indent():
    filas = [
        {
            "FECHA": "06/09/2026",
            "HORA": "20:00",
            "TIRA": "AZUL",
            "CATEGORIA": "U17",
            "RIVAL": "Ñuñorco",
            "LOCALIA": "Visitante",
            "DIRECCION": "Portela 836",
            "RESULTADO": "",
            "ID_PARTIDO": "id-ñ",
        }
    ]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "fixture_echague.json"
        out = escribir_json(
            filas, path, generated_at="2026-08-26T20:00:00-03:00"
        )
        raw = out.read_text(encoding="utf-8")
        assert "Ñuñorco" in raw
        assert "\\u00d1" not in raw
        data = json.loads(raw)
        assert data["partidos"][0]["espacio"] is None
        assert data["partidos"][0]["fecha"] == "2026-09-06"
