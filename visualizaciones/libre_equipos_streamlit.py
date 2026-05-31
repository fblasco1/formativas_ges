# -*- coding: utf-8 -*-
"""
Partidos LIBRE + correcciones de nombres de equipo.

  streamlit run visualizaciones/libre_equipos_streamlit.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analisis.Ranking.seasons import FOCUS_YEARS  # noqa: E402
from analisis.partidos_libre import (  # noqa: E402
    cargar_partidos,
    enriquecer_analisis_libre,
    resumen_por_rival,
)
from mapeos.loader import cargar_mapeo_equipos, normalizar_equipo  # noqa: E402

OUTPUT_LIBRE = ROOT / "outputs" / "mapeo" / "partidos_libre_analisis.csv"


@st.cache_data(ttl=120)
def _datos():
    df = cargar_partidos()
    lib = enriquecer_analisis_libre(df)
    return df, lib


def main() -> None:
    st.set_page_config(page_title="LIBRE y equipos", layout="wide")
    st.title("Partidos LIBRE y corrección de equipos")

    df, lib = _datos()
    mapeo = cargar_mapeo_equipos()

    tab_libre, tab_map, tab_dup = st.tabs(
        ["Partidos LIBRE", "Probar mapeos", "Duplicados A/B"]
    )

    with tab_libre:
        st.markdown(
            """
En GES, **LIBRE** es un cupo del fixture (fecha libre / local ficticio), no un club.
Solo hay **27 partidos** en 23–26; el ranking mostraba puntos de LIBRE porque se
acumulaban filas con visitante=LIBRE (ya corregido en el motor).

Para confirmar el club real cuando LIBRE es **local**, abrí el torneo en GES,
misma categoría / zona / grupo / fecha.
            """
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Partidos con LIBRE", len(lib))
        with c2:
            st.metric("LIBRE como local", int((lib["libre_en"] == "local").sum()))
        with c3:
            st.metric("LIBRE como visitante", int((lib["libre_en"] == "visitante").sum()))

        anio_f = st.multiselect("Año", sorted(lib["anio"].dropna().unique()), default=list(FOCUS_YEARS))
        sub = lib[lib["anio"].isin(anio_f)] if anio_f else lib

        st.subheader("Resumen por equipo conocido")
        st.dataframe(resumen_por_rival(sub), use_container_width=True, hide_index=True)

        st.subheader("Detalle")
        if st.button("Exportar CSV"):
            OUTPUT_LIBRE.parent.mkdir(parents=True, exist_ok=True)
            sub.to_csv(OUTPUT_LIBRE, index=False, encoding="utf-8-sig", sep=";")
            st.success(f"Guardado: {OUTPUT_LIBRE}")

        st.dataframe(
            sub,
            use_container_width=True,
            hide_index=True,
            column_config={
                "url_torneo_ges": st.column_config.LinkColumn("Torneo GES"),
            },
        )

        sel = st.selectbox(
            "Ver partido",
            range(len(sub)),
            format_func=lambda i: (
                f"{sub.iloc[i]['fecha']} | {sub.iloc[i]['categoria']} | "
                f"{sub.iloc[i]['local']} {sub.iloc[i]['ptsL']}-{sub.iloc[i]['ptsV']} "
                f"{sub.iloc[i]['visitante']}"
            ),
        )
        if len(sub):
            r = sub.iloc[sel]
            st.info(r["nota"])
            if r["candidato_equipo_real"]:
                st.write("**Candidato (heurística):**", r["candidato_equipo_real"])
            st.link_button("Abrir torneo en GES", r["url_torneo_ges"])

    with tab_map:
        st.markdown("Probá cómo queda un nombre tras `equipos_map.json` + correcciones.")
        nombres = st.text_area(
            "Nombres (uno por línea)",
            "SAN LORENZO\nSAN LORENZO A\nPLATENSE\nPLATENSE MARRON\nNAUTICO HACOAJ\nCLUB SPORTIVO PILAR\nEL PORVENIR JOSE C. PAZ\n",
        )
        filas = []
        for linea in nombres.strip().splitlines():
            raw = linea.strip()
            if not raw:
                continue
            filas.append({"original": raw, "normalizado": normalizar_equipo(raw, mapeo)})
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
        st.code("python pipelines/aplicar_correcciones_equipos.py", language="powershell")

    with tab_dup:
        st.markdown("Equipos que colisionan al normalizar (mismo destino o origen ambiguo).")
        casos = [
            "SAN LORENZO", "PLATENSE", "NAUTICO HACOAJ", "SAN FERNANDO",
            "ATLETICO BOULOGNE", "SPORTIVO PILAR", "EL PORVENIR", "PORTEÑO",
        ]
        for c in casos:
            hits = sorted(
                {k for k in mapeo if c in k.upper() or c in str(mapeo[k]).upper()}
            )[:12]
            if hits:
                st.write(f"**{c}** → `{normalizar_equipo(c, mapeo)}`")
                st.caption(", ".join(hits[:8]))


if __name__ == "__main__":
    main()
