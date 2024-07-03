import json
import pandas as pd
import plotly.express as px
import streamlit as st


file_path = 'resultado_final.json'
with open(file_path) as f:
    data = json.load(f)

# Crear una lista para almacenar los datos procesados
processed_data = []

# Recorrer los datos y extraer la información relevante
for year_data in data:
    year = year_data['year']
    zonas = year_data['zonas']
    
    for zona in zonas:
        clubs = zona['clubes']
        
        for club in clubs:
            club_name = club['CLUB']
            categorias = club['CATEGORIAS']
            
            for categoria in categorias:
                if categoria["categoria"] == "Mosquitos":
                    continue
                processed_data.append({
                    'Categoria': categoria['categoria'],
                    'Temporada': year,
                    'Partidos Jugados': categoria['partidos jugados'],
                    'Partidos No Completados': categoria['partidos no completados'],
                    'Club': club_name
                })

# Convertir los datos procesados en un DataFrame de pandas
df = pd.DataFrame(processed_data)

# Agrupar los datos por año, club y categoría, sumando los partidos jugados y no completados
grouped_df = df.groupby(['Temporada', 'Club', 'Categoria']).agg({
    'Partidos Jugados': 'sum',
    'Partidos No Completados': 'sum'
}).reset_index()

# Transformar el DataFrame para que los partidos jugados y no completados sean filas separadas
melted_df = pd.melt(grouped_df, id_vars=['Temporada', 'Club', 'Categoria'], 
                    value_vars=['Partidos Jugados', 'Partidos No Completados'], 
                    var_name='Estado', value_name='Partidos')

# Configuración de Streamlit
st.title('Visualización de Partidos por Categoría y Temporada')
selected_clubs = st.multiselect('Selecciona uno o más Clubes', melted_df['Club'].unique())

# Filtrar los datos por los clubes seleccionados
filtered_df = melted_df[melted_df['Club'].isin(selected_clubs)]

# Agrupar los datos por temporada, categoría y estado, sumando los partidos
if not filtered_df.empty:
    aggregated_df = filtered_df.groupby(['Temporada', 'Categoria', 'Estado']).agg({
        'Partidos': 'sum'
    }).reset_index()
    
    # Crear un nuevo DataFrame para el tooltip
    tooltip_df = filtered_df.groupby(['Temporada', 'Categoria', 'Estado', 'Club']).agg({
        'Partidos': 'sum'
    }).reset_index()
    
    # Crear el gráfico interactivo con plotly
    fig = px.bar(
        aggregated_df,
        x='Categoria',
        y='Partidos',
        color='Estado',
        barmode='group',
        facet_col='Temporada',
        category_orders={'Categoria': sorted(aggregated_df['Categoria'].unique())},
        title=f'Partidos Jugados y No Completados por Categoría y Temporada - {", ".join(selected_clubs)}',
        labels={'Partidos': 'Cantidad de Partidos', 'Categoria': 'Categoría'},
    )

    # Añadir información detallada al tooltip
    custom_data = []
    for temp, cat, est in zip(aggregated_df['Temporada'], aggregated_df['Categoria'], aggregated_df['Estado']):
        clubs_data = tooltip_df[(tooltip_df['Temporada'] == temp) & (tooltip_df['Categoria'] == cat) & (tooltip_df['Estado'] == est)]
        breakdown = "<br>".join([f"{row['Club']}: {row['Partidos']}" for row in clubs_data.to_dict('records')])
        custom_data.append(breakdown)

    fig.update_traces(
        customdata=custom_data,
        hovertemplate='<br>'.join([
            'Categoría: %{x}',
            'Partidos: %{y}',
            'Desglose por club:<br>%{customdata}'
        ])
    )

    fig.update_layout(xaxis_tickangle=-90)

    # Mostrar el gráfico en Streamlit
    st.plotly_chart(fig, use_container_width=True)

    # Mostrar el DataFrame filtrado en Streamlit
    st.dataframe(filtered_df)
else:
    st.write("Por favor, selecciona al menos un club para visualizar los datos.")