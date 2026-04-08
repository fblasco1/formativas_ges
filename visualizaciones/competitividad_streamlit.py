import os
import sys
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Agrega el directorio padre al path de Python
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.open_csv import leer_csv_con_encoding_detectado


st.title("Competitividad y concentración por región y año")

OUTDIR = "outputs"

# Cargar los resultados exportados
win_pct = leer_csv_con_encoding_detectado(f"{OUTDIR}/win_pct_por_equipo_region.csv", sep=",")
desv = leer_csv_con_encoding_detectado(f"{OUTDIR}/desviacion_win_pct.csv", sep=",")
ajustados = leer_csv_con_encoding_detectado(f"{OUTDIR}/partidos_ajustados.csv", sep=",")
herf = leer_csv_con_encoding_detectado(f"{OUTDIR}/herfindahl_ganadores.csv", sep=",")

# Filtrar regiones no válidas y ajustar regiones interregionales
regiones_invalidas = ["DESCONOCIDO", "DESCONOCIDA", "INTERCONFERENCIA"]
win_pct = win_pct[~win_pct["region"].isin(regiones_invalidas)]
desv = desv[[c for c in desv.columns if c not in regiones_invalidas]]
ajustados = ajustados[[c for c in ajustados.columns if c not in regiones_invalidas]]
herf = herf[[c for c in herf.columns if c not in regiones_invalidas]]

st.header("Desviación estándar del Win% por región y año")
desv = desv.set_index(desv.columns[0]) if desv.columns[0] != 'año' else desv.set_index('año')
st.dataframe(desv)
st.line_chart(desv)

st.header("Proporción de partidos ajustados (<20 pts) por región y año")
# Asegurar que el año sea el índice en todos los gráficos de líneas
ajustados = ajustados.set_index(ajustados.columns[0]) if ajustados.columns[0] != 'año' else ajustados.set_index('año')
st.dataframe(ajustados)
st.line_chart(ajustados)

st.header("Índice de Herfindahl de ganadores por región y año")
herf = herf.set_index(herf.columns[0]) if herf.columns[0] != 'año' else herf.set_index('año')
st.dataframe(herf)
st.line_chart(herf)

st.header("Histograma de Win% por región y año")
anios = win_pct["año"].unique()
anio = st.selectbox("Selecciona el año para el histograma", sorted(anios))
fig, ax = plt.subplots(figsize=(10,5))
for region, subdf in win_pct[win_pct["año"] == anio].groupby("region"):
    sns.histplot(subdf["win_pct"], bins=10, kde=False, label=region, ax=ax, alpha=0.5)
ax.legend()
ax.set_title(f'Histograma Win% por región - {anio}')
ax.set_xlabel('Win%')
ax.set_ylabel('Frecuencia')
st.pyplot(fig)

# Mostrar resumen agregado por región
resumen = leer_csv_con_encoding_detectado(f"{OUTDIR}/resumen_agregado_regional.csv", sep=",")
st.header("Resumen agregado por región")
st.dataframe(resumen)
