# -*- coding: utf-8 -*-
"""Equipos por región (zona) a partir de partidos normalizados."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

import pandas as pd

from mapeos.loader import cargar_mapeo_equipos, normalizar_equipo
from mapeos.zonas_reglas import zona_regional_equipo

ZONAS_INVALIDAS = {"DESCONOCIDO", "DESCONOCIDA", "DESCONOCIDOS", ""}
# Cuatro regiones FeBAMBA. INTERCONFERENCIA es fase/nivel (cruza regiones), no región.
REGIONES_FEBAMBA: tuple[str, ...] = ("SUR", "OESTE", "NORTE", "CENTRO")
REGIONES_APILADO = REGIONES_FEBAMBA
REGIONES_ORDEN = REGIONES_FEBAMBA
ZONAS_NO_REGION = frozenset({"INTERCONFERENCIA", "CENTRO-OESTE"})


def _norm_col(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.upper()


def cargar_partidos_normalizados(path: Path, sep: str = ";") -> pd.DataFrame:
    from utils.open_csv import leer_csv_con_encoding_detectado

    df = leer_csv_con_encoding_detectado(str(path), sep)
    df["anio"] = pd.to_numeric(df["anio"], errors="coerce")
    df = df.dropna(subset=["anio"])
    df["anio"] = df["anio"].astype(int)
    for c in ("categoria", "fase", "zona", "local", "visitante"):
        if c in df.columns:
            df[c] = _norm_col(df[c])
    mapeo = cargar_mapeo_equipos()
    df["local"] = df["local"].apply(lambda x: normalizar_equipo(x, mapeo).upper())
    df["visitante"] = df["visitante"].apply(lambda x: normalizar_equipo(x, mapeo).upper())
    return df


def es_region_febamba(zona: str) -> bool:
    return str(zona).upper().strip() in REGIONES_FEBAMBA


def _region_en_fila(row: pd.Series, equipo: str) -> str:
    """
    Región del equipo en un partido (solo SUR/OESTE/NORTE/CENTRO).
    Partidos de interconferencia no aportan región.
    """
    z_raw = str(row.get("zona", "")).upper().strip()
    if z_raw in ZONAS_NO_REGION or z_raw in ZONAS_INVALIDAS:
        return ""
    z = zona_regional_equipo(row["anio"], z_raw, equipo)
    if not es_region_febamba(z):
        return ""
    return z


def _zona_primaria(sub: pd.DataFrame, equipo: str) -> str:
    """Región dominante según partidos de fase regional (sin interconferencia)."""
    rows = sub[(sub["local"] == equipo) | (sub["visitante"] == equipo)]
    if rows.empty:
        return ""
    zonas = [_region_en_fila(row, equipo) for _, row in rows.iterrows()]
    zonas = [z for z in zonas if z]
    if not zonas:
        return ""
    cnt = Counter(zonas)
    return cnt.most_common(1)[0][0]


def equipos_detalle_region(
    df: pd.DataFrame,
    *,
    anio: Optional[int] = None,
    categoria: Optional[str] = None,
) -> pd.DataFrame:
    """Una fila por (zona, equipo) con partidos; equipos ordenados alfabéticamente."""
    sub = df.copy()
    if anio is not None:
        sub = sub[sub["anio"] == anio]
    if categoria and categoria != "_TODAS_":
        sub = sub[sub["categoria"] == categoria.upper()]
    sub = sub[~sub["zona"].isin(ZONAS_INVALIDAS)]

    filas: List[dict] = []
    equipos: Set[str] = set(sub["local"]) | set(sub["visitante"])
    equipos.discard("")
    for eq in equipos:
        zona = _zona_primaria(sub, eq)
        if not es_region_febamba(zona):
            continue
        n = len(sub[(sub["local"] == eq) | (sub["visitante"] == eq)])
        filas.append({"zona": zona, "equipo": eq, "partidos": n})

    out = pd.DataFrame(filas)
    if out.empty:
        return out
    out = out.sort_values(["zona", "equipo"], ascending=[True, True]).reset_index(drop=True)
    return out


def tiras_en_temporada(
    df: pd.DataFrame,
    anio: int,
) -> frozenset[str]:
    """Tiras (A/B) con al menos un partido en la temporada."""
    from analisis.renivelacion_tiras.tiras import tira_desde_equipo

    mapeo = cargar_mapeo_equipos()
    sub = df[df["anio"] == int(anio)]
    tiras: set[str] = set()
    for col in ("local", "visitante"):
        if col not in sub.columns:
            continue
        for nombre in sub[col].astype(str):
            if not nombre or nombre == "nan":
                continue
            t = tira_desde_equipo(nombre, mapeo)
            if t:
                tiras.add(t)
    return frozenset(tiras)


def mapa_region_equipos(
    df: pd.DataFrame,
    *,
    anio: int,
    categoria: Optional[str] = None,
) -> dict[str, str]:
    """Equipo normalizado → región (zona dominante en la temporada)."""
    detalle = equipos_detalle_region(df, anio=anio, categoria=categoria)
    if detalle.empty:
        return {}
    return dict(zip(detalle["equipo"], detalle["zona"]))


def totales_por_region(
    detalle: pd.DataFrame,
) -> pd.DataFrame:
    if detalle.empty:
        return pd.DataFrame(columns=["zona", "equipos_distintos"])
    tot = (
        detalle.groupby("zona")["equipo"]
        .nunique()
        .reset_index(name="equipos_distintos")
    )

    def _orden(z: str) -> tuple:
        z = str(z).upper()
        if z in REGIONES_ORDEN:
            return (0, REGIONES_ORDEN.index(z))
        return (1, z)

    tot["_ord"] = tot["zona"].map(_orden)
    tot = tot.sort_values("_ord").drop(columns="_ord")
    return tot.reset_index(drop=True)


def conteo_equipos_apilado_por_anio(
    df: pd.DataFrame,
    *,
    categorias: Optional[Iterable[str]] = None,
) -> pd.DataFrame:
    """
    Matriz temporada × región (equipos distintos) para gráfico de barras apiladas.
    """
    sub = df.copy()
    if categorias:
        cats = {c.upper() for c in categorias}
        sub = sub[sub["categoria"].isin(cats)]

    filas_eq: List[dict] = []
    for (anio, cat), g in sub.groupby(["anio", "categoria"]):
        equipos = set(g["local"]) | set(g["visitante"])
        equipos.discard("")
        for eq in equipos:
            z = _zona_primaria(g, eq)
            if not es_region_febamba(z):
                continue
            filas_eq.append({"anio": int(anio), "categoria": cat, "zona": z, "equipo": eq})

    if not filas_eq:
        return pd.DataFrame()

    eq_df = pd.DataFrame(filas_eq)
    por_cat = (
        eq_df.groupby(["anio", "categoria", "zona"])["equipo"]
        .nunique()
        .reset_index(name="equipos")
    )
    # Total: un equipo una sola vez por año (zona ya es la dominante en filas_eq)
    total_rows = []
    for anio, g in eq_df.groupby("anio"):
        g_year = sub[sub["anio"] == anio]
        equipos = set(g_year["local"]) | set(g_year["visitante"])
        equipos.discard("")
        for eq in equipos:
            z = _zona_primaria(g_year, eq)
            if es_region_febamba(z):
                total_rows.append({"anio": int(anio), "zona": z, "equipo": eq})
    if total_rows:
        total = (
            pd.DataFrame(total_rows)
            .groupby(["anio", "zona"])["equipo"]
            .nunique()
            .reset_index(name="equipos")
        )
        total["categoria"] = "_TODAS_"
        out = pd.concat([total, por_cat], ignore_index=True)
    else:
        out = por_cat
    return out


def pivot_apilado(conteo: pd.DataFrame, categoria: str = "_TODAS_") -> pd.DataFrame:
    """Wide: filas=temporada, columnas=regiones."""
    sub = conteo[conteo["categoria"] == categoria].copy()
    if sub.empty:
        return pd.DataFrame()
    wide = sub.pivot_table(
        index="anio", columns="zona", values="equipos", aggfunc="sum", fill_value=0
    )
    for r in REGIONES_APILADO:
        if r not in wide.columns:
            wide[r] = 0
    cols = [c for c in REGIONES_APILADO if c in wide.columns]
    extra = [c for c in wide.columns if c not in REGIONES_APILADO]
    return wide[cols + extra].astype(int)


def resumen_mapeo(mapeo: Optional[dict] = None) -> dict:
    mapeo = mapeo or cargar_mapeo_equipos()
    destinos = list(mapeo.values())
    return {
        "entradas": len(mapeo),
        "destinos_unicos": len(set(destinos)),
        "origenes_duplicados_destino": len(destinos) - len(set(destinos)),
    }
