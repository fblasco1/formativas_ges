# -*- coding: utf-8 -*-
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from parsers.fases_formativas_2025_2026 import debe_omitir_fase, parsear_fase_2025, parsear_fase_2026
from parsers.grupos_formativas_2025_2026 import parsear_grupo_2025, parsear_grupo_2026


def test_omitir_fases():
    assert debe_omitir_fase("CLASIFICACION LFF") is True
    assert debe_omitir_fase("1er ETAPA LFF") is False
    assert debe_omitir_fase("1ER ENCUENTRO") is True
    assert debe_omitir_fase("2do ENCUENTRO") is True
    assert debe_omitir_fase("TORNEO DE CLASIFICACION") is False


def test_fase_2025_basico():
    p = parsear_fase_2025("1er ETAPA LFF")
    assert p["fase"] == "Fase Regular"
    assert p["ronda"] == "Copa Febamba"
    p2 = parsear_fase_2025("2do SEMESTRE")
    assert p2["fase"] == "Fase Regular"
    assert p2["ronda"] == "2da Fase"
    p3 = parsear_fase_2025("FINAL FOUR 2")
    assert p3["fase"] == "Final Four"
    assert p3["nivel"] == "2"


def test_grupo_2025_segundo_semestre():
    g = parsear_grupo_2025("2do SEMESTRE", "NORTE 2 A")
    assert g["zona"] == "NORTE"
    assert g["nivel"] == "2"
    assert g["grupo"] in ("2A", "2")


def test_fase_2026():
    p = parsear_fase_2026("TORNEO DE CLASIFICACION")
    assert p["fase"] == "Fase Regular"
    assert p["ronda"] == "Torneo Clasificacion"
    assert p["nivel"] == "CLASIFICACION"
    p2 = parsear_fase_2026("TORNEO RECLASIFICATORIO")
    assert p2["fase"] == "Fase Regular"
    assert p2["ronda"] == "Torneo Reclasificatorio"
    assert p2["nivel"] == "RECLASIFICACION"
