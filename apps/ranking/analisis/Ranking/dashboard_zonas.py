import pandas as pd
import streamlit as st

# Cargar datos de partidos
df = pd.read_csv(
    r"c:\Users\Matias Garcia\OneDrive - UTN.BA\Repo Nuevo\PaginaLeyendas\formativas_ges\Data\procesada\19-24.csv",
    sep=";"
)

# Normalizar columnas relevantes
df['zona'] = df['zona'].str.strip().str.upper()
df['categoria'] = df['categoria'].str.strip().str.upper()
df['local'] = df['local'].str.strip().str.upper()
df['visitante'] = df['visitante'].str.strip().str.upper()
df['fase'] = df['fase'].str.strip().str.upper()

# Quitar "DESCONOCIDO" de todas las columnas relevantes
for col in ['zona', 'categoria', 'local', 'visitante', 'fase']:
    df = df[df[col] != "DESCONOCIDO"]

# Filtrar solo categorías válidas (NO filtrar por zona, así se incluyen interconferencia)
categorias_excluir = ["MINI", "PREMINI"]
df = df[~df['categoria'].isin(categorias_excluir)]

# --- Filtros Streamlit ---
zonas_disponibles = sorted(str(z).upper() for z in df['zona'].dropna().unique())
anios_disponibles = sorted(df['anio'].unique())
fases_disponibles = sorted(str(f).upper() for f in df['fase'].dropna().unique())

zona_sel = st.selectbox("Filtrar por zona", ["TODAS"] + zonas_disponibles)
anio_sel = st.selectbox("Filtrar por año", ["TODOS"] + [str(a) for a in anios_disponibles])
fase_sel = st.selectbox("Filtrar por fase", ["TODAS"] + fases_disponibles)

df_filtrado = df.copy()
if zona_sel != "TODAS":
    df_filtrado = df_filtrado[df_filtrado['zona'] == zona_sel]
if anio_sel != "TODOS":
    # Solución robusta para comparar año como string/int/float
    df_filtrado = df_filtrado[df_filtrado['anio'].astype(str) == str(int(float(anio_sel)))]
if fase_sel != "TODAS":
    df_filtrado = df_filtrado[df_filtrado['fase'] == fase_sel]

# --- Agrupación por equipo unitario ---
equipos = pd.unique(df_filtrado[['local', 'visitante']].values.ravel('K'))

@st.cache_data
def calcular_estadisticas(df, equipos):
    lista = []
    for equipo in equipos:
        loc = df[df['local'] == equipo]
        vis = df[df['visitante'] == equipo]
        pj = len(loc) + len(vis)
        if pj == 0:
            continue
        puntos_realizados = loc['ptsL'].sum() + vis['ptsV'].sum()
        puntos_recibidos = loc['ptsV'].sum() + vis['ptsL'].sum()
        ganados = (loc['ptsL'] > loc['ptsV']).sum() + (vis['ptsV'] > vis['ptsL']).sum()
        perdidos = (loc['ptsL'] < loc['ptsV']).sum() + (vis['ptsV'] < vis['ptsL']).sum()
        lista.append({
            'Equipo': equipo,
            'PJ': pj,
            'Ganados': ganados,
            'Perdidos': perdidos,
            'Diferencia de Gol': puntos_realizados - puntos_recibidos,
        })
    return pd.DataFrame(lista)

with st.spinner("Calculando estadísticas..."):
    tabla_general = calcular_estadisticas(df_filtrado, equipos)

if tabla_general.empty:
    st.warning("No hay datos para los filtros seleccionados.")
else:
    # Asegura que la columna se llame 'Equipo'
    if 'Equipo' not in tabla_general.columns:
        tabla_general = tabla_general.rename(columns={tabla_general.columns[0]: 'Equipo'})

    # --- Cargar Power Ranking 2019-2024 ---
    df_power = pd.read_csv(
        r"c:\Users\Matias Garcia\OneDrive - UTN.BA\Repo Nuevo\PaginaLeyendas\formativas_ges\Data\procesada\Ranking2019-2024.csv"
    ).rename(columns={"Puntos": "Power Ranking 2019-2024"})

    # Unir tabla general con power ranking
    tabla_final = pd.merge(tabla_general, df_power[['Equipo', 'Power Ranking 2019-2024']], how="left", on="Equipo")
    tabla_final = tabla_final.sort_values(by="Power Ranking 2019-2024", ascending=False).reset_index(drop=True)

    st.title("Ranking General de Equipos (formato tabla Excel)")
    st.dataframe(tabla_final)

    # Botón para descargar como Excel
    st.download_button(
        label="Descargar Excel",
        data=tabla_final.to_excel(index=False, engine='openpyxl'),
        file_name="ranking_general_equipos.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

