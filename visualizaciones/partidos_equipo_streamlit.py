# -*- coding: utf-8 -*-
"""
Partidos por equipo y temporada — filtro 0-0, 20-0, 0-20.

  streamlit run visualizaciones/partidos_equipo_streamlit.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analisis.Ranking.seasons import FOCUS_YEARS, resolve_partidos_consolidado  # noqa: E402
from analisis.partidos_equipo import (  # noqa: E402
    FILTROS_ESPECIALES,
    filtrar_por_tipo,
    partidos_de_equipo,
    resumen_tipos,
)
from mapeos.equipos_region import cargar_partidos_normalizados  # noqa: E402

PARTIDOS_CONSOLIDADO = resolve_partidos_consolidado()


@st.cache_data(ttl=60)
def _cargar(path: str, mtime: float) -> pd.DataFrame:
    _ = mtime
    return cargar_partidos_normalizados(Path(path))


@st.cache_data(ttl=60)
def _equipos_lista(df: pd.DataFrame) -> list[str]:
    eq = set(df["local"].astype(str)) | set(df["visitante"].astype(str))
    return sorted(e for e in eq if e and e != "nan")


def main() -> None:
    st.set_page_config(page_title="Partidos por equipo", layout="wide")
    st.title("Partidos por equipo")

    if not PARTIDOS_CONSOLIDADO.is_file():
        st.error(f"Falta consolidado formativas ({PARTIDOS_CONSOLIDADO})")
        st.stop()

    df = _cargar(str(PARTIDOS_CONSOLIDADO), PARTIDOS_CONSOLIDADO.stat().st_mtime)
    equipos = _equipos_lista(df)

    with st.expander("¿Cómo leer 0-0, 20-0 y 0-20?"):
        st.markdown(
            """
- **0-20 en contra**: tu equipo quedó en **0** → suele ser **no presentación** (no completó).
- **20-0 a favor**: el rival quedó en **0** → tu equipo **sí presentó** (ganás por forfait GES).
- **0-0**: ambos en 0 → revisar en acta; muchas veces **doble no presentación**.
- **Partido normal**: se jugó con marcador FeBAMBA (diferencia de puntos, no 20-0 fijo).
            """
        )

    c1, c2, c3 = st.columns(3)
    with c1:
        equipo = st.selectbox("Equipo", equipos, index=0 if equipos else None)
    with c2:
        anio = st.selectbox("Temporada", ["Todas"] + list(FOCUS_YEARS), index=1)
    with c3:
        filtro_tipo = st.selectbox("Filtrar marcador", FILTROS_ESPECIALES)

    anio_val = None if anio == "Todas" else int(anio)
    partidos = partidos_de_equipo(df, equipo, anio=anio_val)
    partidos_f = filtrar_por_tipo(partidos, filtro_tipo)

    if partidos.empty:
        st.warning("Sin partidos para esa combinación.")
        st.stop()

    st.subheader(f"{equipo} — {anio}")
    res = resumen_tipos(partidos)
    cols = st.columns(len(res) if len(res) else 1)
    for i, row in res.iterrows():
        with cols[i % len(cols)]:
            st.metric(row["tipo_marcador"], int(row["cantidad"]))

    np_count = int((partidos["no_presenta"] == "Sí").sum())
    normal_count = int((partidos["tipo_marcador"] == "Partido normal").sum())
    st.caption(
        f"Mostrando **{len(partidos_f)}** de **{len(partidos)}** partidos · "
        f"Normales: {normal_count} · Marcados como no presenta: {np_count}"
    )

    st.dataframe(
        partidos_f,
        use_container_width=True,
        hide_index=True,
        height=min(700, 40 + len(partidos_f) * 35),
        column_config={
            "pts_propio": st.column_config.NumberColumn("Pts propios", format="%d"),
            "pts_rival": st.column_config.NumberColumn("Pts rival", format="%d"),
        },
    )


if __name__ == "__main__":
    main()
