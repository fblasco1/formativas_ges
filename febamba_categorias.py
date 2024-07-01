import requests
import json
import re
import time
from bs4 import BeautifulSoup

def cargar_json(filename):
    with open(filename, 'r') as file:
        return json.load(file)

def guardar_json(data, filename):
    with open(filename, 'w') as file:
        json.dump(data, file, indent=4)

def hacer_solicitud(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error al realizar la solicitud a {url}: {e}")
        return None

def obtener_grupos(fase_url):
    html_content = hacer_solicitud(fase_url)
    if html_content is None:
        print(f"No se pudo obtener el contenido HTML para {fase_url}")
        return []
    soup = BeautifulSoup(html_content, 'html.parser')
    grupos_select = soup.find("select", {"name": "DDLGrupos"})
    if not grupos_select:
        print(f"No se encontraron grupos en {fase_url}")
        return []
    grupos = []
    for option in grupos_select.find_all("option"):
        grupo_id = option["value"]
        grupo = option.text
        grupo_url = fase_url + f"&grupo={grupo_id}"
        grupos.append({"grupo_id": grupo_id, "grupo": grupo, "grupo_url": grupo_url})
    return grupos

def obtener_fases(cat_url):
    html_content = hacer_solicitud(cat_url)
    if html_content is None:
        print(f"No se pudo obtener el contenido HTML para {cat_url}")
        return []
    soup = BeautifulSoup(html_content, 'html.parser')
    fases_select = soup.find("select", {"name": "DDLFases"})
    if not fases_select:
        print(f"No se encontraron fases en {cat_url}")
        return []
    fases = []
    for option in fases_select.find_all("option"):
        fase_id = option["value"]
        fase = option.text
        fase_url = cat_url + f"&fase={fase_id}"
        grupos = obtener_grupos(fase_url)
        if grupos:
            fase_con_partidos = False
            for grupo in grupos:
                html_grupo_content = hacer_solicitud(grupo["grupo_url"])
                if html_grupo_content:
                    soup_grupo = BeautifulSoup(html_grupo_content, 'html.parser')
                    tab_pane = soup_grupo.find("div", id="calendario")
                    if tab_pane:
                        fase_con_partidos = True
                        break
            if fase_con_partidos:
                fases.append({"fase_id": fase_id, "fase": fase, "fase_url": fase_url, "grupos": grupos})
    return fases

def normalizar_nombre_equipo(nombre):
    correcciones = {
        "LOS INDIOS U13 NEGRO": "LOS INDIOS DE MORENO NEGRO",
        "LOS INDIOS U15 NEGRO": "LOS INDIOS DE MORENO NEGRO",
        "LOS INDIOS U17 NEGRO": "LOS INDIOS DE MORENO NEGRO",
        "LOS INDIOS U21 NEGRO": "LOS INDIOS DE MORENO NEGRO",
        "LOS INDIOS U9 BLANCO": "LOS INDIOS DE MORENO BLANCO",
        "LOS INDIOS MINI BLANCO": "LOS INDIOS DE MORENO BLANCO",
        "LOS INDIOS U13 BLANCO": "LOS INDIOS DE MORENO BLANCO",
        "LOS INDIOS U15 BLANCO": "LOS INDIOS DE MORENO BLANCO",
        "LOS INDIOS U17 BLANCO": "LOS INDIOS DE MORENO BLANCO",
        "LOS INDIOS U21 BLANCO": "LOS INDIOS DE MORENO BLANCO",
        "BANCO NACION": "BANCO NACIÓN",
        "JUVENTUD": "JUVENTUD UNIDA",
        "DEP.MORON BLANCO": "DEP. MORON BLANCO",
        "DEP.MORON ROJO": "DEP. MORON ROJO",
        "ALL BOYS SAAVEDRA": "ALL BOYS DE SAAVEDRA",
        "INDEPENDIENTE de BURZACO": "INDEPENDIENTE DE BURZACO",
        "QUILMES A.C": "QUILMES A.C."
    }
    return correcciones.get(nombre, nombre)

def extraer_partidos(torneo, categoria_index, fase_index, grupo_index):
    grupo = torneo["categorias"][categoria_index]["fases"][fase_index]["grupos"][grupo_index]
    html_content = hacer_solicitud(grupo["grupo_url"])
    if html_content is None:
        print(f"No se pudo obtener el contenido HTML para {grupo['grupo_url']}")
        return
    soup = BeautifulSoup(html_content, 'html.parser')
    tab_pane = soup.find("div", id="calendario")
    if not tab_pane:
        print(f"No se encontró el panel de calendario en {grupo['grupo_url']}")
        return
    tables = tab_pane.find_all("table")
    partido_id = 1
    for table in tables:
        jornada_fecha = table.find_previous("h4").text.strip()
        try:
            jornada, fecha = jornada_fecha.split(" - ")
        except ValueError:
            continue
        for row in table.find_all("tr")[1:]:

            cells = row.find_all("td")
            local = normalizar_nombre_equipo(cells[0].text.strip())
            puntos_local = cells[1].text.strip()
            puntos_visitante = cells[2].text.strip()
            visitante = normalizar_nombre_equipo(cells[3].text.strip())
            fecha_partido = cells[4].text.strip()
            partido = {
                "Partido_ID": partido_id,
                "Local": local,
                "Puntos LOCAL": puntos_local,
                "Puntos VISITA": puntos_visitante,
                "Visitante": visitante,
                "Fecha": fecha_partido,
                "Jornada": jornada
            }
            partido_id += 1

            if "partidos" not in torneo["categorias"][categoria_index]["fases"][fase_index]["grupos"][grupo_index]:
                torneo["categorias"][categoria_index]["fases"][fase_index]["grupos"][grupo_index]["partidos"] = []
            torneo["categorias"][categoria_index]["fases"][fase_index]["grupos"][grupo_index]["partidos"].append(partido)
    print(f"Partidos extraídos para el grupo {grupo['grupo_url']}: {torneo['categorias'][categoria_index]['fases'][fase_index]['grupos'][grupo_index]}")

def filtrar_torneos_formativas(data):
    torneos_formativas = []
    for competencia in data['competencias']:
        try:
            if (competencia['federacion'] == 'FEDERACION DE BASQUETBOL DEL AREA METROPOLITANA DE BUENOS AIRES' and
                re.search(r'FORMATIVAS \d{4}', competencia['torneo'], re.IGNORECASE) and
                'flex' not in competencia['torneo'].lower()):
                    torneos_formativas.append(competencia)
        except KeyError as e:
            print(f"Error en competencia: {competencia}. Error: {e}")

    return torneos_formativas

def main():
    data = cargar_json('gesdeportiva.json')
    torneos_formativas = filtrar_torneos_formativas(data)
    for torneo in torneos_formativas:
        print(f"Torneo: {torneo['torneo']}, URL: {torneo['url']}")
        html_content = hacer_solicitud(torneo['url'])
        if html_content is None:
            continue
        soup = BeautifulSoup(html_content, 'html.parser')
        torneo["categorias"] = []
        categorias_select = soup.find("select", {"name": "DDLCategorias"})
        if not categorias_select:
            print(f"No se encontraron categorías en {torneo['url']}")
            continue
        for option in categorias_select.find_all("option"):
            cat_id = option["value"]
            cat = option.text
            cat_url = f"{torneo['url']}=&categoria={cat_id}"
            fases = obtener_fases(cat_url)
            torneo["categorias"].append({"cat_id": cat_id, "cat": cat, "cat_url": cat_url, "fases": fases})
            for categoria_index, categoria in enumerate(torneo["categorias"]):
                for fase_index, fase in enumerate(categoria["fases"]):
                    for grupo_index, _ in enumerate(fase["grupos"]):
                        extraer_partidos(torneo, categoria_index, fase_index, grupo_index)
    guardar_json(torneos_formativas, 'categorias.json')
    print("Se ha extraído exitosamente todos los partidos")

if __name__ == "__main__":
    main()
