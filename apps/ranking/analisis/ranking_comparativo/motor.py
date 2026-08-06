# -*- coding: utf-8 -*-
"""
Motor comparativo: ranking GES (baseline) vs ranking institucional (tira).

Uso:
  python -m analisis.ranking_comparativo.motor
  python -m analisis.ranking_comparativo.motor --output-dir outputs/comparativa
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analisis.Ranking.seasons import FOCUS_YEARS, PROCESADA_DIR  # noqa: E402
from analisis.ranking_comparativo.baseline import procesar_baseline_anual  # noqa: E402
from analisis.ranking_comparativo.comparativa import (  # noqa: E402
    comparar_rankings,
    exportar_comparativa,
)
from analisis.ranking_comparativo.ingesta import cargar_partidos, validar_datos  # noqa: E402
from analisis.ranking_comparativo.institucional import (  # noqa: E402
    procesar_institucional_acumulado_global,
    procesar_institucional_anual,
    resumen_jornadas_tira,
)

# =============================================================================
# ANÁLISIS TÉCNICO (tarea 5) — ver también docstring al final del archivo
# =============================================================================


def ejecutar(
    *,
    input_csv: Path | None = None,
    output_dir: Path | None = None,
    years: tuple[int, ...] = FOCUS_YEARS,
    sep: str = ";",
    verbose: bool = True,
) -> pd.DataFrame:
    out_dir = Path(output_dir or ROOT / "outputs" / "comparativa")
    out_dir.mkdir(parents=True, exist_ok=True)

    data = cargar_partidos(input_csv, sep=sep, years=years, exclude_mini_premini=True)
    data_presencia = cargar_partidos(
        input_csv, sep=sep, years=years, exclude_mini_premini=False
    )
    invalid_pts, sin_banda = validar_datos(data)
    if verbose:
        print(f"Partidos cargados: {len(data)}")
        if invalid_pts:
            print(f"  [aviso] {invalid_pts} filas con marcador no numérico (BP=0)")
        if sin_banda:
            print(f"  [aviso] {sin_banda} filas sin banda U mapeada (no cuentan en tira)")

    _, ranking_equipos, ranking_club_baseline = procesar_baseline_anual(data, years)
    partidos_inst, _ = procesar_institucional_anual(
        data, years, data_presencia=data_presencia
    )
    ranking_club_nuevo = procesar_institucional_acumulado_global(partidos_inst)

    comparativa = comparar_rankings(ranking_club_baseline, ranking_club_nuevo)

    ranking_equipos.to_csv(
        out_dir / "Ranking_Actual_Equipos.csv", index=False, encoding="utf-8-sig", sep=sep
    )
    ranking_club_baseline.to_csv(
        out_dir / "Ranking_Actual_Clubes.csv", index=False, encoding="utf-8-sig", sep=sep
    )
    ranking_club_nuevo.to_csv(
        out_dir / "Ranking_Nuevo_Clubes.csv", index=False, encoding="utf-8-sig", sep=sep
    )
    exportar_comparativa(comparativa, out_dir / "Comparativa_Rankings.csv", sep=sep)

    if partidos_inst:
        resumen = pd.concat(
            [
                resumen_jornadas_tira(
                    df,
                    data_presencia[data_presencia["anio"] == year],
                )
                for year, df in partidos_inst.items()
            ],
            ignore_index=True,
        )
        resumen.to_csv(
            out_dir / "Resumen_Tira_Jornadas.csv",
            index=False,
            encoding="utf-8-sig",
            sep=sep,
        )

    if verbose:
        print(f"Comparativa: {out_dir / 'Comparativa_Rankings.csv'}")
        print(f"Clubes evaluados: {len(comparativa)}")
        top_sube = comparativa.nlargest(3, "Delta_Posicion")
        top_baja = comparativa.nsmallest(3, "Delta_Posicion")
        print("Mayor mejora de posición (institucional vs GES):")
        for _, r in top_sube.iterrows():
            print(f"  {r['Club']}: {int(r['Delta_Posicion']):+d} puestos")
        print("Mayor caída de posición:")
        for _, r in top_baja.iterrows():
            print(f"  {r['Club']}: {int(r['Delta_Posicion']):+d} puestos")

    return comparativa


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Motor comparativo GES vs institucional (tira).")
    p.add_argument("--input", type=Path, default=None, help="CSV consolidado de partidos.")
    p.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs" / "comparativa",
    )
    p.add_argument("--years", type=int, nargs="+", default=list(FOCUS_YEARS))
    p.add_argument("--sep", default=";")
    p.add_argument("-q", "--quiet", action="store_true")
    args = p.parse_args(argv)

    ejecutar(
        input_csv=args.input,
        output_dir=args.output_dir,
        years=tuple(args.years),
        sep=args.sep,
        verbose=not args.quiet,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# =============================================================================
# ANÁLISIS Y SUGERENCIAS (Tarea 5)
# =============================================================================
#
# --- 1. Complejidad algorítmica: fila a fila vs groupby ---
#
# Baseline GES:
#   - BP por fila es O(n) con apply; ORP también O(n) pero con lookup O(1) en dict
#     de posiciones → adecuado hasta cientos de miles de partidos.
#   - Agrupación final groupby(equipo).sum() es O(n) y debe preferirse siempre
#     frente a bucles Python puros.
#
# Modelo institucional (P_tira):
#   - Agrupar por jornada_id = (fecha, club_local, club_visitante) es O(n).
#   - Calcular bandas presentes por (jornada, club) recorre cada jornada una vez;
#     con G jornadas y C categorías promedio por jornada, costo ~ O(n).
#   - La implementación actual usa groupby + apply para mapear P_tira a cada fila;
#     para >500k filas conviene:
#       (a) construir DataFrame (jornada_id, club, P_tira) y hacer merge vectorizado
#           en lugar de apply por fila (evita Python callback por partido).
#       (b) precalcular bandas_presentes con pivot_table / categóricas.
#   - Complejidad dominante sigue siendo lineal O(n); el factor constante sube ~2-3×
#     respecto al baseline por el paso extra de jornada.
#
# --- 2. Edge cases del modelo de tira ---
#
# a) Fecha como única clave temporal:
#    Partidos reprogramados que conservan fecha original o comparten fecha entre
#    sedes distintas pueden fusionarse en una sola "jornada" ficticia → penalización
#    errónea (falta U15 cuando en realidad se jugó otro día).
#    Mitigación: añadir jornada_id oficial del fixture, o (fecha + grupo + zona).
#
# b) Oponente distinto por categoría el mismo día:
#    La tira asume club_local vs club_visitante constante en la fecha; si el club
#    A juega U13 vs X y U15 vs Y el mismo día, la agrupación por par de clubes
#    rompe la definición institucional de "tira contra un rival".
#    Mitigación: agrupar por (fecha, club_propio, club_rival_canónico) detectado
#    por mayoría de partidos del día o por calendario publicado.
#
# c) Mini/Premini excluidos del ranking pero obligatorios en tira:
#    Si el CSV no trae partidos U9/U11 (categorías excluidas del filtro MINI/PREMINI),
#    P_tira penalizará siempre -20% por cada banda → sesgo severo.
#    Mitigación: flag --incluir-mini-premini para evaluación de tira, o CSV
#    separado solo para presencia institucional sin entrar al BP.
#
# d) Marcadores 20-0 / 0-0:
#    Siguen generando BP GES; la tira no los distingue de partidos normales salvo
#    exclusiones manuales (exclusiones_partidos.json).
#
# e) Club heurístico (quitar " A"/" B"):
#    Alias mal mapeados fusionan clubes distintos o separan el mismo club.
#
# --- 3. Impacto conceptual en el ecosistema de clubes ---
#
# - Baseline GES: incentiva volumen de partidos competitivos y victorias abultadas
#   (BP por diferencia), con ORP que premia ganarle a rivales bien rankeados el año
#   anterior. Es acumulativo por equipo/categoría mezclado → clubes con muchas
#   divisiones y partidos de Interconferencia suben más rápido.
#
# - Institucional + tira: castiga la incompletitud de la estructura formativa en cada
#   fecha (-20% U9/U11, -15% bandas mayores). Un club con buen rendimiento deportivo
#   pero mala presentación de divisiones baja fuerte en Puntos_Nuevo aunque mantenga
#   BP alto partido a partido.
#
# - Peso por año (0.25→1.0): temporadas recientes pesan más en ambos modelos; el
#   acumulado no es "histórico plano", favorece clubes consistentes en 2025-2026.
#
# - Comparación en Comparativa_Rankings.csv:
#   Delta_Posicion > 0 ⇒ el club sube en el ranking institucional (mejor cumplimiento
#   de tira relativo a sus puntos GES). Clubes "parche" (pocos equipos pero muy
#   ganadores) suelen caer; instituciones completas suben.
#
# Recomendación operativa: validar Resumen_Tira_Jornadas.csv antes de publicar
# rankings institucionales y calibrar si U9/U11 deben leerse de partidos MINI/PREMINI.
# =============================================================================
