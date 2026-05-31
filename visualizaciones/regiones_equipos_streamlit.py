# -*- coding: utf-8 -*-
"""
Equipos por región: barras apiladas y listado.

  streamlit run visualizaciones/regiones_equipos_streamlit.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analisis.Ranking.seasons import FOCUS_YEARS, resolve_partidos_consolidado  # noqa: E402
from mapeos.equipos_region import (  # noqa: E402
    REGIONES_APILADO,
    cargar_partidos_normalizados,
    conteo_equipos_apilado_por_anio,
    equipos_detalle_region,
    pivot_apilado,
    totales_por_region,
)

PARTIDOS_CONSOLIDADO = resolve_partidos_consolidado()

OUTPUT_DIR = ROOT / "outputs" / "regiones"


@st.cache_data(ttl=60)
def _cargar(path: str, mtime: float) -> pd.DataFrame:
    _ = mtime
    return cargar_partidos_normalizados(Path(path))


def main() -> None:
    st.set_page_config(page_title="Equipos por región", layout="wide")
    st.title("Equipos por región")

    if not PARTIDOS_CONSOLIDADO.is_file():
        st.error(
            f"Falta consolidado formativas ({PARTIDOS_CONSOLIDADO}). "
            "Ejecutá consolidar y normalizar primero."
        )
        st.stop()

    df = _cargar(str(PARTIDOS_CONSOLIDADO), PARTIDOS_CONSOLIDADO.stat().st_mtime)
    st.caption(
        "Cuatro regiones: SUR, OESTE, NORTE, CENTRO. La interconferencia no es región. "
        "CENTRO-OESTE (2024–2025): **CLARIDAD** → OESTE; demás → CENTRO."
    )

    cats = ["_TODAS_"] + sorted(df["categoria"].dropna().unique().tolist())
    cat_sel = st.selectbox("Categoría", cats)

    conteo = conteo_equipos_apilado_por_anio(df)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    conteo.to_csv(OUTPUT_DIR / "equipos_por_region_anual.csv", index=False, encoding="utf-8-sig", sep=";")

    wide = pivot_apilado(conteo, cat_sel)
    if wide.empty:
        st.warning("Sin datos para esta categoría.")
        st.stop()

    wide.to_csv(OUTPUT_DIR / f"equipos_apilado_{cat_sel}.csv", encoding="utf-8-sig", sep=";")

    st.subheader("Cantidad de equipos por temporada (barras apiladas)")
    plot_df = wide.reset_index().melt(id_vars="anio", var_name="region", value_name="equipos")
    fig = px.bar(
        plot_df,
        x="anio",
        y="equipos",
        color="region",
        category_orders={"region": list(REGIONES_APILADO)},
        title=f"Equipos distintos por región — {cat_sel}",
        labels={"anio": "Temporada", "equipos": "Equipos", "region": "Región"},
    )
    fig.update_layout(barmode="stack", xaxis=dict(type="category"))
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Tabla (temporada × región)")
    st.dataframe(wide.reset_index(), use_container_width=True, hide_index=True)

    anio_sel = st.selectbox("Temporada (detalle)", FOCUS_YEARS, index=len(FOCUS_YEARS) - 1)
    cat_det = None if cat_sel == "_TODAS_" else cat_sel
    detalle = equipos_detalle_region(df, anio=int(anio_sel), categoria=cat_det)
    totales = totales_por_region(detalle)

    st.subheader(f"Listado alfabético — {anio_sel}")
    for _, row in totales.iterrows():
        z = row["zona"]
        sub = detalle[detalle["zona"] == z][["equipo", "partidos"]].rename(
            columns={"equipo": "Equipo", "partidos": "Partidos"}
        )
        with st.expander(f"{z} ({int(row['equipos_distintos'])} equipos)"):
            st.dataframe(sub, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
