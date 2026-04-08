import pandas as pd
from dash import Dash, html, Input, Output, State, dash_table, dcc
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import dash
from dash.dependencies import ALL

# --- 1. CARGA Y LIMPIEZA DE DATOS ---
def cargar_datos():
    df = pd.read_csv("Data/procesada/19-24.csv", sep=";")
    for col in ['zona', 'ronda', 'categoria', 'local', 'visitante', 'fase']:
        df[col] = df[col].str.strip().str.upper()
    for col in ['nivel', 'zona', 'fase', 'ronda', 'categoria', 'local', 'visitante']:
        df = df[(df[col] != "DESCONOCIDO") & (df[col] != "DESCONOCIDA")]
    df = df[~df['categoria'].isin(["MINI", "PREMINI"])]
    return df

def cargar_power_ranking():
    df_power = pd.read_csv("Data/procesada/Ranking2019-2024.csv").rename(columns={"Puntos": "Power Ranking 2019-2024"})
    return df_power.set_index('Equipo')['Power Ranking 2019-2024'].to_dict()

df = cargar_datos()
ranking_dict = cargar_power_ranking()

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

# Precalcular detalles por equipo (solo años)
detalles_por_equipo = {equipo: resumen_equipo_anio(df, equipo) for equipo in sorted(set(df['local']).union(set(df['visitante'])))}

# DataFrame solo con totales
df_totales = pd.DataFrame([resumen_equipo_general(df, equipo) for equipo in sorted(set(df['local']).union(set(df['visitante']))) if resumen_equipo_general(df, equipo)["pj"] > 0])

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

# --- 4. PREPARACIÓN DE DATOS PARA DASH ---
equipos = sorted(set(df['local']).union(set(df['visitante'])))
equipos_ordenados = sorted(equipos, key=lambda eq: ranking_dict.get(eq, -9999), reverse=True)
detalles_por_equipo = {equipo: resumen_equipo_anio(df, equipo) for equipo in equipos_ordenados}
df_totales = pd.DataFrame([resumen_equipo_general(df, equipo) for equipo in equipos_ordenados if resumen_equipo_general(df, equipo)["pj"] > 0])

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
                    {"name": "Power Ranking 2019-2024", "id": "power_ranking"}
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

app.layout = html.Div([
    html.H2("Análisis de formativas de Febamba", style={"font-size": "2.2rem", "marginBottom": "2.5rem", "textAlign": "center", "letterSpacing": "0.04em"}),
    dcc.Tabs(id="main-tabs", value="general", children=[
        dcc.Tab(label="General", value="general", children=[tab_general]),
        dcc.Tab(label="Power Ranking", value="power_ranking", children=[tab_power_ranking]),
        dcc.Tab(label="SUR", value="sur", children=[tab_sur]),
        dcc.Tab(label="OESTE", value="oeste", children=[tab_oeste]),
        dcc.Tab(label="NORTE", value="norte", children=[tab_norte]),
        dcc.Tab(label="CENTRO", value="centro", children=[tab_centro]),
    ]),
], style={"backgroundColor": "#f9f9f9"})

# --- 6. CALLBACKS ---
@app.callback(
    Output("tabla-promedios-region", "data"),
    [Input("temporada-filter-general", "value"),
     Input("fase-filter-general", "value"),
     Input("ronda-filter-general", "value"),
     Input("nivel-filter-general", "value"),
     Input("region-filter-general", "value")]
)
def update_tabla_promedios(region_sel, fase_sel, ronda_sel, nivel_sel, region_zona_sel):
    df_filtrado = df.copy()
    if region_sel and "TODAS" not in region_sel:
        df_filtrado = df_filtrado[df_filtrado['zona'].isin(region_sel)]
    if fase_sel and "TODAS" not in fase_sel:
        df_filtrado = df_filtrado[df_filtrado['fase'].isin(fase_sel)]
    if ronda_sel and "TODAS" not in ronda_sel:
        df_filtrado = df_filtrado[df_filtrado['ronda'].astype(str).isin([str(r) for r in ronda_sel])]
    if nivel_sel and "TODOS" not in nivel_sel:
        df_filtrado = df_filtrado[df_filtrado['nivel'].isin(nivel_sel)]
    if region_zona_sel and "TODAS" not in region_zona_sel:
        df_filtrado = df_filtrado[df_filtrado['zona'].isin(region_zona_sel)]
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
    df_filtrado = df.copy()
    # Filtros
    if temporada_sel and "TODAS" not in temporada_sel and 'anio' in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado['anio'].astype(str).isin([str(t) for t in temporada_sel])]
    if fase_sel and "TODAS" not in fase_sel:
        df_filtrado = df_filtrado[df_filtrado['fase'].isin(fase_sel)]
    if ronda_sel and "TODAS" not in ronda_sel:
        df_filtrado = df_filtrado[df_filtrado['ronda'].astype(str).isin([str(r) for r in ronda_sel])]
    if nivel_sel and "TODOS" not in nivel_sel:
        df_filtrado = df_filtrado[df_filtrado['nivel'].isin(nivel_sel)]
    if region_sel and "TODAS" not in region_sel:
        df_filtrado = df_filtrado[df_filtrado['zona'].isin(region_sel)]
    # Solo Interconferencia
    df_inter = df_filtrado[(df_filtrado["fase"] == "FASE REGULAR") & (df_filtrado['zona'].str.startswith("INTERCONFERENCIA"))]
    # Tabla
    data_tabla = tabla_interconferencia(df_inter)
    # Gráfico torta de diferencias de puntos en Interconferencia
    diffs = abs(df_inter['ptsL'] - df_inter['ptsV'])
    mas_40 = (diffs > 40).sum()
    mas_20 = ((diffs > 20) & (diffs <= 40)).sum()
    entre_10_20 = ((diffs > 10) & (diffs <= 20)).sum()
    menos_10 = (diffs <= 10).sum()
    labels = ["Menos de 10", "Entre 10 y 20", "Más de 20", "Más de 40"]
    values = [menos_10, entre_10_20, mas_20, mas_40]
    colores = ['#2ca02c', '#ff7f0e', '#1f77b4', '#d62728']
    fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=0.3, marker=dict(colors=colores))])
    fig.update_layout(
        title="Diferencias de puntos en Interconferencia",
        legend=dict(font=dict(size=14)),
        margin=dict(l=10, r=10, t=40, b=10),
        height=250  # <-- Cambiado de 320 a 250 para mejor ajuste vertical
    )
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
    if not ctx.triggered or ctx.triggered[0]['prop_id'].endswith('.id'):
        return get_table_data(df_totales_local)
    if not cell:
        return current_data
    row_idx = cell["row"]
    row = current_data[row_idx]
    if row.get("temporada") != "TOTAL":
        return current_data
    equipo = row["equipo"].replace("🔽", "").replace("▶️", "").strip()
    if any(r.get("equipo", "").startswith("🔽") and equipo in r.get("equipo", "") for r in current_data):
        return get_table_data(df_totales_local)
    return get_table_data(df_totales_local, expanded_equipo=equipo)

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

# --- 7. MAIN ---
if __name__ == "__main__":
    app.run(debug=True)