import streamlit as st
import json
import pandas as pd

# Cargar los datos de competencia con tabla de posiciones desde el archivo JSON
with open("formativas_febamba.json", "r") as file:
    datos_competencia = json.load(file)



# Crear la aplicación de Streamlit
def main():
    st.set_page_config(page_title="Formativas Febamba", page_icon=":basketball:", layout="wide")
    st.title("Todos Somos Febamba")

    nav_col1, nav_col2 = st.columns([1,1])

    with nav_col1:
        # Desplegable para seleccionar la fase con placeholder
        opciones_fase = [fase['fase'] for fase in datos_competencia["fases"]]
        fase_seleccionada = st.selectbox("FASES:", opciones_fase, index=None, placeholder="Seleccione una Fase")
    with nav_col2:
        if fase_seleccionada is None:
            grupo_seleccionado = st.selectbox("GRUPOS:", [], index=None , placeholder="Seleccione un Grupo", disabled=True)
        else:
            # Obtener los grupos de la fase seleccionada
            grupos_fase_seleccionada = []
            for fase in datos_competencia["fases"]:
                if fase["fase"] == fase_seleccionada:
                    grupos_fase_seleccionada = fase["grupos"]
                    opciones_grupo = [grupo['grupo'] for grupo in grupos_fase_seleccionada]
            grupo_seleccionado = st.selectbox("GRUPOS:", opciones_grupo, index=None , placeholder="Seleccione un Grupo")
        

    # Obtener las categorías ordenadas
    col3_cats = ["U9 MIXTO", "U15 Masculino"]
    col2_cats = ["Mini Mixto", "U17 Masculino"]
    col1_cats = ["U13 Mixto", "U21 Masculino"]

    col1, col2, col3 = st.columns(3)

    for fase in datos_competencia["fases"]:
        for grupo in fase["grupos"]:
            if grupo["grupo"] == grupo_seleccionado and fase["fase"] == fase_seleccionada:
                for cat in grupo["categorias"]:
                    categoria = cat["categoria"]
                    if categoria in col1_cats:
                        # Mostrar tabla de posiciones
                        with col1:
                            try:
                                st.subheader(f"{categoria}")
                                st.dataframe(cat["tabla_posiciones"])
                                
                                # Selector de jornadas
                                jornadas = sorted(set(partido["Jornada"] for partido in cat["partidos"]))
                                jornada_seleccionada = st.selectbox(f"Selecciona una jornada para {categoria} - {fase_seleccionada} - {grupo_seleccionado}:", jornadas)
                                
                                # Filtrar partidos por jornada
                                partidos_jornada = [partido for partido in cat["partidos"] if partido["Jornada"] == jornada_seleccionada]
                                df_partidos = pd.DataFrame(partidos_jornada).set_index("Partido_ID")
                                df_partidos = df_partidos[["Local", "Puntos LOCAL", "Puntos VISITA", "Visitante", "Fecha"]]
                                st.table(df_partidos)
                            except KeyError:
                                st.subheader(f"{categoria}")
                    elif categoria in col2_cats:
                        # Mostrar tabla de posiciones
                        with col2:
                            try:
                                st.subheader(f"{categoria}")
                                st.dataframe(cat["tabla_posiciones"])
                                # Selector de jornadas
                                jornadas = sorted(set(partido["Jornada"] for partido in cat["partidos"]))
                                jornada_seleccionada = st.selectbox(f"Selecciona una jornada para {categoria} - {fase_seleccionada} - {grupo_seleccionado}:", jornadas)
                                
                                # Filtrar partidos por jornada
                                partidos_jornada = [partido for partido in cat["partidos"] if partido["Jornada"] == jornada_seleccionada]
                                df_partidos = pd.DataFrame(partidos_jornada).set_index("Partido_ID")
                                df_partidos = df_partidos[["Local", "Puntos LOCAL", "Puntos VISITA", "Visitante", "Fecha"]]
                                st.table(df_partidos)
                            except KeyError:
                                st.subheader(f"{categoria}")
                    elif categoria in col3_cats:
                        # Mostrar tabla de posiciones
                        with col3:
                            try:
                                st.subheader(f"{categoria}")
                                st.dataframe(cat["tabla_posiciones"])
                                # Selector de jornadas
                                jornadas = sorted(set(partido["Jornada"] for partido in cat["partidos"]))
                                jornada_seleccionada = st.selectbox(f"Selecciona una jornada para {categoria} - {fase_seleccionada} - {grupo_seleccionado}:", jornadas)
                                
                                # Filtrar partidos por jornada
                                partidos_jornada = [partido for partido in cat["partidos"] if partido["Jornada"] == jornada_seleccionada]
                                
                                # Mostrar partidos de la jornada en una tabla
                                df_partidos = pd.DataFrame(partidos_jornada).set_index("Partido_ID")
                                df_partidos = df_partidos[["Local", "Puntos LOCAL", "Puntos VISITA", "Visitante", "Fecha"]]
                                st.table(df_partidos)
                            except KeyError:
                                st.subheader(f"{categoria}")      

if __name__ == "__main__":
    main()