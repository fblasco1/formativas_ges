import streamlit as st
import pandas as pd
import json
import matplotlib.pyplot as plt

# Función para calcular proporciones de NP por categoría y zona
def calcular_proporciones_np(zona, fase):
    proporciones_np = []
    for categoria in fase["categorias"]:
        total_partidos = 0
        total_np = 0
        try:
            for equipo in categoria["tabla_general"]:
                total_partidos += equipo["PJ"]
                print(total_partidos)
                total_np += equipo["NP"]
                print(total_np)
            
            if total_partidos > 0:
                proporciones_np.append({
                    "zona": zona,
                    "categoria": categoria["categoria"],
                    "proporcion_np": total_np / total_partidos
                })

        except KeyError:
            print(zona)
    
    return proporciones_np

# Función para resaltar equipos que clasifican a top16 y Liga Federal Formativa
def resaltar_equipos(df, nivel, categoria=None):
    def highlight_row(row):
        if row.name < 4:  # Clasifican los primeros 4
            return ['background-color: green'] * len(row)
        if row['NP'] >= 4:  # No presentaron en 4 o más partidos
            return ['background-color: orange'] * len(row)
        return [''] * len(row)
    
    df = df.style.apply(highlight_row, axis=1)
    return df

# Load data from the reorganized JSON file
with open('nueva_estructura_formativas_febamba.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

def main():
    st.set_page_config(page_title="Formativas Febamba", page_icon=":basketball:", layout="wide")
    st.title("Formativas Febamba")
    nav_col1, nav_col2, nav_col3 = st.columns([1,1,1])

    fase_seleccionada = None

    with nav_col1:
        # Select Level
        niveles = [nivel['nivel'] for nivel in data]
        nivel_seleccionado = st.selectbox("NIVEL:", niveles, index=None, placeholder="Seleccione un nivel", key="sb_nivel")

    with nav_col2:
        if nivel_seleccionado is None:
            zona_seleccionada = st.selectbox("ZONA:", [], index=None , placeholder="Seleccione una zona", disabled=True, key="sb_zona")
        else:
            nivel_data = next(nivel for nivel in data if nivel['nivel'] == nivel_seleccionado)
            # Select Zone
            zonas = [zona['zona'] for zona in nivel_data['zonas']]
            zona_seleccionada = st.selectbox("ZONA:", zonas, index=None , placeholder="Seleccione una zona", key="sb_zona")
    with nav_col3:
        if zona_seleccionada is None:
            st.selectbox("FASES:", [], index=None , placeholder="Seleccione una fase", disabled=True, key="sb_fases")
        else:
            zona_data = next(zona for zona in nivel_data['zonas'] if zona['zona'] == zona_seleccionada)
            # Select Phase
            fases = [fase['fase'] for fase in zona_data['fases']]
            fase_seleccionada = st.selectbox("FASES:", fases, index=None , placeholder="Seleccione una fase", key="sb_fases")
    
    row_1_col1, row_1_col2 = st.columns(2)
    # Obtener las categorías ordenadas
    col1, col2, col3 = st.columns(3)
    col1_cats = ["U13 Mixto", "U21 Masculino"]
    col2_cats = ["Mini Mixto", "U17 Masculino"]
    col3_cats = ["U9 MIXTO", "U15 Masculino"]
    
    if fase_seleccionada is None:
        st.text("Todavía no se cargo información")
    else:    
        fase_data = next(fase for fase in zona_data['fases'] if fase['fase'] == fase_seleccionada)

        with row_1_col1:
            # Display general table for the zone
            st.subheader(f"Tabla General")
            df_tabla_general = pd.DataFrame(fase_data['tabla_general'])
            st.dataframe(resaltar_equipos(df_tabla_general, nivel_seleccionado))

        with row_1_col2:
            st.subheader("Proporción de partidos no presentados por categoría")
            ## Calcular proporciones de NP
            proporciones_np = calcular_proporciones_np(zona_seleccionada, fase_data)
            print(proporciones_np)
            # Filtrar proporciones de NP por la zona seleccionada
            proporciones_np_zona = [np for np in proporciones_np if np["zona"] == zona_seleccionada]

            # Mostrar gráfico de torta
            if proporciones_np_zona:
                
                fig, ax = plt.subplots()
                categorias = [np["categoria"] for np in proporciones_np_zona]
                proporciones = [np["proporcion_np"] for np in proporciones_np_zona]
                ax.pie(proporciones, labels=categorias, autopct='%1.1f%%')
                ax.axis('equal')
                st.pyplot(fig)

        # Display general tables for each category
        for categoria in fase_data['categorias']:
            if categoria['categoria'] in col1_cats:
                with col1:
                    try:
                        st.subheader(f"{categoria['categoria']}")
                        df_tabla_general_categoria = pd.DataFrame(categoria['tabla_general'])
                        st.table(df_tabla_general_categoria.set_index('Equipo'))
                    except KeyError:
                        st.subheader(f"{categoria}")
            elif categoria['categoria'] in col2_cats:
                # Mostrar tabla de posiciones
                with col2:
                    try:
                        st.subheader(f"{categoria['categoria']}")
                        df_tabla_general_categoria = pd.DataFrame(categoria['tabla_general'])
                        st.table(df_tabla_general_categoria.set_index('Equipo'))
                    except KeyError:
                        st.subheader(f"{categoria}")
            elif categoria['categoria'] in col3_cats:
                # Mostrar tabla de posiciones
                with col3:
                    try:
                        st.subheader(f"{categoria['categoria']}")
                        df_tabla_general_categoria = pd.DataFrame(categoria['tabla_general'])
                        st.table(df_tabla_general_categoria.set_index('Equipo'))
                    except KeyError:
                        st.subheader(f"{categoria}")

        # Select Subzone
        subzonas = [subzona['subzona'] for categoria in fase_data['categorias'] for subzona in categoria['subzonas']]
        subzona_seleccionada = st.selectbox("Selecciona una Subzona:", list(dict.fromkeys(subzonas)), key="sb_subzona")

        col1_sb, col2_sb, col3_sb = st.columns(3)

        if subzona_seleccionada:
            for categoria in fase_data['categorias']:
                subzona_data = next((subzona for subzona in categoria['subzonas'] if subzona['subzona'] == subzona_seleccionada), None)
                if subzona_data:
                    if categoria['categoria'] in col1_cats:
                        # Mostrar tabla de posiciones
                        with col1_sb:
                            try:
                                st.subheader(f"{categoria['categoria']}")
                                df_tabla_posiciones = pd.DataFrame(subzona_data['tabla_posiciones'])
                                st.table(df_tabla_posiciones.set_index('Equipo'))

                                # Selector de jornadas
                                jornadas = sorted(set(partido["Jornada"] for partido in subzona_data['partidos']))
                                jornada_seleccionada = st.selectbox(f"Selecciona una jornada para {categoria['categoria']} - {fase_seleccionada} - {subzona_seleccionada}:", jornadas)

                                # Filtrar partidos por jornada
                                partidos_jornada = [partido for partido in subzona_data['partidos'] if partido["Jornada"] == jornada_seleccionada]

                                # Mostrar partidos de la jornada en una tabla
                                df_partidos = pd.DataFrame(partidos_jornada).set_index("Partido_ID")
                                df_partidos = df_partidos[["Local", "Puntos LOCAL", "Puntos VISITA", "Visitante", "Fecha"]]
                                st.table(df_partidos)
                            except KeyError:
                                st.subheader(f"{categoria}")
                    elif categoria['categoria'] in col2_cats:
                        # Mostrar tabla de posiciones
                        with col2_sb:
                            try:
                                st.subheader(f"{categoria['categoria']}")
                                df_tabla_posiciones = pd.DataFrame(subzona_data['tabla_posiciones'])
                                st.table(df_tabla_posiciones.set_index('Equipo'))

                                # Selector de jornadas
                                jornadas = sorted(set(partido["Jornada"] for partido in subzona_data['partidos']))
                                jornada_seleccionada = st.selectbox(f"Selecciona una jornada para {categoria['categoria']} - {fase_seleccionada} - {subzona_seleccionada}:", jornadas)

                                # Filtrar partidos por jornada
                                partidos_jornada = [partido for partido in subzona_data['partidos'] if partido["Jornada"] == jornada_seleccionada]

                                # Mostrar partidos de la jornada en una tabla
                                df_partidos = pd.DataFrame(partidos_jornada).set_index("Partido_ID")
                                df_partidos = df_partidos[["Local", "Puntos LOCAL", "Puntos VISITA", "Visitante", "Fecha"]]
                                st.table(df_partidos)
                            except KeyError:
                                st.subheader(f"{categoria}")
                    elif categoria['categoria'] in col3_cats:
                        with col3_sb:
                            try:
                                st.subheader(f"{categoria['categoria']}")
                                df_tabla_posiciones = pd.DataFrame(subzona_data['tabla_posiciones'])
                                st.table(df_tabla_posiciones.set_index('Equipo'))

                                # Selector de jornadas
                                jornadas = sorted(set(partido["Jornada"] for partido in subzona_data['partidos']))
                                jornada_seleccionada = st.selectbox(f"Selecciona una jornada para {categoria['categoria']} - {fase_seleccionada} - {subzona_seleccionada}:", jornadas)

                                # Filtrar partidos por jornada
                                partidos_jornada = [partido for partido in subzona_data['partidos'] if partido["Jornada"] == jornada_seleccionada]

                                # Mostrar partidos de la jornada en una tabla
                                df_partidos = pd.DataFrame(partidos_jornada).set_index("Partido_ID")
                                df_partidos = df_partidos[["Local", "Puntos LOCAL", "Puntos VISITA", "Visitante", "Fecha"]]
                                st.table(df_partidos)
                            except KeyError:
                                st.subheader(f"{categoria}")
                                

if __name__ == "__main__":
    main()
