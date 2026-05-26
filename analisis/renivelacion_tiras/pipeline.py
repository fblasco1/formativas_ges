# -*- coding: utf-8 -*-
"""Pipeline incremental de renivelación por Tira."""

from __future__ import annotations

import pandas as pd

from analisis.Ranking.seasons import PROCESADA_DIR
from analisis.renivelacion_tiras.agregacion import (
    columnas_ranking_export,
    construir_ranking_baseline,
    construir_ranking_renivelacion,
    fusionar_acumulados,
)
from analisis.renivelacion_tiras.cache import (
    cache_historico_existe,
    cargar_cache_historico,
    guardar_cache_historico,
)
from analisis.renivelacion_tiras.ingesta import (
    HISTORICO_YEARS,
    cargar_dinamico_2026,
    cargar_historico,
)
from analisis.renivelacion_tiras.motor_partido import (
    enriquecer_partidos,
    ranking_tiras_desde_puntos,
)

OUTPUT_RANKING = PROCESADA_DIR / "Ranking_Tiras_Actualizado_2026.csv"
OUTPUT_BASELINE = PROCESADA_DIR / "Ranking_Tiras_Baseline_2026.csv"


def _ranking_para_orp(rank_year: pd.DataFrame) -> pd.DataFrame:
    r = rank_year[["Tira", "Total_Renivelacion"]].copy()
    return ranking_tiras_desde_puntos(
        r.rename(columns={"Total_Renivelacion": "Puntos"}),
        "Puntos",
    )


def _procesar_anios_secuencial(
    df: pd.DataFrame,
    years: tuple[int, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Enriquece partidos año a año; ORP usa ranking renivelación del año previo."""
    partes: list[pd.DataFrame] = []
    ranking_prev = pd.DataFrame(columns=["Tira", "Puntos", "Posicion"])

    for i, year in enumerate(sorted(years)):
        chunk = df[df["anio"] == year].copy()
        if chunk.empty:
            continue
        usar_orp = i > 0 and not ranking_prev.empty
        proc = enriquecer_partidos(chunk, ranking_prev, usar_orp=usar_orp)
        partes.append(proc)
        ranking_prev = _ranking_para_orp(construir_ranking_renivelacion(proc))

    if not partes:
        return pd.DataFrame(), ranking_prev
    return pd.concat(partes, ignore_index=True), ranking_prev


def congelar_historico(verbose: bool = True) -> None:
    """Módulo histórico: 2023-2025 → caché congelado."""
    if verbose:
        print("Cargando histórico 2023-2025...")
    raw = cargar_historico()
    if raw.empty:
        raise RuntimeError("Sin partidos históricos en Data/partidos_{2023,2024,2025}.csv")

    partidos, ranking_2025 = _procesar_anios_secuencial(raw, HISTORICO_YEARS)
    acumulado = construir_ranking_renivelacion(partidos)

    acumulado = acumulado[columnas_ranking_export(acumulado)]

    guardar_cache_historico(
        partidos,
        acumulado,
        ranking_2025,
        meta={
            "years": list(HISTORICO_YEARS),
            "partidos": len(partidos),
            "tiras": len(acumulado),
        },
    )
    if verbose:
        print(f"Cache guardado en {PROCESADA_DIR / 'renivelacion'}")
        print(f"  Partidos: {len(partidos)} | Tiras: {len(acumulado)}")


def actualizar_2026(verbose: bool = True) -> pd.DataFrame:
    """Módulo dinámico: caché histórico + solo partidos_2026.csv."""
    if not cache_historico_existe():
        if verbose:
            print("No hay caché histórico; congelando 2023-2025 primero...")
        congelar_historico(verbose=verbose)

    _, acum_hist, ranking_2025 = cargar_cache_historico()

    if verbose:
        print("Cargando partidos_2026.csv...")
    raw_2026 = cargar_dinamico_2026()
    if raw_2026.empty:
        raise RuntimeError("Sin datos en Data/partidos_2026.csv")

    proc_2026 = enriquecer_partidos(raw_2026, ranking_2025, usar_orp=True)
    acum_2026 = construir_ranking_renivelacion(proc_2026)
    final = fusionar_acumulados(acum_hist, acum_2026)
    final = final[columnas_ranking_export(final)]
    final.insert(0, "Posicion", range(1, len(final) + 1))

    PROCESADA_DIR.mkdir(parents=True, exist_ok=True)
    final.to_csv(OUTPUT_RANKING, index=False, encoding="utf-8-sig", sep=";")

    if verbose:
        print(f"Ranking exportado: {OUTPUT_RANKING}")
        print(f"Tiras: {len(final)}")
    return final


def exportar_baseline_comparativo(verbose: bool = True) -> pd.DataFrame:
    """Baseline GES acumulado (histórico + 2026) para comparación."""
    if not cache_historico_existe():
        congelar_historico(verbose=verbose)
    partidos_hist, _, ranking_2025 = cargar_cache_historico()
    proc_2026 = enriquecer_partidos(cargar_dinamico_2026(), ranking_2025, usar_orp=True)
    todo = pd.concat([partidos_hist, proc_2026], ignore_index=True)
    baseline = construir_ranking_baseline(todo)
    baseline.to_csv(OUTPUT_BASELINE, index=False, encoding="utf-8-sig", sep=";")
    if verbose:
        print(f"Baseline exportado: {OUTPUT_BASELINE}")
    return baseline


def ranking_renivelacion_para_anios(
    years: tuple[int, ...],
) -> pd.DataFrame:
    """
    Ranking de renivelación acumulado solo para las temporadas indicadas.
    Procesa años en orden cronológico (ORP año a año).
    """
    from analisis.renivelacion_tiras.ingesta import cargar_partidos_anios

    years_ord = tuple(sorted({int(y) for y in years}))
    if not years_ord:
        return pd.DataFrame()

    raw = cargar_partidos_anios(years_ord)
    if raw.empty:
        return pd.DataFrame()

    partidos, _ = _procesar_anios_secuencial(raw, years_ord)
    if partidos.empty:
        return pd.DataFrame()

    rank = construir_ranking_renivelacion(partidos)
    rank = rank[columnas_ranking_export(rank)]
    rank = rank.sort_values("Total_Renivelacion", ascending=False).reset_index(drop=True)
    rank.insert(0, "Posicion", range(1, len(rank) + 1))
    return rank


def ejecutar_completo(verbose: bool = True) -> pd.DataFrame:
    if not cache_historico_existe():
        congelar_historico(verbose=verbose)
    ranking = actualizar_2026(verbose=verbose)
    exportar_baseline_comparativo(verbose=verbose)
    return ranking
