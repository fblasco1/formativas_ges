import streamlit as st
import pandas as pd
import json
import plotly.graph_objects as go

# Función para calcular proporciones de NP por categoría y zona
def calcular_proporciones_np(zona, fase):
    proporciones_np = []
    for categoria in fase["categorias"]:
        total_partidos = 0
        total_np = 0
        try:
            for equipo in categoria["tabla_general"]:
                total_partidos += equipo["PJ"]
                total_np += equipo["NP"]
            
            if total_partidos > 0:
                proporciones_np.append({
                    "zona": zona,
                    "categoria": categoria["categoria"],
                    "proporcion_np": total_np / total_partidos
                })

        except KeyError:
            print(zona)
    
    return proporciones_np

# Función para resaltar los equipos en la tabla general según el nivel
def resaltar_equipos(df, nivel):
    styles = pd.DataFrame('', index=df.index, columns=df.columns)
    
    if nivel == "NIVEL 1":
        styles.iloc[:4, :] = 'background-color: lightgreen'  # Top 4 - TOP 16
        styles.iloc[4:8, :] = 'background-color: lightblue'  # 5th to 8th - TOP 16 2
        styles.iloc[8:12, :] = 'background-color: white'  # 9th to 12th - maintain level 1
    elif nivel == "NIVEL 3":
        styles.iloc[:16, :] = 'background-color: lightgreen'  # Top 16 - move to Level 2

    return styles

def resaltar_equipos_cat(df, nivel):
    styles = pd.DataFrame('', index=df.index, columns=df.columns)

    if nivel == "NIVEL 1":
        styles.loc[:3, :] = 'background-color: lightgreen'  # Top 4 - TOP 16
    
    return styles

# Load data from the reorganized JSON file
with open('formativas_febamba.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

def main():
    st.set_page_config(page_title="Formativas Febamba", page_icon=":basketball:", layout="wide")
    header_1, header_2 = st.columns([0.5, 0.5])
    
    with st.container():
        with header_1:
            st.title("Formativas Febamba")
        with header_2:
            st.link_button("Reglamento 2024", url="http://febamba.com/?wpfb_dl=2110")
            st.link_button("Formato Competencias 2024", url="http://febamba.com/?wpfb_dl=2099")
           

        st.text("Art. 3, 4, 19, 27 del Reglamento 2024 explican las sanciones a los equipos que no presenten en una categoria")
        st.text("En el link de formato de competencias puedes ver como es la organización de los niveles y clasificación a LFF")
        st.text("Las tablas generales puede que no reflejen las posiciones reales de los equipos debido que no contemplan el desempate olimpico")
    
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

        # Verificar equipos con 4 o más partidos no presentados en cualquier categoría
        equipos_np = set()
        data_partidos_np_cat = []
        equipos_np_por_categoria = {}

        for categoria in fase_data["categorias"]:
            df_categoria = pd.DataFrame(categoria["tabla_general"])
            equipos_np.update(df_categoria[df_categoria['NP'] >= 4]['Equipo'])
            total_partidos = 0
            no_presentados = 0
            datos_np_equipos = {}
            for subzona in categoria["subzonas"]:
                partidos = subzona["partidos"]
                total_partidos += len(partidos)
                for p in partidos:
                    try:
                        if (int(p["Puntos LOCAL"]) == 20 and int(p["Puntos VISITA"]) == 0): 
                            datos_np_equipos[p["Visitante"]] = datos_np_equipos.get(p["Visitante"], 0) + 1
                            no_presentados += 1
                        elif (int(p["Puntos LOCAL"]) == 0 and int(p["Puntos VISITA"]) == 20):
                            datos_np_equipos[p["Local"]] = datos_np_equipos.get(p["Local"], 0) + 1
                            no_presentados += 1
                        elif(int(p["Puntos LOCAL"]) == 1 and int(p["Puntos VISITA"]) == 1):
                            datos_np_equipos[p["Local"]] = datos_np_equipos.get(p["Local"], 0) + 1
                            datos_np_equipos[p["Visitante"]] = datos_np_equipos.get(p["Visitante"], 0) + 1
                            no_presentados += 1
                    except ValueError:
                        total_partidos -= 1

            data_partidos_np_cat.append({
                "Categoria": categoria["categoria"],
                "Partidos Disputados": total_partidos,
                "Partidos No Presentados": no_presentados
            })

            equipos_np_por_categoria[categoria["categoria"]] = datos_np_equipos

        # Función para resaltar los equipos en negrita y rojo
        def resaltar_equipos_np(val):
            if val in equipos_np:
                return 'font-weight: bold; color: red'
            return ''

        with row_1_col1:
            # Display general table for the zone
            st.subheader(f"Tabla General")
            df_tabla_general = pd.DataFrame(fase_data['tabla_general'])

            # Aplicar estilos por nivel
            tabla_general_styles = resaltar_equipos(df_tabla_general, nivel_seleccionado)

            # Aplicar estilos de equipos no presentados
            styled_df_tabla_general = df_tabla_general.style.map(resaltar_equipos_np)

            # Combinar estilos
            styled_df_tabla_general = styled_df_tabla_general.apply(lambda x: tabla_general_styles.loc[x.name], axis=1)

            # Mostrar el DataFrame con los estilos aplicados
            st.dataframe(styled_df_tabla_general, hide_index=True)

            # Leyenda
            if nivel_seleccionado == "NIVEL 1":
                st.text("""
                Verde: Clasifican a Interconferencias 1
                Celeste: Clasifican a Interconferencias 2
                Blanco: Mantienen nivel 1
                Letras rojas, indica que deberían bajar al FLEX próxima fase.
                """
                )
            # Leyenda
            if nivel_seleccionado == "NIVEL 2":
                st.text("""
                Todos ascienden a Nivel 1
                Letras rojas, indica que deberían bajar al FLEX próxima fase.
                """
                )
            # Leyenda
            if nivel_seleccionado == "NIVEL 3":
                st.text("""
                Verde: Clasifican a Nivel 2
                Letras rojas, indica que deberían bajar al FLEX próxima fase.
                """
                )

        with row_1_col2:
            df_np = pd.DataFrame(data_partidos_np_cat)
            # Crear el gráfico de barras apiladas usando plotly
            fig = go.Figure()

            # Agregar barras de Partidos Disputados
            fig.add_trace(go.Bar(
                x=df_np["Categoria"],
                y=df_np["Partidos Disputados"],
                name="Partidos Disputados",
                marker_color='blue',
            ))

            # Agregar una sola traza de Partidos No Presentados con hoverinfo
            categorias = []
            no_presentados = []
            hover_texts = []

            for i, row in df_np.iterrows():
                categoria = row["Categoria"]
                categorias.append(categoria)
                no_presentados.append(row["Partidos No Presentados"])
                equipos_np = equipos_np_por_categoria[categoria]
                equipos_info = "<br>".join([f"{equipo}: {count}" for equipo, count in equipos_np.items()])
                hover_texts.append(f"Total: {row['Partidos No Presentados']}<br>{equipos_info}")

            fig.add_trace(go.Bar(
                x=categorias,
                y=no_presentados,
                name="Partidos No Presentados",
                marker_color='red',
                hoverinfo='text',
                hovertext=hover_texts,
            ))

            # Actualizar el diseño del gráfico
            fig.update_layout(
                barmode='overlay',
                title="Cantidad de Partidos Disputados y No Presentados por Categoría",
                xaxis_title="Categorías",
                yaxis_title="Cantidad de Partidos",
                legend=dict(x=0, y=1.0, orientation="h", xanchor="left", yanchor="top"),
                hovermode='closest'
            )

            # Mostrar el gráfico en Streamlit
            st.plotly_chart(fig)
            

        # Display general tables for each category
        for categoria in fase_data['categorias']:
            try:
                if categoria['categoria'] in col1_cats:
                    with col1:
                        st.subheader(f"{categoria['categoria']}")
                        df_tabla_general_categoria = pd.DataFrame(categoria['tabla_general'])
                        tabla_general_styles_cat = resaltar_equipos_cat(df_tabla_general_categoria, nivel_seleccionado)
                        st.dataframe(df_tabla_general_categoria.style.apply(lambda _: tabla_general_styles_cat, axis=None), hide_index=True)
                
                        # Selector de jornadas
                        jornadas = sorted(set(partido["Jornada"] for partido in categoria['partidos']))
                        jornada_seleccionada = st.selectbox(f"Selecciona una jornada interzonal para {categoria['categoria']} - {fase_seleccionada}:", jornadas)

                        # Filtrar partidos por jornada
                        partidos_jornada = [partido for partido in categoria['partidos'] if partido["Jornada"] == jornada_seleccionada]

                        # Mostrar partidos de la jornada en una tabla
                        df_partidos = pd.DataFrame(partidos_jornada).set_index("Partido_ID")
                        df_partidos = df_partidos[["Local", "Puntos LOCAL", "Puntos VISITA", "Visitante", "Fecha"]]
                        st.table(df_partidos)
                elif categoria['categoria'] in col2_cats:
                    # Mostrar tabla de posiciones
                    with col2:
                        st.subheader(f"{categoria['categoria']}")
                        df_tabla_general_categoria = pd.DataFrame(categoria['tabla_general'])
                        tabla_general_styles_cat = resaltar_equipos_cat(df_tabla_general_categoria, nivel_seleccionado)
                        st.dataframe(df_tabla_general_categoria.style.apply(lambda _: tabla_general_styles_cat, axis=None), hide_index=True)
                
                        # Selector de jornadas
                        jornadas = sorted(set(partido["Jornada"] for partido in categoria['partidos']))
                        jornada_seleccionada = st.selectbox(f"Selecciona una jornada interzonal para {categoria['categoria']} - {fase_seleccionada}:", jornadas)

                        # Filtrar partidos por jornada
                        partidos_jornada = [partido for partido in categoria['partidos'] if partido["Jornada"] == jornada_seleccionada]

                        # Mostrar partidos de la jornada en una tabla
                        df_partidos = pd.DataFrame(partidos_jornada).set_index("Partido_ID")
                        df_partidos = df_partidos[["Local", "Puntos LOCAL", "Puntos VISITA", "Visitante", "Fecha"]]
                        st.table(df_partidos)
                elif categoria['categoria'] in col3_cats:
                    # Mostrar tabla de posiciones
                    with col3:
                        st.subheader(f"{categoria['categoria']}")
                        df_tabla_general_categoria = pd.DataFrame(categoria['tabla_general'])
                        tabla_general_styles_cat = resaltar_equipos_cat(df_tabla_general_categoria, nivel_seleccionado)
                        st.dataframe(df_tabla_general_categoria.style.apply(lambda _: tabla_general_styles_cat, axis=None), hide_index=True)
            
                        # Selector de jornadas
                        jornadas = sorted(set(partido["Jornada"] for partido in categoria['partidos']))
                        jornada_seleccionada = st.selectbox(f"Selecciona una jornada interzonal para {categoria['categoria']} - {fase_seleccionada}:", jornadas)

                        # Filtrar partidos por jornada
                        partidos_jornada = [partido for partido in categoria['partidos'] if partido["Jornada"] == jornada_seleccionada]

                        # Mostrar partidos de la jornada en una tabla
                        df_partidos = pd.DataFrame(partidos_jornada).set_index("Partido_ID")
                        df_partidos = df_partidos[["Local", "Puntos LOCAL", "Puntos VISITA", "Visitante", "Fecha"]]
                        st.table(df_partidos)

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
