# -*- coding: utf-8 -*-
from mapeos.equipos_casos import club_base, detectar_casos
from mapeos.loader import agregar_entradas_mapeo, clave_mapeo, normalizar_equipo
import pandas as pd


def test_clave_mapeo_upper_strip():
    assert clave_mapeo('  boca juniors "a"  ') == 'BOCA JUNIORS "A"'


def test_normalizar_equipo_con_mapa():
    mapeo = {"BOCA JUNIORS": "BOCA JUNIORS AZUL"}
    assert normalizar_equipo("boca juniors", mapeo) == "BOCA JUNIORS AZUL"
    assert normalizar_equipo("OTRO", mapeo) == "OTRO"


def test_detectar_caso_club_varios_nombres():
    df = pd.DataFrame(
        {
            "anio": [2024, 2024, 2025],
            "local": ["MORON A", "MORON B", "MORON ROJO"],
            "visitante": ["X", "Y", "Z"],
        }
    )
    casos = detectar_casos(df, mapeo={})
    tipos = {c.tipo for c in casos}
    assert "club_varios_nombres" in tipos


def test_agregar_entradas_mapeo(tmp_path, monkeypatch):
    import mapeos.loader as loader

    map_file = tmp_path / "equipos_map.json"
    map_file.write_text('{"A": "ALFA"}', encoding="utf-8")
    monkeypatch.setattr(loader, "EQUIPOS_MAP_PATH", map_file)

    agregar_entradas_mapeo({"b": "BETA"})
    data = loader.cargar_mapeo_equipos()
    assert data["A"] == "ALFA"
    assert data["B"] == "BETA"
