import pandas as pd
from dash import Dash, html, Input, Output, State, dash_table, dcc
import dash_bootstrap_components as dbc
import plotly.graph_objs as go

# Cargar y limpiar datos
df = pd.read_csv(
    "Data/procesada/19-24.csv",
    sep=";"
)

df['zona'] = df['zona'].str.strip().str.upper()
df['categoria'] = df['categoria'].str.strip().str.upper()
df['local'] = df['local'].str.strip().str.upper()
df['visitante'] = df['visitante'].str.strip().str.upper()
df['fase'] = df['fase'].str.strip().str.upper()
for col in ['nivel', 'zona', 'fase', 'ronda', 'categoria', 'local', 'visitante']:
    df = df[(df[col] != "DESCONOCIDO") & (df[col] != "DESCONOCIDA")]
df = df[~df['categoria'].isin(["MINI", "PREMINI"])]

# Cargar Power Ranking
df_power = pd.read_csv(
    "Data/procesada/Ranking2019-2024.csv"
).rename(columns={"Puntos": "Power Ranking 2019-2024"})

ranking_dict = df_power.set_index('Equipo')['Power Ranking 2019-2024'].to_dict()

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

# --- Generar DataFrame visualización ---
equipos = sorted(set(df['local']).union(set(df['visitante'])))
equipos_ordenados = sorted(
    equipos,
    key=lambda eq: ranking_dict.get(eq, -9999),
    reverse=True
)

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
detalles_por_equipo = {}
for equipo in equipos_ordenados:
    detalles_por_equipo[equipo] = resumen_equipo_anio(df, equipo)

# DataFrame solo con totales
df_totales = []
for equipo in equipos_ordenados:
    total = resumen_equipo_general(df, equipo)
    if total["pj"] > 0:
        df_totales.append(total)
df_totales = pd.DataFrame(df_totales)

# Calcular diferencias por región SOLO para regiones válidas y con filtro de fase
regiones_validas = ["SUR", "OESTE", "NORTE", "CENTRO","INTERCONFERENCIA"]

def calcular_diferencias_por_region(df, fase_sel="TODAS"):
    data_por_region = {}
    for region in regiones_validas:
        df_region = df[df['zona'] == region]
        if fase_sel != "TODAS":
            df_region = df_region[df_region['fase'] == fase_sel]
        if df_region.empty:
            continue
        diffs = abs(df_region['ptsL'] - df_region['ptsV'])
        mas_40 = (diffs > 40).sum()
        mas_20 = ((diffs > 20) & (diffs <= 40)).sum()
        entre_10_20 = ((diffs > 10) & (diffs <= 20)).sum()
        menos_10 = (diffs <= 10).sum()
        data_por_region[region] = {
            "Más de 40": mas_40,
            "Más de 20": mas_20,
            "Entre 10 y 20": entre_10_20,
            "Menos de 10": menos_10
        }
    return data_por_region

def graficos_torta_por_region(data_por_region):
    graficos = []
    # Mismos colores para todas las regiones (incluyendo INTERCONFERENCIA)
    colores_regiones = ['#2ca02c', '#ff7f0e', '#1f77b4', '#d62728']  # Menos de 10, Entre 10 y 20, Más de 20, Más de 40

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
        graficos.append(
            dbc.Col([
                dcc.Graph(figure=fig)
            ], width=3)
        )
    return graficos

# --- TABLA PROMEDIOS POR REGIÓN ---
def tabla_promedios_por_region(df):
    regiones = ["SUR", "OESTE", "NORTE", "CENTRO"]
    rows = []
    for region in regiones:
        df_region = df[df['zona'] == region]
        if df_region.empty:
            rows.append({"Región": region, "Prom. ganador": "-", "Prom. perdedor": "-"})
            continue
        puntos_ganador = []
        puntos_perdedor = []
        for _, row in df_region.iterrows():
            if row['ptsL'] > row['ptsV']:
                puntos_ganador.append(row['ptsL'])
                puntos_perdedor.append(row['ptsV'])
            else:
                puntos_ganador.append(row['ptsV'])
                puntos_perdedor.append(row['ptsL'])
        rows.append({
            "Región": region,
            "Prom. ganador": f"{pd.Series(puntos_ganador).mean():.1f}",
            "Prom. perdedor": f"{pd.Series(puntos_perdedor).mean():.1f}"
        })
    return rows

# --- TABLA INTERCONFERENCIA CON DETALLE POR EQUIPO ---
def tabla_interconferencia(df, region_expandida=None):
    # Mapeo de equipo a región (solo equipos de SUR, OESTE, NORTE, CENTRO)
    equipos_region = {}
    for region in ["SUR", "OESTE", "NORTE", "CENTRO"]:
        equipos = set(df[df['zona'] == region]['local']).union(set(df[df['zona'] == region]['visitante']))
        for eq in equipos:
            equipos_region[eq] = region

    # Filtrar solo partidos de Interconferencia y Fase Regular
    df_inter = df[(df["fase"] == "FASE REGULAR") & (df['zona'] == "INTERCONFERENCIA")]

    categorias = ["PREINFANTILES", "INFANTILES", "CADETES", "JUVENILES"]
    conteo = {r: {cat: 0 for cat in categorias} for r in ["SUR", "OESTE", "NORTE", "CENTRO"]}
    conteo_totales = {r: 0 for r in ["SUR", "OESTE", "NORTE", "CENTRO"]}
    equipos_ganadores = {r: {} for r in ["SUR", "OESTE", "NORTE", "CENTRO"]}

    for _, row in df_inter.iterrows():
        # Determinar ganador
        if row['ptsL'] > row['ptsV']:
            ganador = row['local']
        else:
            ganador = row['visitante']
        region_ganador = equipos_region.get(ganador, "OTRO")
        categoria = row.get('categoria', '').strip().upper()
        if region_ganador in conteo:
            if categoria in categorias:
                conteo[region_ganador][categoria] += 1
            conteo_totales[region_ganador] += 1
            # Conteo por equipo y categoría
            if ganador not in equipos_ganadores[region_ganador]:
                equipos_ganadores[region_ganador][ganador] = {cat: 0 for cat in categorias}
                equipos_ganadores[region_ganador][ganador]['TOTALES'] = 0
            if categoria in categorias:
                equipos_ganadores[region_ganador][ganador][categoria] += 1
            equipos_ganadores[region_ganador][ganador]['TOTALES'] += 1

    # Formato para tabla
    resultado = []
    for r in ["SUR", "OESTE", "NORTE", "CENTRO"]:
        fila = {"Región": r}
        for cat in categorias:
            fila[cat] = conteo[r][cat]
        fila["TOTALES"] = conteo_totales[r]
        resultado.append(fila)
        # Si la región está expandida, agregar filas de equipos ordenados por cantidad de ganados (power ranking si hay empate)
        if region_expandida == r:
            equipos_ordenados = sorted(
                equipos_ganadores[r].items(),
                key=lambda x: (-x[1]['TOTALES'], -ranking_dict.get(x[0], -9999), x[0])
            )
            for eq, datos in equipos_ordenados:
                fila_eq = {"Región": f"   {eq}"}
                for cat in categorias:
                    fila_eq[cat] = datos[cat]
                fila_eq["TOTALES"] = datos["TOTALES"]
                resultado.append(fila_eq)
    return resultado

# Layout Dash con filtro de región y fase (sin nivel)

regiones_disponibles = sorted(df['zona'].unique())
fases_disponibles = sorted(df['fase'].unique())
niveles_disponibles = sorted(df['nivel'].unique())
temporadas_disponibles = sorted(df['anio'].unique()) if 'anio' in df.columns else []
rondas_disponibles = sorted(df['ronda'].unique()) if 'ronda' in df.columns else []


# --- NUEVO LAYOUT VISUAL ---

# --- NUEVO LAYOUT CON TABS ---
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

filtros_layout = dbc.Container([
    dbc.Row([
        dbc.Col([
            html.Label("Región", style={"font-size": "1.1rem", "marginBottom": "0.2rem"}),
            dcc.Dropdown(
                options=[{"label": "TODAS", "value": "TODAS"}] + [{"label": z, "value": z} for z in regiones_disponibles],
                value=["TODAS"],
                id="region-filter",
                clearable=False,
                multi=True,
                style={"font-size": "1.05rem", "minWidth": "120px"}
            ),
        ], width=2),
        dbc.Col([
            html.Label("Temporada", style={"font-size": "1.1rem", "marginBottom": "0.2rem"}),
            dcc.Dropdown(
                options=[{"label": "TODAS", "value": "TODAS"}] + [{"label": str(t), "value": str(t)} for t in temporadas_disponibles],
                value=["TODAS"],
                id="temporada-filter",
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
                id="fase-filter",
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
                id="ronda-filter",
                clearable=False,
                multi=True,
                style={"font-size": "1.05rem", "minWidth": "120px"}
            ),
        ], width=2),
        dbc.Col([
            html.Label("Nivel (solo gráficos)", style={"font-size": "1.1rem", "marginBottom": "0.2rem"}),
            dcc.Dropdown(
                options=[{"label": "TODOS", "value": "TODOS"}] + [{"label": n, "value": n} for n in niveles_disponibles],
                value=["TODOS"],
                id="nivel-torta-filter",
                clearable=False,
                multi=True,
                style={"font-size": "1.05rem", "minWidth": "120px"}
            )
        ], width=2),
    ], className="mb-4 justify-content-center g-2"),
], fluid=True, style={"paddingLeft": "0.5rem", "paddingRight": "0.5rem", "maxWidth": "1400px"})

tab_general = dbc.Container([
    dbc.Row([
        dbc.Col([
            html.H4("Distribución de diferencias por región", style={"marginTop": "1.5rem", "marginBottom": "1rem", "textAlign": "center"}),
            dbc.Row(id="graficos-torta", className="mb-4 justify-content-center"),
        ], width=12)
    ]),
    dbc.Row([
        dbc.Col([
            html.H4("Promedio de puntos por partido según región", style={"marginTop": "2.5rem", "marginBottom": "1rem", "textAlign": "center"}),
            dash_table.DataTable(
                id='tabla-promedios-region',
                columns=[
                    {"name": "Región", "id": "Región"},
                    {"name": "Prom. ganador", "id": "Prom. ganador"},
                    {"name": "Prom. perdedor", "id": "Prom. perdedor"},
                ],
                data=[],
                style_cell={'font-size': '1.1rem', 'textAlign': 'center'},
                style_header={'fontWeight': 'bold', 'font-size': '1.2rem', 'backgroundColor': '#e0e0e0'},
                style_table={"marginBottom": "2.5rem"}
            ),
        ], width=12)
    ]),
    dbc.Row([
        dbc.Col([
            html.H4("Partidos ganados por región en Interconferencia", style={"marginTop": "2.5rem", "marginBottom": "1rem", "textAlign": "center"}),
            dash_table.DataTable(
                id='tabla-interconferencia',
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

app.layout = html.Div([
    html.H2("Análisis de formativas de Febamba", style={"font-size": "2.2rem", "marginBottom": "2.5rem", "textAlign": "center", "letterSpacing": "0.04em"}),
    filtros_layout,
    dcc.Tabs(id="main-tabs", value="general", children=[
        dcc.Tab(label="General", value="general", children=[tab_general]),
        dcc.Tab(label="Power Ranking", value="power_ranking", children=[tab_power_ranking]),
    ]),
], style={"backgroundColor": "#f9f9f9"})

def get_table_data(df_totales, expanded_equipo=None):
    data = []
    for i, row in enumerate(df_totales.to_dict("records")):
        equipo = row["equipo"]
        is_expanded = (equipo == expanded_equipo)
        flecha = "🔽" if is_expanded else "▶️"
        data.append({
            "posicion": i+1,
            "equipo": f"{flecha} {equipo}",
            "pj": row["pj"],
            "ganados": row["ganados"],
            "perdidos": row["perdidos"],
            "diferencia": row["diferencia"],
            "power_ranking": f'{int(round(ranking_dict.get(equipo, 0)))}' if ranking_dict.get(equipo) is not None else "",
            "temporada": "TOTAL"
        })
        # Solo si está expandido, agregamos los años (ya precalculados)
        if is_expanded:
            for det in detalles_por_equipo[equipo]:
                data.append({
                    "posicion": "",
                    "equipo": f"   {det['temporada']}",
                    "pj": det["pj"],
                    "ganados": det["ganados"],
                    "perdidos": det["perdidos"],
                    "diferencia": det["diferencia"],
                    "power_ranking": "",
                    "temporada": det["temporada"]
                })
    return data

import dash
@app.callback(
    Output("tabla", "data"),
    [Input("tabla", "active_cell"),
     Input("region-filter", "value"),
     Input("temporada-filter", "value"),
     Input("fase-filter", "value"),
     Input("ronda-filter", "value"),
     Input("tabla", "id")],
    State("tabla", "data")
)
def unified_callback(cell, region_sel, temporada_sel, fase_sel, ronda_sel, _id, current_data):
    ctx = dash.callback_context
    df_filtrado = df.copy()
    # Región
    if region_sel and "TODAS" not in region_sel:
        df_filtrado = df_filtrado[df_filtrado['zona'].isin(region_sel)]
    # Temporada
    if temporada_sel and "TODAS" not in temporada_sel and 'anio' in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado['anio'].astype(str).isin([str(t) for t in temporada_sel])]
    # Fase
    if fase_sel and "TODAS" not in fase_sel:
        df_filtrado = df_filtrado[df_filtrado['fase'].isin(fase_sel)]
    # Ronda
    if ronda_sel and "TODAS" not in ronda_sel:
        df_filtrado = df_filtrado[df_filtrado['ronda'].astype(str).isin([str(r) for r in ronda_sel])]
    equipos_filtrados = sorted(set(df_filtrado['local']).union(set(df_filtrado['visitante'])))
    equipos_ordenados_local = sorted(
        equipos_filtrados,
        key=lambda eq: ranking_dict.get(eq, -9999),
        reverse=True
    )
    df_totales_local = []
    for equipo in equipos_ordenados_local:
        total = resumen_equipo_general(df_filtrado, equipo)
        if total["pj"] > 0:
            df_totales_local.append(total)
    df_totales_local = pd.DataFrame(df_totales_local)

    if not ctx.triggered or ctx.triggered[0]['prop_id'].endswith('.id') or \
       ctx.triggered[0]['prop_id'].startswith('region-filter') or \
       ctx.triggered[0]['prop_id'].startswith('temporada-filter') or \
       ctx.triggered[0]['prop_id'].startswith('fase-filter') or \
       ctx.triggered[0]['prop_id'].startswith('ronda-filter'):
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
    Output("graficos-torta", "children"),
    [Input("region-filter", "value"),
     Input("temporada-filter", "value"),
     Input("fase-filter", "value"),
     Input("ronda-filter", "value"),
     Input("nivel-torta-filter", "value")]
)
def update_graficos_torta(region_sel, temporada_sel, fase_sel, ronda_sel, nivel_sel):
    df_filtrado = df.copy()
    if region_sel and "TODAS" not in region_sel:
        df_filtrado = df_filtrado[df_filtrado['zona'].isin(region_sel)]
    if temporada_sel and "TODAS" not in temporada_sel and 'anio' in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado['anio'].astype(str).isin([str(t) for t in temporada_sel])]
    if fase_sel and "TODAS" not in fase_sel:
        df_filtrado = df_filtrado[df_filtrado['fase'].isin(fase_sel)]
    if ronda_sel and "TODAS" not in ronda_sel:
        df_filtrado = df_filtrado[df_filtrado['ronda'].astype(str).isin([str(r) for r in ronda_sel])]
    if nivel_sel and "TODOS" not in nivel_sel:
        df_filtrado = df_filtrado[df_filtrado['nivel'].isin(nivel_sel)]
    data_por_region = calcular_diferencias_por_region(df_filtrado)
    return graficos_torta_por_region(data_por_region)

# --- CALLBACKS PARA ACTUALIZAR LAS TABLAS ---
@app.callback(
    Output("tabla-promedios-region", "data"),
    [Input("region-filter", "value"),
     Input("temporada-filter", "value"),
     Input("fase-filter", "value"),
     Input("ronda-filter", "value"),
     Input("nivel-torta-filter", "value")]
)
def update_tabla_promedios(region_sel, temporada_sel, fase_sel, ronda_sel, nivel_sel):
    df_filtrado = df.copy()
    if region_sel and "TODAS" not in region_sel:
        df_filtrado = df_filtrado[df_filtrado['zona'].isin(region_sel)]
    if temporada_sel and "TODAS" not in temporada_sel and 'anio' in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado['anio'].astype(str).isin([str(t) for t in temporada_sel])]
    if fase_sel and "TODAS" not in fase_sel:
        df_filtrado = df_filtrado[df_filtrado['fase'].isin(fase_sel)]
    if ronda_sel and "TODAS" not in ronda_sel:
        df_filtrado = df_filtrado[df_filtrado['ronda'].astype(str).isin([str(r) for r in ronda_sel])]
    if nivel_sel and "TODOS" not in nivel_sel:
        df_filtrado = df_filtrado[df_filtrado['nivel'].isin(nivel_sel)]
    return tabla_promedios_por_region(df_filtrado)


# --- CALLBACK INTERACTIVO PARA TABLA INTERCONFERENCIA ---
@app.callback(
    Output("tabla-interconferencia", "data"),
    [Input("tabla-interconferencia", "active_cell"),
     Input("region-filter", "value"),
     Input("temporada-filter", "value"),
     Input("fase-filter", "value"),
     Input("ronda-filter", "value"),
     Input("nivel-torta-filter", "value")],
    State("tabla-interconferencia", "data")
)
def update_tabla_interconferencia(active_cell, region_sel, temporada_sel, fase_sel, ronda_sel, nivel_sel, current_data):
    df_filtrado = df.copy()
    if region_sel and "TODAS" not in region_sel:
        df_filtrado = df_filtrado[df_filtrado['zona'].isin(region_sel)]
    if temporada_sel and "TODAS" not in temporada_sel and 'anio' in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado['anio'].astype(str).isin([str(t) for t in temporada_sel])]
    if fase_sel and "TODAS" not in fase_sel:
        df_filtrado = df_filtrado[df_filtrado['fase'].isin(fase_sel)]
    if ronda_sel and "TODAS" not in ronda_sel:
        df_filtrado = df_filtrado[df_filtrado['ronda'].astype(str).isin([str(r) for r in ronda_sel])]
    if nivel_sel and "TODOS" not in nivel_sel:
        df_filtrado = df_filtrado[df_filtrado['nivel'].isin(nivel_sel)]

    region_expandida = None
    if active_cell and active_cell.get('column_id') == 'Región':
        row_idx = active_cell.get('row')
        if current_data and 0 <= row_idx < len(current_data):
            region_val = current_data[row_idx].get('Región', '').strip()
            # Solo expandir si es una región principal
            if region_val in ["SUR", "OESTE", "NORTE", "CENTRO"]:
                region_expandida = region_val

    return tabla_interconferencia(df_filtrado, region_expandida=region_expandida)

if __name__ == "__main__":
    app.run(debug=True)