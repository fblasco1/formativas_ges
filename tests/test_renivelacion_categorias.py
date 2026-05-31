# -*- coding: utf-8 -*-
from analisis.renivelacion_tiras.categorias import (
    CATEGORIAS_COMPETITIVAS,
    bucket_renivelacion,
    columna_puntos,
    es_categoria_competitiva,
)


def test_legacy_2024_desplazamiento():
    """CSV 2023-24: nombres viejos → bucket desplazado."""
    assert bucket_renivelacion("PREINFANTILES", 2024) == "INFANTILES"
    assert bucket_renivelacion("INFANTILES", 2024) == "CADETES"
    assert bucket_renivelacion("CADETES", 2024) == "JUVENILES"
    assert bucket_renivelacion("JUVENILES", 2024) == "LIGA PROXIMO"


def test_preinfantiles_obsoleto_siempre_infantiles():
    """PREINFANTILES ya no existe en GES; mismo bucket en cualquier año."""
    assert bucket_renivelacion("PREINFANTILES", 2023) == "INFANTILES"
    assert bucket_renivelacion("PREINFANTILES", 2026) == "INFANTILES"
    assert bucket_renivelacion("PREINFANTILES MASCULINO", 2025) == "INFANTILES"


def test_nuevo_2025_masculino():
    assert bucket_renivelacion("INFANTILES MASCULINO", 2025) == "INFANTILES"
    assert bucket_renivelacion("CADETES MASCULINO", 2025) == "CADETES"
    assert bucket_renivelacion("JUVENILES MASCULINO", 2025) == "JUVENILES"
    assert bucket_renivelacion("LIGA PROXIMO MASCULINO", 2026) == "LIGA PROXIMO"


def test_mini_no_competitivo():
    assert not es_categoria_competitiva("MINI", 2024)
    assert bucket_renivelacion("PREMINI", 2025) is None


def test_equivalencia_u():
    assert bucket_renivelacion("U17 MASCULINO", 2025) == "JUVENILES"
    assert bucket_renivelacion("U19", 2024) == "LIGA PROXIMO"


def test_columnas_export():
    assert columna_puntos("Pts_Aportados", "LIGA PROXIMO") == "Pts_Aportados_LIGA_PROXIMO"
    assert len(CATEGORIAS_COMPETITIVAS) == 4
