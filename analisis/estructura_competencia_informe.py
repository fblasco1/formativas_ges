# -*- coding: utf-8 -*-
"""
Informe de estructura del torneo formativas: equipos por región, altas/bajas y cambios.

Entrada por defecto: Data/procesada/23-26.csv (GES 2023–2025).
Salida: outputs/informe_estructura/
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analisis.Ranking.seasons import FOCUS_YEARS, resolve_partidos_consolidado  # noqa: E402
from mapeos.loader import cargar_mapeo_equipos, normalizar_equipo  # noqa: E402
from utils.open_csv import leer_csv_con_encoding_detectado  # noqa: E402

ZONAS_INVALIDAS = {"DESCONOCIDO", "DESCONOCIDA", "DESCONOCIDOS", ""}
CATEGORIAS_EXCLUIR_DEFAULT = ("MOSQUITOS",)


def _norm_col(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.upper()


def cargar_partidos(path: Path, sep: str = ";") -> pd.DataFrame:
    df = leer_csv_con_encoding_detectado(str(path), sep)
    df["anio"] = pd.to_numeric(df["anio"], errors="coerce")
    df = df.dropna(subset=["anio"])
    df["anio"] = df["anio"].astype(int)
    for c in ["categoria", "fase", "ronda", "nivel", "zona", "local", "visitante"]:
        if c in df.columns:
            df[c] = _norm_col(df[c])
    mapeo = cargar_mapeo_equipos()
    df["local"] = df["local"].apply(lambda x: normalizar_equipo(x, mapeo).upper())
    df["visitante"] = df["visitante"].apply(lambda x: normalizar_equipo(x, mapeo).upper())
    return df


def filtrar_df(
    df: pd.DataFrame,
    years: Iterable[int],
    exclude_categorias: Iterable[str],
) -> pd.DataFrame:
    out = df[df["anio"].isin(list(years))].copy()
    if exclude_categorias and "categoria" in out.columns:
        cat_u = out["categoria"].str.upper()
        for ex in exclude_categorias:
            out = out[~cat_u.str.contains(ex.strip().upper(), na=False)]
    out = out[~out["zona"].isin(ZONAS_INVALIDAS)]
    return out


def _zona_primaria(sub: pd.DataFrame, equipo: str) -> str:
    """Zona más frecuente del equipo en el subconjunto (excl. interconferencia si hay otra)."""
    rows = sub[(sub["local"] == equipo) | (sub["visitante"] == equipo)]
    if rows.empty:
        return ""
    zonas = pd.concat(
        [
            rows.loc[rows["local"] == equipo, "zona"],
            rows.loc[rows["visitante"] == equipo, "zona"],
        ]
    )
    cnt = Counter(zonas.tolist())
    orden = sorted(
        cnt.keys(),
        key=lambda z: (
            z == "INTERCONFERENCIA",
            z in ZONAS_INVALIDAS,
            -cnt[z],
        ),
    )
    return orden[0] if orden else ""


def equipos_por_region_categoria(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por (anio, categoria, zona, equipo) con partidos jugados."""
    filas: List[dict] = []
    for (anio, cat), g in df.groupby(["anio", "categoria"]):
        equipos: Set[str] = set(g["local"]) | set(g["visitante"])
        equipos.discard("")
        for eq in equipos:
            zona = _zona_primaria(g, eq)
            if not zona or zona in ZONAS_INVALIDAS:
                continue
            n = len(
                g[(g["local"] == eq) | (g["visitante"] == eq)]
            )
            filas.append(
                {
                    "anio": anio,
                    "categoria": cat,
                    "zona": zona,
                    "equipo": eq,
                    "partidos": n,
                }
            )
    return pd.DataFrame(filas)


def totales_equipos(df_eq: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Totales por temporada y por temporada+región."""
    por_temp = (
        df_eq.groupby(["anio", "categoria"])["equipo"]
        .nunique()
        .reset_index(name="equipos_distintos")
    )
    por_temp_total = (
        df_eq.groupby("anio")["equipo"].nunique().reset_index(name="equipos_distintos")
    )
    por_temp_total["categoria"] = "_TODAS_"
    por_temp = pd.concat([por_temp, por_temp_total], ignore_index=True)

    por_reg = (
        df_eq.groupby(["anio", "categoria", "zona"])["equipo"]
        .nunique()
        .reset_index(name="equipos_distintos")
    )
    por_reg_total = (
        df_eq.groupby(["anio", "zona"])["equipo"]
        .nunique()
        .reset_index(name="equipos_distintos")
    )
    por_reg_total["categoria"] = "_TODAS_"
    por_reg = pd.concat([por_reg, por_reg_total], ignore_index=True)
    return por_temp, por_reg


def estructura_torneo_anual(df: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for (anio, cat), g in df.groupby(["anio", "categoria"]):
        filas.append(
            {
                "anio": anio,
                "categoria": cat,
                "partidos": len(g),
                "fases": " | ".join(sorted(g["fase"].unique())),
                "rondas": " | ".join(sorted(g["ronda"].unique())),
                "niveles": " | ".join(sorted(g["nivel"].unique())),
                "zonas": " | ".join(sorted(g["zona"].unique())),
                "n_zonas": g["zona"].nunique(),
                "n_fases": g["fase"].nunique(),
                "n_niveles": g["nivel"].nunique(),
            }
        )
    return pd.DataFrame(filas)


def movimientos_entre_anios(
    df_eq: pd.DataFrame,
    cat: str,
    anio_desde: int,
    anio_hasta: int,
) -> pd.DataFrame:
    """Nuevos, bajas y cambio de región entre dos años consecutivos (misma categoría)."""
    a = df_eq[(df_eq["anio"] == anio_desde) & (df_eq["categoria"] == cat)]
    b = df_eq[(df_eq["anio"] == anio_hasta) & (df_eq["categoria"] == cat)]
    map_a = a.set_index("equipo")["zona"].to_dict()
    map_b = b.set_index("equipo")["zona"].to_dict()
    set_a, set_b = set(map_a), set(map_b)

    filas = []
    for eq in sorted(set_b - set_a):
        filas.append(
            {
                "categoria": cat,
                "anio_anterior": anio_desde,
                "anio_actual": anio_hasta,
                "equipo": eq,
                "movimiento": "NUEVO",
                "zona_anterior": "",
                "zona_actual": map_b[eq],
            }
        )
    for eq in sorted(set_a - set_b):
        filas.append(
            {
                "categoria": cat,
                "anio_anterior": anio_desde,
                "anio_actual": anio_hasta,
                "equipo": eq,
                "movimiento": "BAJA",
                "zona_anterior": map_a[eq],
                "zona_actual": "",
            }
        )
    for eq in sorted(set_a & set_b):
        if map_a[eq] != map_b[eq]:
            filas.append(
                {
                    "categoria": cat,
                    "anio_anterior": anio_desde,
                    "anio_actual": anio_hasta,
                    "equipo": eq,
                    "movimiento": "CAMBIO_REGION",
                    "zona_anterior": map_a[eq],
                    "zona_actual": map_b[eq],
                }
            )
    return pd.DataFrame(filas)


def resumen_movimientos(df_mov: pd.DataFrame) -> pd.DataFrame:
    if df_mov.empty:
        return pd.DataFrame()
    return (
        df_mov.groupby(["categoria", "anio_anterior", "anio_actual", "movimiento"])
        .size()
        .reset_index(name="cantidad")
    )


def generar_informe_texto(
    df: pd.DataFrame,
    df_estructura: pd.DataFrame,
    df_tot_temp: pd.DataFrame,
    df_tot_reg: pd.DataFrame,
    df_mov: pd.DataFrame,
    df_res_mov: pd.DataFrame,
    years: List[int],
) -> str:
    lines = [
        "# Informe — Estructura torneo formativas FeBAMBA",
        "",
        f"Temporadas analizadas: {', '.join(str(y) for y in years)}",
        f"Partidos considerados: {len(df):,} (solo partidos jugados con marcador)",
        "",
        "**Nota 2026:** En GES el torneo está incompleto por ahora: solo figuran "
        "Torneo de Clasificación y Torneo Reclasificatorio (nivelación). "
        "Playoffs, Final Four e interconferencias de campeonato se publicarán después.",
        "",
        "## 1. Estructura año a año (por categoría)",
        "",
    ]
    for anio in years:
        lines.append(f"### Temporada {anio}")
        sub = df_estructura[df_estructura["anio"] == anio]
        for _, r in sub.iterrows():
            lines.append(
                f"- **{r['categoria']}**: {int(r['partidos']):,} partidos | "
                f"zonas: {r['zonas']} | fases: {r['fases']} | "
                f"niveles: {r['niveles']}"
            )
        tot = df_tot_temp[
            (df_tot_temp["anio"] == anio) & (df_tot_temp["categoria"] == "_TODAS_")
        ]
        if not tot.empty:
            lines.append(
                f"- **Total equipos distintos (todas categorías):** "
                f"{int(tot.iloc[0]['equipos_distintos'])}"
            )
        lines.append("")

    lines.extend(["## 2. Equipos por región y temporada", ""])
    for anio in years:
        lines.append(f"### {anio}")
        sub = df_tot_reg[
            (df_tot_reg["anio"] == anio) & (df_tot_reg["categoria"] != "_TODAS_")
        ]
        for cat in sorted(sub["categoria"].unique()):
            lines.append(f"#### {cat}")
            sc = sub[sub["categoria"] == cat].sort_values("zona")
            for _, r in sc.iterrows():
                lines.append(f"- {r['zona']}: **{int(r['equipos_distintos'])}** equipos")
        lines.append("")

    lines.extend(["## 3. Movimientos entre temporadas", ""])
    if df_res_mov.empty:
        lines.append("(Sin datos de comparación)")
    else:
        for _, r in df_res_mov.iterrows():
            lines.append(
                f"- {r['categoria']} {r['anio_anterior']}→{r['anio_actual']}: "
                f"**{r['movimiento']}** = {int(r['cantidad'])}"
            )
    lines.append("")
    lines.append("Detalle en `movimientos_equipos.csv`.")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Informe estructura torneo y equipos por región.")
    p.add_argument("--input", type=Path, default=None)
    p.add_argument("--sep", default=";")
    p.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "outputs" / "informe_estructura",
    )
    p.add_argument(
        "--years",
        type=int,
        nargs="+",
        default=list(FOCUS_YEARS),
    )
    p.add_argument(
        "--incluir-mini",
        action="store_true",
        help="Incluir MINI/PREMINI (por defecto se excluyen).",
    )
    args = p.parse_args()

    path = args.input or resolve_partidos_consolidado()
    if not path.is_file():
        print(f"No existe: {path}", file=sys.stderr)
        return 1

    excl = () if args.incluir_mini else CATEGORIAS_EXCLUIR_DEFAULT
    df_raw = cargar_partidos(path, args.sep)
    years_avail = sorted(df_raw["anio"].unique())
    years = [y for y in args.years if y in years_avail]
    if not years:
        print(f"Sin datos para años {args.years}. Disponibles: {years_avail}", file=sys.stderr)
        return 1

    df = filtrar_df(df_raw, years, excl)
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    df_eq = equipos_por_region_categoria(df)
    df_estructura = estructura_torneo_anual(df)
    df_tot_temp, df_tot_reg = totales_equipos(df_eq)

    mov_parts = []
    cats = sorted(df["categoria"].unique())
    for i in range(len(years) - 1):
        y0, y1 = years[i], years[i + 1]
        for cat in cats:
            m = movimientos_entre_anios(df_eq, cat, y0, y1)
            if not m.empty:
                mov_parts.append(m)
    df_mov = pd.concat(mov_parts, ignore_index=True) if mov_parts else pd.DataFrame()
    df_res_mov = resumen_movimientos(df_mov)

    df_estructura.to_csv(out / "estructura_torneo_anual.csv", index=False, encoding="utf-8-sig")
    df_eq.to_csv(out / "equipos_por_region_categoria.csv", index=False, encoding="utf-8-sig")
    df_tot_temp.to_csv(out / "totales_equipos_temporada.csv", index=False, encoding="utf-8-sig")
    df_tot_reg.to_csv(out / "totales_equipos_por_region.csv", index=False, encoding="utf-8-sig")
    if not df_mov.empty:
        df_mov.to_csv(out / "movimientos_equipos.csv", index=False, encoding="utf-8-sig")
    df_res_mov.to_csv(out / "resumen_movimientos.csv", index=False, encoding="utf-8-sig")

    texto = generar_informe_texto(
        df, df_estructura, df_tot_temp, df_tot_reg, df_mov, df_res_mov, years
    )
    (out / "INFORME.md").write_text(texto, encoding="utf-8")

    print(f"Informe generado en: {out.resolve()}")
    print(f"Temporadas: {years}")
    print(f"Partidos: {len(df):,} | Equipos (filas equipo-zona-cat): {len(df_eq):,}")
    if not df_res_mov.empty:
        print("\nResumen movimientos:")
        print(df_res_mov.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
