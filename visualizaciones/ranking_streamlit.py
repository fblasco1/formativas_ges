# -*- coding: utf-8 -*-
"""
Dashboard principal: ranking de renivelación por tira (2023–2026).

  streamlit run visualizaciones/ranking_streamlit.py
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
    TIPOS_MARCADOR,
    filtrar_por_tipo,
    partidos_de_equipo,
    resumen_tipos,
)
from analisis.renivelacion_tiras.ejemplo_partido import ejemplo_partido_reniv  # noqa: E402
from analisis.renivelacion_tiras.pipeline import ranking_renivelacion_para_anios  # noqa: E402
from mapeos.equipos_region import (  # noqa: E402
    REGIONES_APILADO,
    cargar_partidos_normalizados,
    equipos_detalle_region,
    mapa_region_equipos,
    tiras_en_temporada,
    totales_por_region,
)

ANIO_REGION = 2026
TEMPORADAS = list(FOCUS_YEARS)
PARTIDOS_CONSOLIDADO = resolve_partidos_consolidado()


@st.cache_data(ttl=120)
def _partidos_df(path: str, mtime: float) -> pd.DataFrame:
    _ = mtime
    return cargar_partidos_normalizados(Path(path))


@st.cache_data(ttl=120)
def _ranking_anios(years: tuple[int, ...], partidos_mtime: float) -> pd.DataFrame:
    _ = partidos_mtime
    return ranking_renivelacion_para_anios(years)


@st.cache_data(ttl=120)
def _regiones_y_tiras_2026(path: str, mtime: float) -> tuple[dict[str, str], pd.DataFrame, frozenset[str]]:
    _ = mtime
    df = cargar_partidos_normalizados(Path(path))
    detalle = equipos_detalle_region(df, anio=ANIO_REGION)
    totales = totales_por_region(detalle)
    tiras = tiras_en_temporada(df, ANIO_REGION)
    return mapa_region_equipos(df, anio=ANIO_REGION), totales, tiras


@st.cache_data(ttl=300)
def _ejemplo_partido_cached(partidos_mtime: float) -> dict | None:
    _ = partidos_mtime
    return ejemplo_partido_reniv((2025, 2026))


def _tabla_vista(rank: pd.DataFrame, region_map: dict[str, str]) -> pd.DataFrame:
    out = rank.copy()
    out["Equipo"] = out["Tira"].astype(str)
    out["Region"] = out["Equipo"].map(region_map).fillna("")
    out["Pts"] = pd.to_numeric(out["Total_Renivelacion"], errors="coerce").fillna(0).astype(int)
    out["Posicion"] = pd.to_numeric(out["Posicion"], errors="coerce").fillna(0).astype(int)
    return out[["Posicion", "Equipo", "Region", "Pts"]].sort_values("Posicion")


def _metricas_region(totales: pd.DataFrame) -> None:
    cols = st.columns(len(REGIONES_APILADO))
    lookup = (
        totales.set_index("zona")["equipos_distintos"].to_dict()
        if not totales.empty and "zona" in totales.columns
        else {}
    )
    for col, reg in zip(cols, REGIONES_APILADO):
        col.metric(reg, int(lookup.get(reg, 0)))


def _fila_resumen_partidos(partidos: pd.DataFrame, partidos_f: pd.DataFrame) -> None:
    resumen = resumen_tipos(partidos)
    orden = list(TIPOS_MARCADOR) + [
        t for t in resumen["tipo_marcador"].tolist() if t not in TIPOS_MARCADOR
    ]
    labels = orden + ["Mostrados", "Total"]
    valores = []
    lookup = resumen.set_index("tipo_marcador")["cantidad"].to_dict() if not resumen.empty else {}
    for t in orden:
        valores.append(int(lookup.get(t, 0)))
    valores.append(len(partidos_f))
    valores.append(len(partidos))

    cols = st.columns(len(labels))
    for col, lab, val in zip(cols, labels, valores):
        col.metric(lab, val)


def _tab_como_funciona() -> None:
    st.markdown(
        """
### Qué es este ranking

- Se calcula por **tira** (ej. `PEDRO ECHAGUE A` y `PEDRO ECHAGUE B` son filas distintas).
- Solo suman puntos las categorías competitivas: **Infantiles, Cadetes, Juveniles y Liga Próximo** (U13–U21).
- **Mini / Premini**: no suman puntos al total, pero un 0-20 en contra genera **−1000** al total de la tira.
- Las **cuatro regiones** son SUR, OESTE, NORTE y CENTRO. La interconferencia es una fase, no una región.

### Fórmula por partido (renivelación)

```text
Puntos_tira = peso_año × peso_etapa × peso_nivel × (BP + ORP)
```

| Componente | Idea |
|------------|------|
| **BP** (basis points) | Depende del marcador y la diferencia (ganó/perdió, 10+, 20+ pts). 20-0 / 0-20 tienen reglas especiales. |
| **ORP** | Bonus si el rival estaba **arriba en el ranking del año anterior** (misma tira). Primer año del rango: ORP = 0. |
| **peso_año** | 2023→0,25 · 2024→0,50 · 2025→0,75 · 2026→1,00 (lo más reciente pesa más). |
| **peso_etapa / peso_nivel** | Playoff e interconferencia valen más que fase regular según la matriz FeBAMBA. |

### Total de la tira

```text
Total = Pts_Infantiles + Pts_Cadetes + Pts_Juveniles + Pts_Liga_Proximo − (forfaits × 1000)
```
        """
    )

    ej = _ejemplo_partido_cached(_mtime)
    if not ej:
        st.info("No hay partido de ejemplo disponible (cargá partidos 2025–2026).")
        return

    st.subheader("Ejemplo con un partido real (2026)")
    st.markdown(
        f"**{ej['local']}** {ej['ptsL']} – {ej['ptsV']} **{ej['visitante']}** · "
        f"{ej['fecha']} · {ej['categoria']} → bucket **{ej['bucket']}**  \n"
        f"Fase: {ej['fase']} · Ronda: {ej['ronda']} · Nivel: {ej['nivel']} · Zona: {ej['zona']}"
    )

    st.markdown("#### Basis points (BP) por marcador")
    st.markdown(
        f"- Local ganó por 2 pts → BP local **{ej['bp_local']}**, visitante **{ej['bp_visitante']}**  \n"
        "(Diferencia chica: 650 / 350 en la escala estándar.)"
    )

    st.markdown("#### ORP (según ranking de tiras 2025)")
    st.markdown(
        f"- {ej['local']}: ORP **{ej['orp_local']:.1f}**  \n"
        f"- {ej['visitante']}: ORP **{ej['orp_visitante']:.1f}**"
    )

    st.markdown("#### Pesos aplicados")
    st.markdown(
        f"- peso_año = **{ej['peso_anio']}** · peso_etapa = **{ej['peso_etapa']}** · "
        f"peso_nivel = **{ej['peso_nivel']}**  \n"
        f"- Factor = **{ej['factor']:.3f}**"
    )

    st.markdown("#### Puntos de renivelación del partido")
    filas = [
        {
            "Tira": ej["local"],
            "BP": ej["bp_local"],
            "ORP": round(ej["orp_local"], 1),
            "BP + ORP": ej["bp_local"] + ej["orp_local"],
            "× Factor": ej["factor"],
            "Puntos partido": ej["pts_reniv_local"],
        },
        {
            "Tira": ej["visitante"],
            "BP": ej["bp_visitante"],
            "ORP": round(ej["orp_visitante"], 1),
            "BP + ORP": ej["bp_visitante"] + ej["orp_visitante"],
            "× Factor": ej["factor"],
            "Puntos partido": ej["pts_reniv_visitante"],
        },
    ]
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

    st.caption(
        "Esos puntos se suman en la columna del bucket (ej. Liga Próximo). "
        "Al elegir varias temporadas, cada partido entra con el peso de su año y el ORP "
        "se encadena año a año."
    )


st.set_page_config(page_title="Ranking Renivelación", layout="wide")
st.title("Ranking de renivelación FeBAMBA")

_estado_path = ROOT / "Data" / "procesada" / "ultima_actualizacion.json"
if _estado_path.is_file():
    try:
        import json

        _est = json.loads(_estado_path.read_text(encoding="utf-8"))
        if _est.get("ok"):
            st.caption(
                f"Última actualización GES: {_est.get('ultima_ejecucion', '')[:19]} · "
                f"partidos {_est.get('temporada_activa')}: {_est.get('partidos_despues')} "
                f"(Δ {_est.get('partidos_delta', 0):+d})"
            )
        else:
            st.warning(f"Última actualización falló: {_est.get('error', 'ver logs')}")
    except (json.JSONDecodeError, OSError):
        pass

if not PARTIDOS_CONSOLIDADO.is_file():
    st.error(
        f"Falta consolidado formativas ({PARTIDOS_CONSOLIDADO}). "
        "Ejecutá: python pipelines/consolidar_temporadas.py"
    )
    st.stop()

_mtime = PARTIDOS_CONSOLIDADO.stat().st_mtime
region_map, totales_2026, tiras_2026 = _regiones_y_tiras_2026(str(PARTIDOS_CONSOLIDADO), _mtime)

tab_ranking, tab_partidos, tab_info = st.tabs(
    ["Ranking", "Partidos por equipo", "Cómo funciona"]
)

with tab_ranking:
    st.caption(
        f"Equipos por región (**{ANIO_REGION}**): SUR, OESTE, NORTE y CENTRO. "
        "La interconferencia no es región; la región de cada tira sale de sus partidos zonales."
    )
    _metricas_region(totales_2026)

    st.divider()

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        temporadas_sel = st.multiselect(
            "Temporadas incluidas",
            options=TEMPORADAS,
            default=TEMPORADAS,
            format_func=str,
            help="Se acumulan en orden cronológico (ORP usa el ranking del año anterior).",
        )
    with c2:
        regiones_opts = ["Todas"] + list(REGIONES_APILADO)
        region_filtro = st.selectbox("Filtrar por región", regiones_opts)
    with c3:
        solo_2026 = st.checkbox(
            f"Solo tiras en {ANIO_REGION}",
            value=False,
            help="Oculta tiras que no jugaron ningún partido en la temporada 2026.",
        )

    if not temporadas_sel:
        st.warning("Seleccioná al menos una temporada.")
        st.stop()

    years = tuple(sorted(temporadas_sel))
    with st.spinner(f"Calculando ranking {years[0]}–{years[-1]}…"):
        rank_raw = _ranking_anios(years, _mtime)

    if rank_raw.empty:
        st.warning("Sin datos para las temporadas elegidas.")
        st.stop()

    vista = _tabla_vista(rank_raw, region_map)
    if solo_2026:
        vista = vista[vista["Equipo"].isin(tiras_2026)]
    if region_filtro != "Todas":
        vista = vista[vista["Region"] == region_filtro]

    vista = vista.reset_index(drop=True)
    vista["Posicion"] = range(1, len(vista) + 1)

    etiqueta = (
        f"Ranking {years[0]}" if len(years) == 1 else f"Ranking acumulado {years[0]}–{years[-1]}"
    )
    extra = f" · solo tiras {ANIO_REGION}" if solo_2026 else ""
    st.subheader(etiqueta)
    st.caption(f"{len(vista)} tiras{extra} · Puntos = Total_Renivelacion (forfaits incluidos)")

    st.dataframe(
        vista,
        use_container_width=True,
        hide_index=True,
        height=min(800, 40 + len(vista) * 35),
        column_config={
            "Posicion": st.column_config.NumberColumn("Posición", format="%d"),
            "Equipo": st.column_config.TextColumn("Equipo"),
            "Region": st.column_config.TextColumn("Región"),
            "Pts": st.column_config.NumberColumn("Pts", format="%d"),
        },
    )

with tab_partidos:
    df_p = _partidos_df(str(PARTIDOS_CONSOLIDADO), _mtime)
    equipos_p = sorted(set(df_p["local"].astype(str)) | set(df_p["visitante"].astype(str)))
    equipos_p = [e for e in equipos_p if e and e != "nan"]

    with st.expander("Marcadores 0-0, 20-0 y 0-20"):
        st.markdown(
            "- **0-20 en contra**: tu equipo en 0 → no presentación.\n"
            "- **20-0 a favor**: rival en 0 → tu equipo presentó.\n"
            "- **0-0**: revisar acta (a menudo doble NP).\n"
            "- **Partido normal**: partido jugado con regla FeBAMBA."
        )

    c1, c2, c3 = st.columns(3)
    with c1:
        equipo_p = st.selectbox("Equipo", equipos_p, key="part_equipo")
    with c2:
        anio_p = st.selectbox("Temporada", ["Todas"] + [str(y) for y in TEMPORADAS], key="part_anio")
    with c3:
        filtro_p = st.selectbox("Filtrar marcador", FILTROS_ESPECIALES, key="part_filtro")

    anio_val = None if anio_p == "Todas" else int(anio_p)
    partidos = partidos_de_equipo(df_p, equipo_p, anio=anio_val)
    partidos_f = filtrar_por_tipo(partidos, filtro_p)

    if partidos.empty:
        st.warning("Sin partidos para esa combinación.")
    else:
        _fila_resumen_partidos(partidos, partidos_f)
        st.dataframe(partidos_f, use_container_width=True, hide_index=True)

with tab_info:
    _tab_como_funciona()
