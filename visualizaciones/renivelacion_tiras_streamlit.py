# -*- coding: utf-8 -*-
"""
Dashboard de renivelación por Tira (2023-2026).

  streamlit run visualizaciones/renivelacion_tiras_streamlit.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analisis.Ranking.seasons import PROCESADA_DIR  # noqa: E402
from analisis.renivelacion_tiras.pipeline import (  # noqa: E402
    OUTPUT_BASELINE,
    OUTPUT_RANKING,
)
from analisis.renivelacion_tiras.categorias import (  # noqa: E402
    CATEGORIAS_COMPETITIVAS,
    columna_puntos,
)
from analisis.renivelacion_tiras.tiras import institucion_desde_tira  # noqa: E402

CACHE_DIR = PROCESADA_DIR / "renivelacion"
ACUM_HIST = CACHE_DIR / "acumulado_tiras_2023_2025.csv"

COLS_RENIV = [columna_puntos("Pts_Aportados", c) for c in CATEGORIAS_COMPETITIVAS]
COLS_BASE = [columna_puntos("Pts_Baseline", c) for c in CATEGORIAS_COMPETITIVAS]
LABEL_CATEGORIA = {
    "Pts_Aportados_INFANTILES": "INFANTILES",
    "Pts_Aportados_CADETES": "CADETES",
    "Pts_Aportados_JUVENILES": "JUVENILES",
    "Pts_Aportados_LIGA_PROXIMO": "LIGA PROXIMO",
}


def _leer_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    sep = ";" if path.read_bytes()[:2000].count(b";") > path.read_bytes()[:2000].count(b",") else ","
    return pd.read_csv(path, sep=sep)


@st.cache_data(ttl=120)
def _cargar_renivelacion(path: str, mtime: float) -> pd.DataFrame:
    _ = mtime
    df = _leer_csv(Path(path))
    if df.empty:
        return df
    for c in COLS_RENIV + ["Total_Renivelacion", "Total_Penalizaciones", "Cantidad_Forfaits"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    if "Posicion" in df.columns:
        df["Posicion"] = pd.to_numeric(df["Posicion"], errors="coerce").fillna(0).astype(int)
    df["Institucion"] = df["Tira"].map(institucion_desde_tira)
    return df


@st.cache_data(ttl=120)
def _cargar_baseline(path: str, mtime: float) -> pd.DataFrame:
    _ = mtime
    df = _leer_csv(Path(path))
    if df.empty or "Tira" not in df.columns:
        return df
    for c in COLS_BASE + ["Total_Baseline"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round(0).astype(int)
    df["Institucion"] = df["Tira"].map(institucion_desde_tira)
    df = df.sort_values("Total_Baseline", ascending=False).reset_index(drop=True)
    df.insert(0, "Posicion_Baseline", range(1, len(df) + 1))
    return df


def _comparativa(reniv: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    if reniv.empty or base.empty:
        return pd.DataFrame()
    a = reniv[["Tira", "Posicion", "Total_Renivelacion"] + COLS_RENIV].rename(
        columns={"Posicion": "Pos_Reniv", "Total_Renivelacion": "Pts_Reniv"}
    )
    b = base[["Tira", "Posicion_Baseline", "Total_Baseline"]].rename(
        columns={"Posicion_Baseline": "Pos_Baseline", "Total_Baseline": "Pts_Baseline"}
    )
    cmp = a.merge(b, on="Tira", how="outer")
    fill = max(cmp["Pos_Reniv"].max(skipna=True) or 0, cmp["Pos_Baseline"].max(skipna=True) or 0, len(cmp)) + 1
    cmp["Pos_Reniv"] = cmp["Pos_Reniv"].fillna(fill).astype(int)
    cmp["Pos_Baseline"] = cmp["Pos_Baseline"].fillna(fill).astype(int)
    cmp["Pts_Reniv"] = cmp["Pts_Reniv"].fillna(0).astype(int)
    cmp["Pts_Baseline"] = cmp["Pts_Baseline"].fillna(0).astype(int)
    cmp["Delta_Posicion"] = cmp["Pos_Baseline"] - cmp["Pos_Reniv"]
    cmp["Delta_Puntos"] = cmp["Pts_Reniv"] - cmp["Pts_Baseline"]
    if "Cantidad_Forfaits" in reniv.columns:
        cmp = cmp.merge(reniv[["Tira", "Cantidad_Forfaits", "Total_Penalizaciones"]], on="Tira", how="left")
    return cmp.sort_values("Pos_Reniv").reset_index(drop=True)


def _grafico_aporte_bandas(df: pd.DataFrame, tira: str, prefijo: str) -> go.Figure:
    cols = [
        columna_puntos(prefijo, c)
        for c in CATEGORIAS_COMPETITIVAS
        if columna_puntos(prefijo, c) in df.columns
    ]
    row = df[df["Tira"] == tira]
    if row.empty:
        return go.Figure()
    valores = [int(row[c].iloc[0]) for c in cols]
    etiquetas = [LABEL_CATEGORIA.get(c, c.replace(f"{prefijo}_", "").replace("_", " ")) for c in cols]
    fig = go.Figure(data=[go.Bar(x=etiquetas, y=valores, marker_color="#2563eb")])
    fig.update_layout(
        title=f"Aporte por categoría — {tira}",
        yaxis_title="Puntos",
        height=360,
    )
    return fig


def main() -> None:
    st.set_page_config(page_title="Renivelación Tiras", layout="wide")
    st.title("Renivelación por Tira (2023–2026)")

    path_reniv = OUTPUT_RANKING
    path_base = OUTPUT_BASELINE

    if not path_reniv.is_file():
        st.error(
            f"No existe {path_reniv}. Ejecutá:\n\n"
            "`python -m analisis.renivelacion_tiras`"
        )
        st.stop()

    reniv = _cargar_renivelacion(str(path_reniv), path_reniv.stat().st_mtime)
    base = (
        _cargar_baseline(str(path_base), path_base.stat().st_mtime)
        if path_base.is_file()
        else pd.DataFrame()
    )

    with st.sidebar:
        st.subheader("Filtros")
        buscar = st.text_input("Buscar tira o institución", "").strip().upper()
        top_n = st.slider("Top N en gráficos", 5, 40, 15)
        solo_con_forfait = st.checkbox("Solo tiras con forfaits", value=False)

    df = reniv.copy()
    if buscar:
        df = df[
            df["Tira"].str.upper().str.contains(buscar, na=False)
            | df["Institucion"].str.upper().str.contains(buscar, na=False)
        ]
    if solo_con_forfait and "Cantidad_Forfaits" in df.columns:
        df = df[df["Cantidad_Forfaits"] > 0]

    tab_rank, tab_cmp, tab_det, tab_info = st.tabs(
        ["Ranking renivelación", "Reniv vs Baseline", "Detalle de tira", "Cómo se calcula"]
    )

    with tab_rank:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Tiras", len(reniv))
        with c2:
            ff = int(reniv["Cantidad_Forfaits"].sum()) if "Cantidad_Forfaits" in reniv.columns else 0
            st.metric("Forfaits totales", ff)
        with c3:
            st.metric("Líder", reniv["Tira"].iloc[0] if len(reniv) else "—")
        with c4:
            st.metric("Puntos líder", int(reniv["Total_Renivelacion"].iloc[0]) if len(reniv) else 0)

        st.subheader("Tabla de ranking")
        columnas_show = [
            c
            for c in [
                "Posicion",
                "Tira",
                "Institucion",
                *COLS_RENIV,
                "Cantidad_Forfaits",
                "Total_Penalizaciones",
                "Total_Renivelacion",
            ]
            if c in df.columns
        ]
        st.dataframe(
            df[columnas_show],
            use_container_width=True,
            hide_index=True,
            height=min(700, 40 + len(df) * 35),
        )

        top = reniv.head(top_n)
        fig_top = px.bar(
            top,
            x="Total_Renivelacion",
            y="Tira",
            orientation="h",
            title=f"Top {top_n} — Total renivelación",
            labels={"Total_Renivelacion": "Puntos", "Tira": ""},
        )
        fig_top.update_layout(yaxis={"categoryorder": "total ascending"}, height=420)
        st.plotly_chart(fig_top, use_container_width=True)

        if COLS_RENIV[0] in reniv.columns:
            melt = top.melt(
                id_vars=["Tira"],
                value_vars=[c for c in COLS_RENIV if c in top.columns],
                var_name="Categoria",
                value_name="Puntos",
            )
            melt["Categoria"] = melt["Categoria"].map(
                lambda x: LABEL_CATEGORIA.get(x, x.replace("Pts_Aportados_", "").replace("_", " "))
            )
            fig_stack = px.bar(
                melt,
                x="Tira",
                y="Puntos",
                color="Categoria",
                title=f"Composición por categoría (top {top_n})",
                barmode="stack",
            )
            fig_stack.update_layout(xaxis_tickangle=-35, height=420)
            st.plotly_chart(fig_stack, use_container_width=True)

    with tab_cmp:
        if base.empty:
            st.warning("Falta Ranking_Tiras_Baseline_2026.csv. Regenerá con `python -m analisis.renivelacion_tiras`.")
        else:
            cmp = _comparativa(reniv, base)
            if buscar:
                cmp = cmp[cmp["Tira"].str.upper().str.contains(buscar, na=False)]
            st.subheader("Comparativa de posiciones")
            st.caption(
                "Delta_Posicion = Pos_Baseline − Pos_Reniv → positivo = sube en renivelación."
            )
            st.dataframe(
                cmp[
                    [
                        c
                        for c in [
                            "Tira",
                            "Pos_Baseline",
                            "Pos_Reniv",
                            "Delta_Posicion",
                            "Pts_Baseline",
                            "Pts_Reniv",
                            "Delta_Puntos",
                            "Cantidad_Forfaits",
                            "Total_Penalizaciones",
                        ]
                        if c in cmp.columns
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

            sube = cmp.nlargest(top_n, "Delta_Posicion")
            baja = cmp.nsmallest(top_n, "Delta_Posicion")
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("**Más mejoras de posición (reniv vs GES)**")
                st.dataframe(sube[["Tira", "Delta_Posicion", "Pts_Reniv"]], hide_index=True)
            with col_b:
                st.markdown("**Mayor caída de posición**")
                st.dataframe(baja[["Tira", "Delta_Posicion", "Pts_Reniv"]], hide_index=True)

            scatter = cmp.head(min(len(cmp), 80))
            fig_sc = px.scatter(
                scatter,
                x="Pts_Baseline",
                y="Pts_Reniv",
                hover_name="Tira",
                size="Cantidad_Forfaits" if "Cantidad_Forfaits" in scatter.columns else None,
                title="Puntos baseline vs renivelación",
                labels={"Pts_Baseline": "Baseline GES", "Pts_Reniv": "Renivelación"},
            )
            max_p = max(scatter["Pts_Baseline"].max(), scatter["Pts_Reniv"].max(), 1)
            fig_sc.add_trace(
                go.Scatter(
                    x=[0, max_p],
                    y=[0, max_p],
                    mode="lines",
                    line=dict(dash="dash", color="gray"),
                    showlegend=False,
                )
            )
            st.plotly_chart(fig_sc, use_container_width=True)

    with tab_det:
        opciones = sorted(reniv["Tira"].unique())
        tira_sel = st.selectbox("Elegí una tira", opciones, index=0)
        row = reniv[reniv["Tira"] == tira_sel]
        if row.empty:
            st.info("Sin datos.")
        else:
            r = row.iloc[0]
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Posición", int(r["Posicion"]))
            m2.metric("Total renivelación", int(r["Total_Renivelacion"]))
            m3.metric("Forfaits", int(r.get("Cantidad_Forfaits", 0)))
            m4.metric("Penalizaciones", int(r.get("Total_Penalizaciones", 0)))

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.plotly_chart(
                    _grafico_aporte_bandas(reniv, tira_sel, "Pts_Aportados"),
                    use_container_width=True,
                )
            with col_g2:
                if not base.empty and tira_sel in base["Tira"].values:
                    st.plotly_chart(
                        _grafico_aporte_bandas(base, tira_sel, "Pts_Baseline"),
                        use_container_width=True,
                    )
                else:
                    st.caption("Sin baseline para esta tira.")

            st.markdown(
                f"**Institución:** {r.get('Institucion', institucion_desde_tira(tira_sel))}  \n"
                f"Fórmula: Total = INFANTILES+CADETES+JUVENILES+LIGA PROXIMO − forfaits×1000"
            )

            hermanas = reniv[reniv["Institucion"] == r["Institucion"]].sort_values("Posicion")
            if len(hermanas) > 1:
                st.subheader("Otras tiras del mismo club")
                st.dataframe(
                    hermanas[
                        ["Posicion", "Tira", "Total_Renivelacion", "Cantidad_Forfaits"]
                    ],
                    hide_index=True,
                )

    with tab_info:
        st.markdown(
            """
### Pipeline incremental
1. **Histórico 2023–2025** congelado en `Data/procesada/renivelacion/`
2. **2026** se suma solo desde `partidos_2026.csv`

### Renivelación
- Puntos por partido: `peso_año × peso_etapa × peso_nivel × (BP + ORP)`
- Columnas = buckets **U13→INFANTILES, U15→CADETES, U17→JUVENILES, U19→LIGA PROXIMO** (mapeo distinto en CSV 2023-24 vs 2025+; ver docs)
- Cada forfait **0-20** (cualquier categoría, incl. Mini/Premini) = **−1000** a la tira

### Tira A vs Tira B
Son claves distintas (`PEDRO ECHAGUE A` ≠ `PEDRO ECHAGUE B`); puntos y forfaits no se mezclan.

Documentación: `docs/RENIVELACION_TIRAS.md`

```powershell
python -m analisis.renivelacion_tiras
streamlit run visualizaciones/renivelacion_tiras_streamlit.py
```
            """
        )
        if ACUM_HIST.is_file():
            st.success(f"Caché histórico: `{ACUM_HIST}`")
        if path_reniv.is_file():
            st.success(f"Ranking actualizado: `{path_reniv}`")


if __name__ == "__main__":
    main()
