from __future__ import annotations

import json
from datetime import datetime, timezone
import os
from pathlib import Path

import pandas as pd
from dash import Dash, html, Input, Output, State, dash_table, dcc
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import dash
from dash.dependencies import ALL

from analisis.dashboard_zonas_helpers import (
    figura_torta_diferencias,
    figura_torta_interconferencia_vacia,
    filtrar_partidos,
    get_equipos_region_nivel_tabla,
    get_table_data,
    inferir_region_equipo,
    tabla_interconferencia,
    tabla_promedios_por_region,
)
from analisis.ranking import run_ranking_on_dataframe
from utils.logger import get_logger

# --- 1. CARGA Y LIMPIEZA DE DATOS ---
def cargar_datos():
    # Fuente única: matches_clean (parquet; fallback a CSV si no hay engine).
    try:
        df = pd.read_parquet("Data/procesada/matches_clean.parquet")
    except Exception:
        df = pd.read_csv("Data/procesada/matches_clean.csv")

    for col in ['zona', 'ronda', 'categoria', 'local', 'visitante', 'fase']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.upper()
    for col in ['nivel', 'zona', 'fase', 'ronda', 'categoria', 'local', 'visitante']:
        if col in df.columns:
            df = df[(df[col] != "DESCONOCIDO") & (df[col] != "DESCONOCIDA")]
    df = df[~df['categoria'].isin(["MINI", "PREMINI"])]
    if "is_forfeit" in df.columns:
        df = df[~df["is_forfeit"].astype(bool)]
    for col in ("ptsL", "ptsV"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    return df


_log_dash = get_logger(__name__)


def construir_power_ranking_map(df: pd.DataFrame) -> dict[str, float]:
    """
    Rating acumulativo FeBAMBA (motor FIBA adaptado) para ordenar la tabla y la columna power_ranking.
    """
    if df.empty:
        return {}
    try:
        eng = run_ranking_on_dataframe(df)
        r = eng.get_ranking()
        if r.empty or "club" not in r.columns:
            return {}
        return r.set_index("club")["rating"].astype(float).to_dict()
    except Exception as exc:
        _log_dash.warning("Ranking FeBAMBA no disponible para el dashboard: %s", exc)
        return {}


df = cargar_datos()
ranking_dict = construir_power_ranking_map(df)
df_edit = df.reset_index(drop=True).copy()
df_edit.insert(0, "_row_idx", range(len(df_edit)))


def _edit_opts_todas_str(vals: list[str]) -> list[dict[str, str]]:
    u = sorted({str(v).strip() for v in vals if str(v).strip() and str(v).strip().upper() != "NAN"})
    return [{"label": "TODAS", "value": "TODAS"}] + [{"label": v, "value": v} for v in u]


def _edit_opts_todos_str(vals: list[str]) -> list[dict[str, str]]:
    u = sorted({str(v).strip() for v in vals if str(v).strip() and str(v).strip().upper() != "NAN"})
    return [{"label": "TODOS", "value": "TODOS"}] + [{"label": v, "value": v} for v in u]


def _edit_coerce_dropdown(val: object, opts: list[dict[str, str]], default: str) -> str:
    allowed = {o["value"] for o in opts}
    if val is None:
        return default
    s = str(val).strip()
    return s if s in allowed else default


def _edit_apply_cascade(
    anio: object,
    fase: object,
    nivel: object,
    ronda: object,
    zona: object,
    categoria: object,
) -> tuple[
    list[dict[str, str]],
    str,
    list[dict[str, str]],
    str,
    list[dict[str, str]],
    str,
    list[dict[str, str]],
    str,
    list[dict[str, str]],
    str,
    pd.DataFrame,
]:
    """Temporada→fase; fase→nivel y ronda; nivel+ronda→zona; zona→categoría."""
    d_t = df_edit
    if anio and str(anio) != "TODAS":
        d_t = d_t[d_t["anio"].astype(str) == str(anio)]

    fase_opts = _edit_opts_todas_str(d_t["fase"].astype(str).tolist())
    fase_v = _edit_coerce_dropdown(fase, fase_opts, "TODAS")

    d_f = d_t if fase_v == "TODAS" else d_t[d_t["fase"].astype(str) == str(fase_v)]

    nivel_opts = _edit_opts_todos_str(d_f["nivel"].astype(str).tolist())
    ronda_opts = _edit_opts_todas_str(d_f["ronda"].astype(str).tolist())
    nivel_v = _edit_coerce_dropdown(nivel, nivel_opts, "TODOS")
    ronda_v = _edit_coerce_dropdown(ronda, ronda_opts, "TODAS")

    d_nr = d_f
    if nivel_v not in ("TODOS", "TODAS"):
        d_nr = d_nr[d_nr["nivel"].astype(str) == str(nivel_v)]
    if ronda_v != "TODAS":
        d_nr = d_nr[d_nr["ronda"].astype(str) == str(ronda_v)]

    zona_opts = _edit_opts_todas_str(d_nr["zona"].astype(str).tolist())
    zona_v = _edit_coerce_dropdown(zona, zona_opts, "TODAS")

    d_z = d_nr if zona_v == "TODAS" else d_nr[d_nr["zona"].astype(str) == str(zona_v)]
    cat_opts = _edit_opts_todas_str(d_z["categoria"].astype(str).tolist())
    cat_v = _edit_coerce_dropdown(categoria, cat_opts, "TODAS")

    d_out = d_z if cat_v == "TODAS" else d_z[d_z["categoria"].astype(str) == str(cat_v)]
    return (
        fase_opts,
        fase_v,
        nivel_opts,
        nivel_v,
        ronda_opts,
        ronda_v,
        zona_opts,
        zona_v,
        cat_opts,
        cat_v,
        d_out,
    )


# --- 2. FUNCIONES UTILITARIAS Y DE CÁLCULO ---
def resumen_equipo_general(df, equipo):
    df_eq = df[(df['local'] == equipo) | (df['visitante'] == equipo)]
    loc = df_eq[df_eq['local'] == equipo]
    vis = df_eq[df_eq['visitante'] == equipo]
    pj = len(loc) + len(vis)
    puntos_realizados = loc['ptsL'].sum() + vis['ptsV'].sum()
    puntos_recibidos = loc['ptsV'].sum() + vis['ptsL'].sum()
    ganados = (loc['ptsL'] > loc['ptsV']).sum() + (vis['ptsV'] > vis['ptsL']).sum()
    perdidos = (loc['ptsL'] < loc['ptsV']).sum() + (vis['ptsV'] < vis['ptsL']).sum()
    return {
        "equipo": equipo,
        "pj": pj,
        "ganados": ganados,
        "perdidos": perdidos,
        "diferencia": puntos_realizados - puntos_recibidos,
        "es_total": True
    }

def resumen_equipo_anio(df, equipo):
    rows = []
    for anio in sorted(df['anio'].unique()):
        df_anio = df[((df['local'] == equipo) | (df['visitante'] == equipo)) & (df['anio'] == anio)]
        if df_anio.empty:
            continue
        loc = df_anio[df_anio['local'] == equipo]
        vis = df_anio[df_anio['visitante'] == equipo]
        pj = len(loc) + len(vis)
        if pj == 0:
            continue
        puntos_realizados = loc['ptsL'].sum() + vis['ptsV'].sum()
        puntos_recibidos = loc['ptsV'].sum() + vis['ptsL'].sum()
        ganados = (loc['ptsL'] > loc['ptsV']).sum() + (vis['ptsV'] > vis['ptsL']).sum()
        perdidos = (loc['ptsL'] < loc['ptsV']).sum() + (vis['ptsV'] < vis['ptsL']).sum()
        rows.append({
            "equipo": equipo,
            "temporada": str(anio),
            "pj": pj,
            "ganados": ganados,
            "perdidos": perdidos,
            "diferencia": puntos_realizados - puntos_recibidos,
            "es_total": False
        })
    return rows

def build_df_vis(df, equipos_ordenados):
    df_vis = []
    for equipo in equipos_ordenados:
        total = resumen_equipo_general(df, equipo)
        detalle = resumen_equipo_anio(df, equipo)
        if total["pj"] > 0:
            df_vis.append(total)
            df_vis.extend(detalle)
    return pd.DataFrame(df_vis)

regiones_validas = ["SUR", "OESTE", "NORTE", "CENTRO", "INTERCONFERENCIA"]
regiones_disponibles = sorted(df['zona'].unique())
fases_disponibles = sorted(df['fase'].unique())
niveles_disponibles = sorted(df['nivel'].unique())
temporadas_disponibles = sorted(df['anio'].unique()) if 'anio' in df.columns else []
rondas_disponibles = sorted(df['ronda'].unique()) if 'ronda' in df.columns else []

# --- 3. FUNCIONES DE VISUALIZACIÓN ---
def graficos_torta_por_region(data_por_region):
    graficos = []
    colores_regiones = ['#2ca02c', '#ff7f0e', '#1f77b4', '#d62728']  # Menos de 10, Entre 10 y 20, Más de 20, Más de 40
    cols = []
    count = 0
    for region in regiones_validas:
        if region not in data_por_region:
            continue
        valores = data_por_region[region]
        colores = colores_regiones
        labels = ["Menos de 10", "Entre 10 y 20", "Más de 20", "Más de 40"]
        values = [valores.get(l, 0) for l in labels]
        fig = go.Figure(
            data=[go.Pie(
                labels=labels,
                values=values,
                hole=0.3,
                marker=dict(colors=colores)
            )]
        )
        fig.update_layout(
            title=f"Distribución de diferencias en {region}",
            legend=dict(font=dict(size=14)),
            margin=dict(l=10, r=10, t=40, b=10),
            height=320
        )
        cols.append(
            dbc.Col([
                dcc.Graph(figure=fig)
            ], width=3)
        )
        count += 1
        if count % 4 == 0:
            graficos.append(dbc.Row(cols, className="mb-4"))
            cols = []
    if cols:
        graficos.append(dbc.Row(cols, className="mb-4"))
    return graficos

# --- 4. PREPARACIÓN DE DATOS PARA DASH ---
equipos = sorted(set(df['local']).union(set(df['visitante'])))
equipos_ordenados = sorted(equipos, key=lambda eq: ranking_dict.get(eq, -9999), reverse=True)
detalles_por_equipo = {equipo: resumen_equipo_anio(df, equipo) for equipo in equipos_ordenados}
df_totales = pd.DataFrame([resumen_equipo_general(df, equipo) for equipo in equipos_ordenados if resumen_equipo_general(df, equipo)["pj"] > 0])
equipo_region_por_club = inferir_region_equipo(df)

# --- 5. LAYOUT DASH ---
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

filtros_general = dbc.Container([
    dbc.Row([
        dbc.Col([
            html.Label("Temporada", style={"font-size": "1.1rem", "marginBottom": "0.2rem"}),
            dcc.Dropdown(
                options=[{"label": "TODAS", "value": "TODAS"}] + [{"label": str(t), "value": str(t)} for t in temporadas_disponibles],
                value=["TODAS"],
                id="temporada-filter-general",
                clearable=False,
                multi=True,
                style={"font-size": "1.05rem", "minWidth": "120px"}
            ),
        ], width=2),
        dbc.Col([
            html.Label("Fase", style={"font-size": "1.1rem", "marginBottom": "0.2rem"}),
            dcc.Dropdown(
                options=[{"label": "TODAS", "value": "TODAS"}] + [{"label": f, "value": f} for f in fases_disponibles],
                value=["TODAS"],
                id="fase-filter-general",
                clearable=False,
                multi=True,
                style={"font-size": "1.05rem", "minWidth": "120px"}
            ),
        ], width=2),
        dbc.Col([
            html.Label("Ronda", style={"font-size": "1.1rem", "marginBottom": "0.2rem"}),
            dcc.Dropdown(
                options=[{"label": "TODAS", "value": "TODAS"}] + [{"label": str(r), "value": str(r)} for r in rondas_disponibles],
                value=["TODAS"],
                id="ronda-filter-general",
                clearable=False,
                multi=True,
                style={"font-size": "1.05rem", "minWidth": "120px"}
            ),
        ], width=2),
        dbc.Col([
            html.Label("Nivel", style={"font-size": "1.1rem", "marginBottom": "0.2rem"}),
            dcc.Dropdown(
                options=[{"label": "TODOS", "value": "TODOS"}] + [{"label": n, "value": n} for n in niveles_disponibles],
                value=["TODOS"],
                id="nivel-filter-general",
                clearable=False,
                multi=True,
                style={"font-size": "1.05rem", "minWidth": "120px"}
            )
        ], width=2),
        dbc.Col([
            html.Label("Región (zona)", style={"font-size": "1.1rem", "marginBottom": "0.2rem"}),
            dcc.Dropdown(
                options=[{"label": "TODAS", "value": "TODAS"}] + [{"label": z, "value": z} for z in regiones_disponibles],
                value=["TODAS"],
                id="region-filter-general",
                clearable=False,
                multi=True,
                style={"font-size": "1.05rem", "minWidth": "120px"}
            ),
        ], width=2),
    ], className="mb-4 justify-content-center g-2"),
], fluid=True, style={"paddingLeft": "0.5rem", "paddingRight": "0.5rem", "maxWidth": "1400px"})



tab_general = dbc.Container([
    filtros_general,
    dbc.Row([
        # Tabla Interconferencia y gráfico torta
        dbc.Col([
            html.H4("Actuación de las regiones en el Nivel Interconferencia", style={"marginTop": "1.5rem", "marginBottom": "1rem", "textAlign": "center"}),
            dash_table.DataTable(
                id='tabla-interconferencia-general',
                columns=[
                    {"name": "Región", "id": "Región"},
                    {"name": "PREINFANTILES", "id": "PREINFANTILES"},
                    {"name": "INFANTILES", "id": "INFANTILES"},
                    {"name": "CADETES", "id": "CADETES"},
                    {"name": "JUVENILES", "id": "JUVENILES"},
                    {"name": "TOTALES", "id": "TOTALES"},
                ],
                data=[],
                style_cell={'font-size': '1.1rem', 'textAlign': 'center'},
                style_header={'fontWeight': 'bold', 'font-size': '1.2rem', 'backgroundColor': '#e0e0e0'},
                style_table={"marginBottom": "2.5rem"},
                row_selectable='single',
            ),
        ], width=7),
        dbc.Col([
            html.H4("Diferencias de puntos en Interconferencia", style={"marginTop": "1.5rem", "marginBottom": "1rem", "textAlign": "center"}),
            html.Div(
                dcc.Graph(id="grafico-torta-interconferencia-general"),
                style={"display": "flex", "justifyContent": "center", "alignItems": "center", "height": "270px", "maxWidth": "100%"}
            ),
        ], width=5)
    ], className="mb-4 justify-content-center"),
    dbc.Row([
        dbc.Col([
            html.H4("Promedio de puntos por partido según región y categoría", style={"marginTop": "2.5rem", "marginBottom": "1rem", "textAlign": "center"}),
            dash_table.DataTable(
                id='tabla-promedios-region',
                columns=[
                    {"name": "Región", "id": "Región"},
                    {"name": "Categoría", "id": "Categoría"},
                    {"name": "Prom. ganador", "id": "Prom. ganador"},
                    {"name": "Prom. perdedor", "id": "Prom. perdedor"},
                    {"name": "Prom. diferencia", "id": "Prom. diferencia"},
                ],
                data=[],
                style_cell={'font-size': '1.1rem', 'textAlign': 'center'},
                style_header={'fontWeight': 'bold', 'font-size': '1.2rem', 'backgroundColor': '#e0e0e0'},
                style_table={"marginBottom": "2.5rem"}
            ),
        ], width=12)
    ]),
], fluid=True, style={"paddingLeft": "0.5rem", "paddingRight": "0.5rem", "maxWidth": "1400px"})

tab_power_ranking = dbc.Container([
    dbc.Row([
        dbc.Col([
            html.H4("Ranking de equipos", style={"marginTop": "2.5rem", "marginBottom": "1rem", "textAlign": "center"}),
            dash_table.DataTable(
                id='tabla',
                columns=[
                    {"name": "Posición", "id": "posicion", "presentation": "markdown"},
                    {"name": "Equipo", "id": "equipo", "presentation": "markdown"},
                    {"name": "PJ", "id": "pj"},
                    {"name": "Ganados", "id": "ganados"},
                    {"name": "Perdidos", "id": "perdidos"},
                    {"name": "Diferencia de Gol", "id": "diferencia"},
                    {"name": "Rating FeBAMBA (FIBA)", "id": "power_ranking"}
                ],
                data=[],
                style_data={
                    'font-size': '1.25rem',
                    'whiteSpace': 'normal',
                    'height': 'auto',
                },
                style_header={
                    'fontWeight': 'bold',
                    'font-size': '1.3rem',
                    'backgroundColor': '#e0e0e0'
                },
                style_cell={
                    'padding': '6px 4px',
                    'minWidth': '60px', 'width': '70px', 'maxWidth': '120px',
                    'textAlign': 'center'
                },
                style_cell_conditional=[
                    {'if': {'column_id': 'equipo'}, 'minWidth': '120px', 'width': '180px', 'maxWidth': '250px', 'textAlign': 'left'},
                    {'if': {'column_id': 'posicion'}, 'width': '60px', 'maxWidth': '70px'},
                    {'if': {'column_id': 'power_ranking'}, 'width': '90px', 'maxWidth': '100px'},
                ],
                style_data_conditional=[
                    {
                        'if': {'filter_query': '{temporada} = "TOTAL"'},
                        'fontWeight': 'bold',
                        'backgroundColor': '#f0f0f0'
                    }
                ],
                row_selectable='single',
                style_table={"marginBottom": "2.5rem"}
            ),
        ], width=12)
    ]),
], fluid=True, style={"paddingLeft": "0.5rem", "paddingRight": "0.5rem", "maxWidth": "1400px"})


# --- NUEVAS TABS POR REGIÓN ---
def build_tab_region(region):
    return dbc.Container([
        dbc.Row([
            dbc.Col([
                html.H4(f"Equipos de la región {region}", style={"marginTop": "1.5rem", "marginBottom": "1rem", "textAlign": "center"}),
                dash_table.DataTable(
                    id=f'tabla-equipos-{region.lower()}',
                    columns=[
                        {"name": "Equipo", "id": "Equipo"},
                        {"name": "Región", "id": "Región"},
                        {"name": "Nivel 1ra Fase", "id": "Nivel 1ra Fase"},
                        {"name": "Temporada", "id": "Temporada"},
                    ],
                    data=[],
                    style_cell={'font-size': '1.1rem', 'textAlign': 'center'},
                    style_header={'fontWeight': 'bold', 'font-size': '1.2rem', 'backgroundColor': '#e0e0e0'},
                    style_table={"marginBottom": "2.5rem"}
                ),
            ], width=12)
        ]),
        # Se pueden agregar más tablas o visualizaciones por región aquí
    ], fluid=True, style={"paddingLeft": "0.5rem", "paddingRight": "0.5rem", "maxWidth": "1400px"})

tab_sur = build_tab_region("SUR")
tab_oeste = build_tab_region("OESTE")
tab_norte = build_tab_region("NORTE")
tab_centro = build_tab_region("CENTRO")

tab_edicion = dbc.Container(
    [
        html.H4(
            "Edición de partidos (metadatos)",
            style={"marginTop": "1.5rem", "marginBottom": "0.75rem", "textAlign": "center"},
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.Label("Temporada → restringe fase"),
                        dcc.Dropdown(
                            id="edit-filter-anio",
                            options=[{"label": "TODAS", "value": "TODAS"}]
                            + [{"label": str(t), "value": str(t)} for t in temporadas_disponibles],
                            value="TODAS",
                            clearable=False,
                        ),
                    ],
                    width=3,
                ),
                dbc.Col(
                    [
                        html.Label("Fase → restringe nivel y ronda"),
                        dcc.Dropdown(
                            id="edit-filter-fase",
                            options=[{"label": "TODAS", "value": "TODAS"}],
                            value="TODAS",
                            clearable=False,
                        ),
                    ],
                    width=3,
                ),
                dbc.Col(
                    [
                        html.Label("Nivel → restringe zona"),
                        dcc.Dropdown(
                            id="edit-filter-nivel",
                            options=[{"label": "TODOS", "value": "TODOS"}],
                            value="TODOS",
                            clearable=False,
                        ),
                    ],
                    width=3,
                ),
                dbc.Col(
                    [
                        html.Label("Ronda"),
                        dcc.Dropdown(
                            id="edit-filter-ronda",
                            options=[{"label": "TODAS", "value": "TODAS"}],
                            value="TODAS",
                            clearable=False,
                        ),
                    ],
                    width=3,
                ),
            ],
            className="g-2",
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.Label("Zona"),
                        dcc.Dropdown(
                            id="edit-filter-zona",
                            options=[{"label": "TODAS", "value": "TODAS"}],
                            value="TODAS",
                            clearable=False,
                        ),
                    ],
                    width=3,
                ),
                dbc.Col(
                    [
                        html.Label("Categoría"),
                        dcc.Dropdown(
                            id="edit-filter-categoria",
                            options=[{"label": "TODAS", "value": "TODAS"}],
                            value="TODAS",
                            clearable=False,
                        ),
                    ],
                    width=3,
                ),
                dbc.Col(
                    [
                        html.Label("Equipo (texto)"),
                        dcc.Input(
                            id="edit-filter-equipo",
                            type="text",
                            value="",
                            debounce=True,
                            placeholder="Buscar en local o visitante…",
                            style={"width": "100%"},
                        ),
                    ],
                    width=6,
                ),
            ],
            className="g-2",
            style={"marginTop": "0.5rem"},
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.Label("Filas por página"),
                        dcc.Dropdown(
                            id="edit-page-size",
                            options=[
                                {"label": "25", "value": 25},
                                {"label": "50", "value": 50},
                                {"label": "100", "value": 100},
                                {"label": "250", "value": 250},
                            ],
                            value=50,
                            clearable=False,
                        ),
                    ],
                    width=2,
                ),
                dbc.Col(
                    [
                        html.Label("Total (según filtros)"),
                        html.Div(id="edit-total", style={"fontWeight": "bold", "paddingTop": "0.4rem"}),
                    ],
                    width=3,
                ),
            ],
            className="g-2",
            style={"marginTop": "0.5rem"},
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.Label("Navegación"),
                        html.Div(
                            [
                                dbc.ButtonGroup(
                                    [
                                        dbc.Button("« Primera", id="edit-page-first", outline=True, color="secondary", size="sm"),
                                        dbc.Button("‹ Anterior", id="edit-page-prev", outline=True, color="secondary", size="sm"),
                                        dbc.Button("Siguiente ›", id="edit-page-next", outline=True, color="secondary", size="sm"),
                                        dbc.Button("Última »", id="edit-page-last", outline=True, color="secondary", size="sm"),
                                    ],
                                    className="me-2",
                                ),
                                html.Span(
                                    id="edit-page-info",
                                    style={"verticalAlign": "middle", "fontWeight": "500"},
                                ),
                            ],
                            style={
                                "display": "flex",
                                "flexWrap": "wrap",
                                "alignItems": "center",
                                "gap": "0.5rem",
                            },
                        ),
                    ],
                    width=12,
                ),
            ],
            className="g-2",
            style={"marginTop": "0.25rem"},
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Button(
                            "Agregar filas visibles a correcciones",
                            id="edit-add-visible",
                            color="primary",
                            className="me-2",
                        ),
                        dbc.Button(
                            "Exportar correcciones (CSV + manifest)",
                            id="edit-export",
                            color="secondary",
                        ),
                        html.Span(id="edit-status", style={"marginLeft": "0.75rem"}),
                    ],
                    width=12,
                    style={"marginTop": "0.75rem", "marginBottom": "0.5rem"},
                )
            ]
        ),
        dcc.Store(id="edit-visible-rows-store"),
        dcc.Store(id="edit-correcciones-store"),
        dash_table.DataTable(
            id="edit-table",
            columns=[
                {"name": "_row_idx", "id": "_row_idx"},
                {"name": "anio", "id": "anio"},
                {"name": "categoria", "id": "categoria"},
                {"name": "fecha", "id": "fecha"},
                {"name": "local", "id": "local"},
                {"name": "ptsL", "id": "ptsL"},
                {"name": "visitante", "id": "visitante"},
                {"name": "ptsV", "id": "ptsV"},
                {"name": "fase", "id": "fase", "editable": True},
                {"name": "ronda", "id": "ronda", "editable": True},
                {"name": "nivel", "id": "nivel", "editable": True},
                {"name": "zona", "id": "zona", "editable": True},
                {"name": "grupo", "id": "grupo", "editable": True},
            ],
            data=[],
            page_action="custom",
            page_current=0,
            page_size=50,
            page_count=1,
            sort_action="custom",
            sort_mode="multi",
            editable=True,
            style_table={"overflowX": "auto", "width": "100%", "minWidth": "100%"},
            style_cell={"fontSize": "0.95rem", "padding": "6px", "textAlign": "center"},
            style_header={"fontWeight": "bold", "backgroundColor": "#e0e0e0"},
            style_cell_conditional=[
                {"if": {"column_id": "local"}, "textAlign": "left", "minWidth": "200px"},
                {"if": {"column_id": "visitante"}, "textAlign": "left", "minWidth": "200px"},
                {"if": {"column_id": "fase"}, "textAlign": "left", "minWidth": "180px"},
                {"if": {"column_id": "ronda"}, "textAlign": "left", "minWidth": "140px"},
                {"if": {"column_id": "nivel"}, "textAlign": "left", "minWidth": "120px"},
                {"if": {"column_id": "zona"}, "textAlign": "left", "minWidth": "140px"},
                {"if": {"column_id": "grupo"}, "textAlign": "left", "minWidth": "120px"},
            ],
        ),
    ],
    fluid=True,
    className="px-2 px-md-3",
    style={"maxWidth": "100%", "width": "100%"},
)

app.layout = html.Div([
    html.H2("Análisis de formativas de Febamba", style={"font-size": "2.2rem", "marginBottom": "2.5rem", "textAlign": "center", "letterSpacing": "0.04em"}),
    dcc.Tabs(
        id="main-tabs",
        value="general",
        children=[
            dcc.Tab(label="General", value="general", children=[tab_general]),
            dcc.Tab(label="Ranking FeBAMBA", value="power_ranking", children=[tab_power_ranking]),
            dcc.Tab(label="Edición", value="edicion", children=[tab_edicion]),
            dcc.Tab(label="SUR", value="sur", children=[tab_sur]),
            dcc.Tab(label="OESTE", value="oeste", children=[tab_oeste]),
            dcc.Tab(label="NORTE", value="norte", children=[tab_norte]),
            dcc.Tab(label="CENTRO", value="centro", children=[tab_centro]),
        ],
        style={"width": "100%"},
        content_style={"width": "100%", "maxWidth": "100%"},
    ),
], style={"backgroundColor": "#f9f9f9", "width": "100%", "minHeight": "100vh", "boxSizing": "border-box"})

# --- 6. CALLBACKS ---
@app.callback(
    Output("tabla-promedios-region", "data"),
    [Input("temporada-filter-general", "value"),
     Input("fase-filter-general", "value"),
     Input("ronda-filter-general", "value"),
     Input("nivel-filter-general", "value"),
     Input("region-filter-general", "value")]
)
def update_tabla_promedios(temporada_sel, fase_sel, ronda_sel, nivel_sel, region_zona_sel):
    df_filtrado = filtrar_partidos(
        df, temporada_sel, fase_sel, ronda_sel, nivel_sel, region_zona_sel
    )
    return tabla_promedios_por_region(df_filtrado)

@app.callback(
    [Output("tabla-interconferencia-general", "data"),
     Output("grafico-torta-interconferencia-general", "figure")],
    [Input("temporada-filter-general", "value"),
     Input("fase-filter-general", "value"),
     Input("ronda-filter-general", "value"),
     Input("nivel-filter-general", "value"),
     Input("region-filter-general", "value")]
)
def update_interconferencia_general(temporada_sel, fase_sel, ronda_sel, nivel_sel, region_sel):
    df_filtrado = filtrar_partidos(
        df, temporada_sel, fase_sel, ronda_sel, nivel_sel, region_sel
    )
    zona_s = df_filtrado["zona"].astype(str)
    df_inter = df_filtrado[
        (df_filtrado["fase"] == "FASE REGULAR") & (zona_s.str.startswith("INTERCONFERENCIA"))
    ]
    data_tabla = tabla_interconferencia(df_inter, equipo_region_por_club)
    if df_inter.empty:
        return data_tabla, figura_torta_interconferencia_vacia()
    diffs = (df_inter["ptsL"] - df_inter["ptsV"]).abs()
    fig = figura_torta_diferencias(diffs)
    return data_tabla, fig

@app.callback(
    Output("tabla", "data"),
    [Input("tabla", "active_cell"),
     Input("tabla", "id")],
    State("tabla", "data")
)
def unified_callback(cell, _id, current_data):
    ctx = dash.callback_context
    df_totales_local = df_totales.copy()
    if not ctx.triggered or ctx.triggered[0]["prop_id"].endswith(".id"):
        return get_table_data(df_totales_local, detalles_por_equipo, ranking_dict)
    if not cell:
        return current_data
    row_idx = cell["row"]
    row = current_data[row_idx]
    if row.get("temporada") != "TOTAL":
        return current_data
    equipo = row["equipo"].replace("🔽", "").replace("▶️", "").strip()
    if any(
        r.get("equipo", "").startswith("🔽") and equipo in r.get("equipo", "")
        for r in current_data
    ):
        return get_table_data(df_totales_local, detalles_por_equipo, ranking_dict)
    return get_table_data(
        df_totales_local, detalles_por_equipo, ranking_dict, expanded_equipo=equipo
    )

@app.callback(
    Output('tabla-equipos-sur', 'data'),
    [Input('temporada-filter-general', 'value'),
     Input('fase-filter-general', 'value'),
     Input('nivel-filter-general', 'value')]
)
def update_tabla_equipos_sur(temporada_sel, fase_sel, nivel_sel):
    return get_equipos_region_nivel_tabla(df, "SUR", temporada_sel, fase_sel, nivel_sel)

@app.callback(
    Output('tabla-equipos-oeste', 'data'),
    [Input('temporada-filter-general', 'value'),
     Input('fase-filter-general', 'value'),
     Input('nivel-filter-general', 'value')]
)
def update_tabla_equipos_oeste(temporada_sel, fase_sel, nivel_sel):
    return get_equipos_region_nivel_tabla(df, "OESTE", temporada_sel, fase_sel, nivel_sel)

@app.callback(
    Output('tabla-equipos-norte', 'data'),
    [Input('temporada-filter-general', 'value'),
     Input('fase-filter-general', 'value'),
     Input('nivel-filter-general', 'value')]
)
def update_tabla_equipos_norte(temporada_sel, fase_sel, nivel_sel):
    return get_equipos_region_nivel_tabla(df, "NORTE", temporada_sel, fase_sel, nivel_sel)

@app.callback(
    Output('tabla-equipos-centro', 'data'),
    [Input('temporada-filter-general', 'value'),
     Input('fase-filter-general', 'value'),
     Input('nivel-filter-general', 'value')]
)
def update_tabla_equipos_centro(temporada_sel, fase_sel, nivel_sel):
    return get_equipos_region_nivel_tabla(df, "CENTRO", temporada_sel, fase_sel, nivel_sel)

@app.callback(
    Output("edit-filter-fase", "options"),
    Output("edit-filter-fase", "value"),
    Output("edit-filter-nivel", "options"),
    Output("edit-filter-nivel", "value"),
    Output("edit-filter-ronda", "options"),
    Output("edit-filter-ronda", "value"),
    Output("edit-filter-zona", "options"),
    Output("edit-filter-zona", "value"),
    Output("edit-filter-categoria", "options"),
    Output("edit-filter-categoria", "value"),
    Input("edit-filter-anio", "value"),
    Input("edit-filter-fase", "value"),
    Input("edit-filter-nivel", "value"),
    Input("edit-filter-ronda", "value"),
    Input("edit-filter-zona", "value"),
    Input("edit-filter-categoria", "value"),
)
def edit_cascade_dropdowns(anio, fase, nivel, ronda, zona, categoria):
    """Cascada: temporada→fase; fase→nivel y ronda; nivel+ronda→zona; zona→categoría."""
    out = _edit_apply_cascade(anio, fase, nivel, ronda, zona, categoria)
    return out[0], out[1], out[2], out[3], out[4], out[5], out[6], out[7], out[8], out[9]


@app.callback(
    Output("edit-table", "data"),
    Output("edit-visible-rows-store", "data"),
    Output("edit-table", "page_count"),
    Output("edit-table", "page_current"),
    Output("edit-table", "page_size"),
    Output("edit-total", "children"),
    Output("edit-page-info", "children"),
    Output("edit-page-first", "disabled"),
    Output("edit-page-prev", "disabled"),
    Output("edit-page-next", "disabled"),
    Output("edit-page-last", "disabled"),
    Input("edit-filter-anio", "value"),
    Input("edit-filter-fase", "value"),
    Input("edit-filter-nivel", "value"),
    Input("edit-filter-ronda", "value"),
    Input("edit-filter-zona", "value"),
    Input("edit-filter-categoria", "value"),
    Input("edit-filter-equipo", "value"),
    Input("edit-page-size", "value"),
    Input("edit-table", "sort_by"),
    Input("edit-page-first", "n_clicks"),
    Input("edit-page-prev", "n_clicks"),
    Input("edit-page-next", "n_clicks"),
    Input("edit-page-last", "n_clicks"),
    State("edit-table", "page_current"),
)
def edit_update_table(
    anio,
    fase,
    nivel,
    ronda,
    zona,
    categoria,
    equipo_texto,
    page_size,
    sort_by,
    _nf,
    _np,
    _nn,
    _nl,
    page_current,
):
    *_, d = _edit_apply_cascade(anio, fase, nivel, ronda, zona, categoria)

    if equipo_texto:
        q = str(equipo_texto).strip().upper()
        if q:
            d = d[
                d["local"].astype(str).str.contains(q, na=False)
                | d["visitante"].astype(str).str.contains(q, na=False)
            ]

    # Ordenamiento (multi-columna) desde el DataTable.
    if sort_by:
        cols = [x.get("column_id") for x in sort_by if x.get("column_id")]
        asc = [x.get("direction", "asc") == "asc" for x in sort_by]
        cols = [c for c in cols if c in d.columns]
        if cols:
            d = d.sort_values(cols, ascending=asc[: len(cols)], kind="mergesort")

    total = int(len(d))
    try:
        ps = int(page_size or 50)
    except Exception:
        ps = 50

    page_count = max(1, (total + ps - 1) // ps)

    try:
        cur = int(page_current) if page_current is not None else 0
    except Exception:
        cur = 0

    ctx_cb = dash.callback_context
    trig = ctx_cb.triggered_id
    trig_prop: str | None = None
    if ctx_cb.triggered:
        prop_id_full = str(ctx_cb.triggered[0].get("prop_id", ""))
        if "." in prop_id_full:
            trig_prop = prop_id_full.rsplit(".", 1)[-1]

    reset_ids = {
        "edit-filter-anio",
        "edit-filter-fase",
        "edit-filter-nivel",
        "edit-filter-ronda",
        "edit-filter-zona",
        "edit-filter-categoria",
        "edit-filter-equipo",
        "edit-page-size",
    }
    if trig in reset_ids:
        page_idx = 0
    elif trig == "edit-page-first":
        page_idx = 0
    elif trig == "edit-page-prev":
        page_idx = max(0, cur - 1)
    elif trig == "edit-page-next":
        page_idx = min(page_count - 1, cur + 1)
    elif trig == "edit-page-last":
        page_idx = page_count - 1
    elif trig_prop == "sort_by":
        page_idx = cur
    else:
        page_idx = cur

    if page_idx >= page_count:
        page_idx = max(0, page_count - 1)

    start = page_idx * ps
    end = start + ps
    d = d.iloc[start:end].copy()
    cols = [
        "_row_idx",
        "anio",
        "categoria",
        "fecha",
        "local",
        "ptsL",
        "visitante",
        "ptsV",
        "fase",
        "ronda",
        "nivel",
        "zona",
        "grupo",
    ]
    rows = d[cols].to_dict("records")
    fila_desde = start + 1 if total else 0
    fila_hasta = min(start + len(rows), total)
    info = (
        f"Página {page_idx + 1} de {page_count} · filas {fila_desde}–{fila_hasta} de {total:,}".replace(",", ".")
    )
    dis_first = page_idx <= 0
    dis_prev = page_idx <= 0
    dis_next = page_idx >= page_count - 1
    dis_last = page_idx >= page_count - 1
    return (
        rows,
        rows,
        page_count,
        page_idx,
        ps,
        f"{total:,}".replace(",", "."),
        info,
        dis_first,
        dis_prev,
        dis_next,
        dis_last,
    )


@app.callback(
    Output("edit-correcciones-store", "data"),
    Output("edit-status", "children"),
    Input("edit-add-visible", "n_clicks"),
    State("edit-table", "data"),
    State("edit-correcciones-store", "data"),
    prevent_initial_call=True,
)
def edit_add_visible_to_correcciones(_n, table_rows, store):
    if not table_rows:
        return store, "No hay filas visibles para agregar."
    existing = store or []
    existing_by_idx = {int(r["_row_idx"]): r for r in existing if "_row_idx" in r}

    # Normalizamos a esquema del script: _row_idx + columnas de verificación + metadatos.
    nuevas = 0
    for r in table_rows:
        try:
            idx = int(r["_row_idx"])
        except Exception:
            continue
        base = df_edit.iloc[idx]
        row_out = {
            "_row_idx": idx,
            "anio": int(base["anio"]) if pd.notna(base["anio"]) else base["anio"],
            "categoria": str(base["categoria"]),
            "fecha": base.get("fecha", ""),
            "local": str(base["local"]),
            "visitante": str(base["visitante"]),
            "ptsL": int(base["ptsL"]) if pd.notna(base["ptsL"]) else base["ptsL"],
            "ptsV": int(base["ptsV"]) if pd.notna(base["ptsV"]) else base["ptsV"],
            "fase": r.get("fase", ""),
            "ronda": r.get("ronda", ""),
            "nivel": r.get("nivel", ""),
            "zona": r.get("zona", ""),
            "grupo": r.get("grupo", ""),
        }
        if idx not in existing_by_idx:
            nuevas += 1
        existing_by_idx[idx] = row_out

    merged = [existing_by_idx[k] for k in sorted(existing_by_idx)]
    return merged, f"Correcciones acumuladas: {len(merged)} filas (+{nuevas})."


@app.callback(
    Output("edit-status", "children", allow_duplicate=True),
    Input("edit-export", "n_clicks"),
    State("edit-correcciones-store", "data"),
    prevent_initial_call=True,
)
def edit_export_correcciones(_n, store):
    filas = store or []
    out_dir = Path("outputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "correcciones_metadatos.csv"
    man_path = out_dir / "correcciones_metadatos.manifest.json"

    df_out = pd.DataFrame(filas)
    # Asegurar columnas clave en orden amigable.
    cols = [
        "_row_idx",
        "anio",
        "categoria",
        "fecha",
        "local",
        "visitante",
        "ptsL",
        "ptsV",
        "fase",
        "ronda",
        "nivel",
        "zona",
        "grupo",
    ]
    for c in cols:
        if c not in df_out.columns:
            df_out[c] = ""
    df_out = df_out[cols]
    df_out.to_csv(csv_path, index=False, encoding="utf-8-sig")

    payload = {
        "version": 1,
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Data/procesada/matches_clean.parquet",
        "row_indices": sorted({int(x["_row_idx"]) for x in filas if "_row_idx" in x}),
        "nota": "Editar fase/ronda/nivel/zona/grupo y aplicar con scripts/corregir_metadatos_partidos.py fusionar.",
    }
    man_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"Exportado: {csv_path.as_posix()} (+ manifest). Filas: {len(df_out)}."

# --- 7. MAIN ---
if __name__ == "__main__":
    port = int(os.getenv("DASH_PORT", "8050"))
    app.run(debug=True, port=port)