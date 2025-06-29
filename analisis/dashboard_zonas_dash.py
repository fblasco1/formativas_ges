import pandas as pd
from dash import Dash, html, Input, Output, State, dash_table, dcc
import dash_bootstrap_components as dbc

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
for col in ['zona', 'categoria', 'local', 'visitante', 'fase']:
    df = df[df[col] != "DESCONOCIDO"]
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

# Layout Dash con filtro de región
regiones_disponibles = sorted(df['zona'].unique())
fases_disponibles = sorted(df['fase'].unique())

app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

app.layout = html.Div([
    html.H2("Análisis de formativas de Febamba", style={"font-size": "2.2rem", "margin-bottom": "1.5rem"}),
    dbc.Row([
        dbc.Col([
            html.Label("Filtrar por región:", style={"font-size": "1.2rem"}),
            dcc.Dropdown(
                options=[{"label": "TODAS", "value": "TODAS"}] + [{"label": z, "value": z} for z in regiones_disponibles],
                value="TODAS",
                id="region-filter",
                clearable=False,
                style={"font-size": "1.1rem"}
            )
        ], width=3),
        dbc.Col([
            html.Label("Filtrar por fase:", style={"font-size": "1.2rem"}),
            dcc.Dropdown(
                options=[{"label": "TODAS", "value": "TODAS"}] + [{"label": f, "value": f} for f in fases_disponibles],
                value="TODAS",
                id="fase-filter",
                clearable=False,
                style={"font-size": "1.1rem"}
            )
        ], width=3)
    ], className="mb-4"),
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
        row_selectable='single'
    )
])

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
    [Input("tabla", "active_cell"), Input("region-filter", "value"), Input("fase-filter", "value"), Input("tabla", "id")],
    State("tabla", "data")
)
def unified_callback(cell, region_sel, fase_sel, _id, current_data):
    ctx = dash.callback_context
    # Filtrar el dataframe según región y fase
    df_filtrado = df.copy()
    if region_sel != "TODAS":
        df_filtrado = df_filtrado[(df_filtrado['zona'] == region_sel)]
    if fase_sel != "TODAS":
        df_filtrado = df_filtrado[(df_filtrado['fase'] == fase_sel)]
    equipos_filtrados = sorted(set(df_filtrado['local']).union(set(df_filtrado['visitante'])))
    equipos_ordenados_local = sorted(
        equipos_filtrados,
        key=lambda eq: ranking_dict.get(eq, -9999),
        reverse=True
    )
    # Solo totales filtrados
    df_totales_local = []
    for equipo in equipos_ordenados_local:
        total = resumen_equipo_general(df_filtrado, equipo)
        if total["pj"] > 0:
            df_totales_local.append(total)
    df_totales_local = pd.DataFrame(df_totales_local)

    # Primer render (triggered por tabla.id o filtros)
    if not ctx.triggered or ctx.triggered[0]['prop_id'].endswith('.id') or ctx.triggered[0]['prop_id'].startswith('region-filter') or ctx.triggered[0]['prop_id'].startswith('fase-filter'):
        return get_table_data(df_totales_local)
    # Click en fila
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

if __name__ == "__main__":
    app.run(debug=True)