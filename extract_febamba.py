import json
import requests

from bs4 import BeautifulSoup


url = "http://competicionescabb.gesdeportiva.es/competicion.aspx?competencia=1178"

response = requests.get(url)
html_content = response.text

# Parse the HTML content
soup = BeautifulSoup(html_content, 'html.parser')

competencia = {
    "categorias": []
}

def obtener_grupos(fase_url):
    response = requests.get(fase_url)
    html_content = response.text
    # Parse the HTML content
    soup = BeautifulSoup(html_content, 'html.parser')
    # Obtener grupos
    grupos_select = soup.find("select", {"name": "DDLGrupos"})
    grupos = []
    for option in grupos_select.find_all("option"):
        grupo_id = option["value"]
        grupo = option.text
        grupo_url = fase_url + f"&grupo={grupo_id}"
        grupos.append({"grupo_id": grupo_id, "grupo": grupo, "grupo_url": grupo_url})
    return grupos

def obtener_fases(cat_url):
    response = requests.get(cat_url)
    html_content = response.text
    # Parse the HTML content
    soup = BeautifulSoup(html_content, 'html.parser')
    # Obtener fases
    fases_select = soup.find("select", {"name": "DDLFases"})
    fases = []
    for option in fases_select.find_all("option"):
        fase_id = option["value"]
        fase = option.text
        fase_url = cat_url + f"&fase={fase_id}"
        grupos = obtener_grupos(fase_url)
        fases.append({"fase_id": fase_id, "fase": fase, "fase_url": fase_url, "grupos": grupos})
    return fases

# Obtener categorias
categorias_select = soup.find("select", {"name": "DDLCategorias"})
for option in categorias_select.find_all("option"):
    cat_id = option["value"]
    cat = option.text
    cat_url = f"http://competicionescabb.gesdeportiva.es/competicion.aspx?competencia=1178&categoria={cat_id}"
    fases = obtener_fases(cat_url)
    competencia["categorias"].append({"cat_id": cat_id, "cat": cat, "cat_url": cat_url, "fases": fases})

# Iterar sobre cada categoría
for categoria_index, categoria in enumerate(competencia["categorias"]):
    # Iterar sobre cada fase de la categoría
    for fase_index, fase in enumerate(categoria["fases"]):
        # Iterar sobre cada grupo de la fase
        for grupo_index, grupo in enumerate(fase["grupos"]):
            # Realizar la solicitud HTTP para obtener la información de los partidos del grupo
            response = requests.get(grupo["grupo_url"])
            html_content = response.text

            # Parsear el contenido HTML
            soup = BeautifulSoup(html_content, 'html.parser')

            # Encontrar el panel de pestañas con id "calendario"
            tab_pane = soup.find("div", id="calendario")

            # Encontrar todas las tablas dentro del panel de pestañas
            tables = tab_pane.find_all("table")

            # Inicializar un contador para los identificadores de los partidos
            partido_id = 1

            # Iterar sobre cada tabla de la página
            for table in tables:
                # Obtener la información de la jornada y la fecha
                jornada_fecha = table.find_previous("h4").text.strip()
                try:
                    jornada, fecha = jornada_fecha.split(" - ")
                except ValueError:
                    continue

                # Iterar sobre cada fila de la tabla
                for row in table.find_all("tr")[1:]:
                    # Extraer la información de cada celda de la fila
                    cells = row.find_all("td")
                    local = cells[0].text.strip()
                    puntos_local = cells[1].text.strip()
                    puntos_visitante = cells[2].text.strip()
                    visitante = cells[3].text.strip()
                    fecha_partido = cells[4].text.strip()

                    if local == "LOS INDIOS U13 NEGRO" or local == "LOS INDIOS U15 NEGRO" or local == "LOS INDIOS U17 NEGRO" or local == "LOS INDIOS U21 NEGRO":
                        local = "LOS INDIOS DE MORENO NEGRO"
                    if visitante == "LOS INDIOS U13 NEGRO" or visitante == "LOS INDIOS U15 NEGRO" or visitante == "LOS INDIOS U17 NEGRO" or visitante == "LOS INDIOS U21 NEGRO":
                        visitante = "LOS INDIOS DE MORENO NEGRO"
                    
                    if local == "LOS INDIOS U9 BLANCO" or local == "LOS INDIOS MINI BLANCO" or local == "LOS INDIOS U13 BLANCO" or local == "LOS INDIOS U15 BLANCO" or local == "LOS INDIOS U17 BLANCO" or local == "LOS INDIOS U21 BLANCO":
                        local = "LOS INDIOS DE MORENO BLANCO"
                    if visitante == "LOS INDIOS U9 BLANCO" or visitante == "LOS INDIOS MINI BLANCO" or visitante == "LOS INDIOS U13 BLANCO" or visitante == "LOS INDIOS U15 BLANCO" or visitante == "LOS INDIOS U17 BLANCO" or  visitante == "LOS INDIOS U21 BLANCO":
                        visitante = "LOS INDIOS DE MORENO BLANCO"

                    if local == "BANCO NACION":
                        local = "BANCO NACIÓN"
                    if visitante == "BANCO NACION":
                        visitante = "BANCO NACIÓN"
                    
                    if local == "JUVENTUD":
                        local = "JUVENTUD UNIDA"
                    if visitante == "JUVENTUD":
                        visitante = "JUVENTUD UNIDA"
                    
                    if local == "DEP.MORON BLANCO":
                        local = "DEP. MORON BLANCO"
                    if visitante == "DEP.MORON BLANCO":
                        visitante = "DEP. MORON BLANCO"
                    if local == "DEP.MORON ROJO":
                        local = "DEP. MORON ROJO"
                    if visitante == "DEP.MORON ROJO":
                        visitante = "DEP. MORON ROJO"
                    
                    if local == "ALL BOYS SAAVEDRA":
                        local = "ALL BOYS DE SAAVEDRA"
                    if visitante == "ALL BOYS SAAVEDRA":
                        visitante = "ALL BOYS DE SAAVEDRA"

                    if local == "INDEPENDIENTE de BURZACO":
                        local = "INDEPENDIENTE DE BURZACO"
                    if visitante == "INDEPENDIENTE de BURZACO":
                        visitante = "INDEPENDIENTE DE BURZACO"

                    # Crear un diccionario con la información del partido
                    partido = {
                        "Partido_ID": partido_id,
                        "Local": local,
                        "Puntos LOCAL": puntos_local,
                        "Puntos VISITA": puntos_visitante,
                        "Visitante": visitante,
                        "Fecha": fecha_partido,
                        "Jornada": jornada
                    }

                    # Incrementar el contador de identificadores de partidos
                    partido_id += 1

                    # Agregar el partido a la lista de partidos del grupo correspondiente
                    competencia["categorias"][categoria_index]["fases"][fase_index]["grupos"][grupo_index].setdefault("partidos", []).append(partido)

# Escribir la estructura competencia en un archivo JSON
with open('competencia.json', 'w') as json_file:
    json.dump(competencia, json_file, indent=4)

print("Se ha extraido exitosamente todos los partidos")