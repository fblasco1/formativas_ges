import requests
import json
import re
import time
from bs4 import BeautifulSoup

def hacer_solicitud(url, max_intentos=10):
    intentos = 0
    while intentos < max_intentos:
        try:
            response = requests.get(url)
            if response.status_code == 200:
                return response.content
            else:
                print(f"Error al hacer solicitud a {url}: {response.status_code}")
        except Exception as e:
            print(f"Excepción al hacer solicitud a {url}: {e}")
        intentos += 1
        time.sleep(1)  # Espera 1 segundo antes de intentar nuevamente
    return None

def cargar_json(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)

def guardar_json(data, file_path):
    with open(file_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

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
        "LOS INDIOS A": "LOS INDIOS DE MORENO NEGRO",
        "LOS INDIOS B": "LOS INDIOS DE MORENO BLANCO",
        "LOS INDIOS U9 BLANCO": "LOS INDIOS DE MORENO BLANCO",
        "LOS INDIOS MINI BLANCO": "LOS INDIOS DE MORENO BLANCO",
        "LOS INDIOS U13 BLANCO": "LOS INDIOS DE MORENO BLANCO",
        "LOS INDIOS U15 BLANCO": "LOS INDIOS DE MORENO BLANCO",
        "LOS INDIOS U17 BLANCO": "LOS INDIOS DE MORENO BLANCO",
        "LOS INDIOS U21 BLANCO": "LOS INDIOS DE MORENO BLANCO",
        "PREMINI INDIOS NEGRO": "LOS INDIOS DE MORENO NEGRO",
        "MINI INDIOS NEGRO": "LOS INDIOS DE MORENO NEGRO",
        "U13 INDIOS NEGRO": "LOS INDIOS DE MORENO NEGRO",
        "U15 INDIOS NEGRO": "LOS INDIOS DE MORENO NEGRO",
        "U17 INDIOS NEGRO": "LOS INDIOS DE MORENO NEGRO",
        "U19 INDIOS NEGRO": "LOS INDIOS DE MORENO NEGRO",
        "PREMINI INDIOS BLANCO": "LOS INDIOS DE MORENO BLANCO",
        "MINI INDIOS BLANCO": "LOS INDIOS DE MORENO BLANCO",
        "U13 INDIOS BLANCO": "LOS INDIOS DE MORENO BLANCO",
        "U15 INDIOS BLANCO": "LOS INDIOS DE MORENO BLANCO",
        "U17 INDIOS BLANCO": "LOS INDIOS DE MORENO BLANCO",
        "U19 INDIOS BLANCO": "LOS INDIOS DE MORENO BLANCO",
        "CLUB PORTUGUES": "CLUB PORTUGUES DEL GRAN BUENOS AIRES",
        "PORTEÑO ATLETIC CLUB ZARATE CAMPANA": "PORTEÑO ATLETICO CLUB",
        "CLUB GIMNASIA Y ESGRIMA LA PLATA": "CLUB GIMNASIA Y ESGRIMA LA PLATA AZUL",
        "SPORTIVO ALSINA ORO": "SPORTIVO ALSINA", 
        "SP.ESCOBAR": "SPORTIVO ESCOBAR",
        "BCO.NACION": "BANCO NACIÓN",
        "BANCO NACION": "BANCO NACIÓN",
        "JUV.DE CAÑUELAS": "JUVENTUD UNIDA",
        "JUVENTUD": "JUVENTUD UNIDA",
        "DEPORTIVO MORON": "DEP. MORON BLANCO",
        "DEPORTIVO MORON - Mini": "DEP. MORON BLANCO",
        "DEPORTIVO MORON - Premini": "DEP. MORON BLANCO",
        "DEP.MORON BLANCO": "DEP. MORON BLANCO",
        "DEP.MORON ROJO": "DEP. MORON ROJO",
        "DEPORTIVO MORON B": "DEP. MORON ROJO",
        "DEPORTIVO MORON B - Sub 19": "DEP. MORON ROJO",
        "DEPORTIVO MORON B - Sub 17": "DEP. MORON ROJO",
        "DEPORTIVO MORON B -Sub 17": "DEP. MORON ROJO",
        "DEPORTIVO MORON B - Sub 13": "DEP. MORON ROJO",
        "DEPORTIVO MORON B - Mini": "DEP. MORON ROJO",
        "DEPORTIVO MORON B - Premini": "DEP. MORON ROJO",
        "DEPORTIVO MORON B - Sub 15": "DEP. MORON ROJO",
        "ALL BOYS SAAVEDRA": "ALL BOYS DE SAAVEDRA",
        "INDEPENDIENTE de BURZACO": "INDEPENDIENTE DE BURZACO",
        "QUILMES": "QUILMES A.C.",
        "QUILMES A.C": "QUILMES A.C.",
        "CAÑUELAS FC - Sub 19": "CAÑUELAS FC",
        "CAÑUELAS FC - Sub 17": "CAÑUELAS FC",
        "CAÑUELAS FC - Sub 15": "CAÑUELAS FC",
        "CAÑUELAS FC - Sub 13": "CAÑUELAS FC",
        "CAÑUELAS FC - Mini": "CAÑUELAS FC",
        "CAÑUELAS FC - Premini": "CAÑUELAS FC",
        "CAÑUELAS - Sub 19": "CAÑUELAS FC",
        "CAÑUELAS - Sub 17": "CAÑUELAS FC",
        "CAÑUELAS - Sub 15": "CAÑUELAS FC",
        "CAÑUELAS - Sub 13": "CAÑUELAS FC",
        "CAÑUELAS - Mini": "CAÑUELAS FC",
        "CAÑUELAS - Premini": "CAÑUELAS FC",
        "CANUELAS F.C.": "CAÑUELAS FC",
        "NÁUTICO BUCHARDO A": "NAUTICO BUCHARDO A",
        "NAUTICO BUCHARDO CENTRO (B)": "NAUTICO BUCHARDO B",
        "NAUTICO BUCHARDO CENTRO \"B\"": "NAUTICO BUCHARDO B",
        "NAUTICO BUCHARDO NORTE (A)": "NAUTICO BUCHARDO A",
        "NAUTICO BUCHARDO NORTE \"A\"": "NAUTICO BUCHARDO A",
        "NAUTICO BUCHARDO NORTE": "NAUTICO BUCHARDO A",
        "NAUTICO BUCHARDO": "NAUTICO BUCHARDO A",
        "UBA": "UNIVERSIDAD DE BUENOS AIRES",
        "BA.NA.DE.": "BANADE",
        "BA.NA.DE": "BANADE",
        "CLUB 3 DE FEBRERO BLANCO": "CLUB TRES DE FEBRERO BLANCO",
        "CLUB 3 DE FEBRERO AZUL": "CLUB TRES DE FEBRERO AZUL",
        "TRES DE FEBRERO": "CLUB TRES DE FEBRERO BLANCO",
        "TRES DE FEBRERO B": "CLUB TRES DE FEBRERO AZUL",
        "CIRCULO URQUIZA": "CIRCULO URQUIZA AZUL",
        "PLATENSE B": "PLATENSE BLANCO",
        "PLATENSE \"B\"": "PLATENSE BLANCO",
        "PLATENSE A": "PLATENSE MARRON",
        "PLATENSE \"A\"": "PLATENSE MARRON",
        "NAUTICO HACOAJ B": "NAUTICO HACOAJ AZUL",
        "NAUTICO HACOAJ": "NAUTICO HACOAJ BLANCO",
        "SAN FERNANDO B": "SAN FERNANDO BLANCO",
        "SAN FERNANDO": "SAN FERNANDO AZUL",
        "SP.VILLA BALLESTER": "SPORTIVO VILLA BALLESTER",
        "BALLESTER": "SPORTIVO VILLA BALLESTER",
        "SP.BALLESTER": "SPORTIVO VILLA BALLESTER",
        "SOC.BECCAR": "SOCIAL BECCAR",
        "U.V.MUNRO": "UNION VECINAL DE MUNRO",
        "HARRODS": "HARRODS GATH Y CHAVES",
        "LAS HERAS": "LAS HERAS A",
        "CAZA Y PESCA": "CAZA Y PESCA A",
        "ATL.BOULOGNE": "ATLETICO BOULOGNE",
        "VILLA ADELINA": "U.V.V.ADELINA",
        "U.V.V.A. UNION VECINAL VILLA ADELINA" : "U.V.V.ADELINA",
        "CIUDAD DE BS.AS.": "CIUDAD DE BUENOS AIRES A",
        "CIUDAD DE BS.AS. B": "CIUDAD DE BUENOS AIRES B",
        "12 DE OCTUBRE": "CLUB 12 DE OCTUBRE",
        "CLUB DEPORTIVO SAN ANDRES": "DEPORTIVO SAN ANDRES",
        "CLUB DEPORTIVO SAN ANDRÉS": "DEPORTIVO SAN ANDRES",
        "G.E.V.PARQUE": "GEVP BLANCO",
        "G.E.V.PARQUE B": "GEVP CELESTE",
        "A.F.A.L.P.": "A.F.A.L.P. A",
        'A.F.A.L.P. "A"': "A.F.A.L.P. A",
        "BOCA JUNIORS": "BOCA JUNIORS AZUL",
        "BOCA JUNIORS \"A\"": "BOCA JUNIORS AZUL",
        "BOCA JUNIORS \"AZUL\"": "BOCA JUNIORS AZUL",
        "BOCA JUNIORS \"B\"": "BOCA JUNIORS AMARILLO",
        "BOCA JUNIORS B": "BOCA JUNIORS AMARILLO",
        "BOCA JUNIORS \"AMARILLO\"": "BOCA JUNIORS AMARILLO",
        "LANUS": "LANUS A",
        "HURACAN DE SAN JUSTO A" : "HURACAN DE SAN JUSTO ROJO",
        "HURACAN DE SAN JUSTO B" : "HURACAN DE SAN JUSTO BLANCO",
        "G.Y E. DE LOMAS DE ZAMORA": "G.E DE LOMAS DE ZAMORA A",
        "G Y E DE LOMAS DE ZAMORA": "G.E DE LOMAS DE ZAMORA A",
        "G.E.LOMAS A": "G.E DE LOMAS DE ZAMORA A",
        "G.Y E. DE LOMAS DE ZAMORA B": "G.E DE LOMAS DE ZAMORA B",
        "G Y E DE LOMAS DE ZAMORA B": "G.E DE LOMAS DE ZAMORA B",
        "G.E.LOMAS B": "G.E DE LOMAS DE ZAMORA B",
        "PEDRO ECHAGUE B": "PEDRO ECHAGUE AMARILLO",
        "PEDRO ECHAGUE": "PEDRO ECHAGUE AZUL",
        "MORON": "MORON A",
        "VELEZ SARSFIELD": "VELEZ SARSFIELD BLANCO",
        "VELEZ SARSFIELD B": "VELEZ SARSFIELD AZUL",
        "GIMNASIA Y ESGRIMA DE ITUZAINGO B": "Club GEI BLANCO",
        "GIMNASIA Y ESGRIMA DE ITUZAINGO": "Club GEI AZUL",
        "GIMNASIA ESGRIMA DE ITUZAINGO B": "Club GEI BLANCO",
        "GIMNASIA ESGRIMA DE ITUZAINGO": "Club GEI AZUL",
        "GIMNASIA ESGRIMA DE ITUZAIGO": "Club GEI AZUL",
        "GEI AZUL": "Club GEI AZUL",
        "GEI BLANCO": "Club GEI BLANCO",
        "G.E.ITUZAINGO": "Club GEI AZUL",
        "G.E.ITUZAINGO B": "Club GEI BLANCO",
        "GEI B": "Club GEI BLANCO",
        "G Y E DE ITUZAINGO B": "Club GEI BLANCO",
        "DEF.DE S.LUGARES": "DEFENSORES DE SANTOS LUGARES",
        "ITALIANO J.C.PAZ": "ITALIANO DE JOSE C PAZ",
        "RAMOS MEJIA LTC. B" : "RAMOS MEJIA LTC B",
        "RAMOS MEJIA LTC." : "RAMOS MEJIA LTC",
        "ARGENTINOS JRS.": "ARGENTINOS JUNIORS",
        "ARGENTINOS DE CASTELAR B": "ARGENTINO DE CASTELAR CENTRO",
        "ARGENTINO DE CASTELAR SUR": "ARGENTINO DE CASTELAR CENTRO",
        "ARGENTINOS DE CASTELAR": "ARGENTINO DE CASTELAR NORTE",
        "ARGENTINOS DE CASTELAR A": "ARGENTINO DE CASTELAR NORTE",
        "ARGENTINO DE CASTELAR A": "ARGENTINO DE CASTELAR NORTE",
        "S.A.DE PADUA B": "C.A.S.A PADUA B",
        "S.A.DE PADUA": "C.A.S.A PADUA A",
        "C.A.S.A DE PADUA": "C.A.S.A PADUA A",
        "C.A.S.A PADUA": "C.A.S.A PADUA A",
        "CLUB ATLETICO EL PALOMAR": "EL PALOMAR",
        "S.I.T.A.S.":"SITAS",
        "ESTUDIANTIL PORTENO": "ESTUDIANTIL PORTEÑO A",
        "ESTUDIANTIL PORTENO B": "ESTUDIANTIL PORTEÑO B",
        "ESTUDIANTIL PORTEÑO \"A\"": "ESTUDIANTIL PORTEÑO A",
        "ESTUDIANTIL PORTEÑO \"B\"": "ESTUDIANTIL PORTEÑO B",
        "INST.SARMIENTO A": "INSTITUCION SARMIENTO VERDE",
        "INST.SARMIENTO B": "INSTITUCION SARMIENTO BLANCO",
        "INSTITUCION SARMIENTO": "INSTITUCION SARMIENTO VERDE",
        "INSTITUCION SARMIENTO B": "INSTITUCION SARMIENTO BLANCO",
        "SAN MIGUEL Blanco": "SAN MIGUEL BLANCO",
        "UNIVERSIDAD LA MATANZA": "UNLAM A",
        "UNLAM": "UNLAM A",
        "MIDLAND FC": "MIDLAND",
        "ALEM": "LEANDRO N ALEM",
        "ALEM LEANDRO N.": "LEANDRO N ALEM",
        "ALEM LEANDRO N": "LEANDRO N ALEM",
        "UNITARIOS": "UNITARIOS DE MARCOS PAZ",
        "DEF.DE HURLINGHAM": "DEFENSORES DE HURLINGHAM VERDE",
        "DEF.HURLINGHAM": "DEFENSORES DE HURLINGHAM VERDE",
        "DEFENSORES DE HURLINGHAM": "DEFENSORES DE HURLINGHAM VERDE",
        "MUNICIPALIDAD AVELLANEDA":"MUNICIPALIDAD DE AVELLANEDA",
        "MUNIC.AVELLANEDA": "MUNICIPALIDAD DE AVELLANEDA",
        "BURZACO F.C. B": "BURZACO FC B",
        "BURZACO F.C.": "BURZACO FC A",
        "BURZACO FC": "BURZACO FC A",
        "COLON F.C.": "COLON FC",
        "DEF. BANFIELD": "DEFENSORES DE BANFIELD",
        "DEF.BANFIELD": "DEFENSORES DE BANFIELD",
        "INDEP.DE BURZACO" : "INDEPENDIENTE DE BURZACO",
        "BERNAL": "CLUB ATLETICO BERNAL",
        "VARELA JUNIOR": "VARELA JRS",
        "COUNTRY C.I.B.": "COUNTRY BANFIELD",
        "VILLA ESPANA": "VILLA ESPAÑA",
        "CLUB ATLETICO TEMPERLEY": "TEMPERLEY",
        "C.A.TEMPERLEY": "TEMPERLEY",
        "RACING": "RACING CLUB",
        "CLUB SOCIAL Y DEPORTIVO PINOCHO VERDE": "PINOCHO VERDE",
        "CLUB SOCIAL Y DEPORTIVO PINOCHO BLANCO": "PINOCHO BLANCO",
        "CLUB PINOCHO": "PINOCHO",
        "JOSE HERNANDEZ": "JOSE HERNANDEZ A",
        "SAN LORENZO": "SAN LORENZO AZUL",
        "SAN LORENZO B": "SAN LORENZO ROJO",
        "U.GRAL.ARMENIA": "ARMENIA",
        "C.A. NUEVA CHICAGO": "NUEVA CHICAGO",
        "EL TALAR A": "EL TALAR",
        "IMPERIO JRS. B": "IMPERIO NEGRO",
        "IMPERIO JRS.": "IMPERIO BLANCO",
        "IMPERIO JRS": "IMPERIO BLANCO",
        "ALL BOYS": "ALL BOYS BLANCO",
        "U.A.I URQUIZA": "UAI URQUIZA",
        "CLUB COLEGIALES B": "COLEGIALES NEGRO",
        "CLUB COLEGIALES A": "COLEGIALES BLANCO",
        "COLEGIALES A": "COLEGIALES BLANCO",
        "COLEGIALES B": "COLEGIALES NEGRO",
        "COLEGIO COPELLO": "COPELLO",
        "VILLA GRAL. MITRE": "VILLA MITRE",
        "ATENEO P.VERSAILLES": "APV",
        "ATENEO P. VERSAILLES": "APV",
        "OHA MACABI": "MACABI",
        "G.E.BUENOS AIRES": "GEBA",
        "ARQUITECTURA": "ARQUITECTURA NEGRO",
        "FERROCARRIL OESTE": "FERROCARRIL OESTE A",
        "FERRO CARRIL OESTE": "FERROCARRIL OESTE A",
        "FERRO CARRIL OESTE B": "FERROCARRIL OESTE B",
        "FERRO CARRIL OESTE C": "FERROCARRIL OESTE C",
        "Club Social Deportivo y Cultural Moreno": "MORENO DE QUILMES",
        "PAMPERO": "CLUB ATLETICO PAMPERO",
        "CLUB VECINAL LA UNION": "LA UNION",
        "COOP DE TORTUGUITAS": "COOPERATIVA TORTUGUITAS",
        "TORTUGUITAS BASKET": "COOPERATIVA TORTUGUITAS",
    }
    return correcciones.get(nombre, nombre)

def partido_existe(partidos, partido):
    for p in partidos:
        if (p["Local"] == partido["Local"] and
            p["Visitante"] == partido["Visitante"] and
            p["Puntos LOCAL"] == partido["Puntos LOCAL"] and
            p["Puntos VISITA"] == partido["Puntos VISITA"] and
            p["Fecha"] == partido["Fecha"] and
            p["Jornada"] == partido["Jornada"]):
            return True
    return False

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

            if not partido_existe(torneo["categorias"][categoria_index]["fases"][fase_index]["grupos"][grupo_index]["partidos"], partido):
                torneo["categorias"][categoria_index]["fases"][fase_index]["grupos"][grupo_index]["partidos"].append(partido)


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
