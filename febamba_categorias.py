import requests
import json
import re
import time
import pandas as pd
from datetime import datetime
from collections import defaultdict
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

def aplicar_desempates(tabla_posiciones, partidos):
    # Encontrar los equipos empatados en la tabla
    empates = encontrar_equipos_empatados(tabla_posiciones)
    
    for equipos_empatados in empates:
        # Aplicar desempate olímpico
        tabla_posiciones, desempate_resuelto = desempate_olimpico(equipos_empatados, partidos, tabla_posiciones)
        
        # Si el desempate olímpico no resolvió el empate, aplicar el siguiente criterio
        if not desempate_resuelto:
            tabla_posiciones, desempate_resuelto = desempate_coeficiente(equipos_empatados, tabla_posiciones)
        
        # Si el empate aún persiste, aplicar el último criterio
        if not desempate_resuelto:
            tabla_posiciones, desempate_resuelto = desempate_promedio_victorias(equipos_empatados, tabla_posiciones)
    
    # Ordenar la tabla por la posición
    tabla_posiciones.sort(key=lambda x: x['Pos'])
    return tabla_posiciones

def encontrar_equipos_empatados(tabla_posiciones):
    equipos_empatados = []
    empates = []
    for i in range(len(tabla_posiciones)):
        if i > 0 and tabla_posiciones[i]['Pos'] == tabla_posiciones[i - 1]['Pos']:
            equipos_empatados.append(tabla_posiciones[i])
        else:
            if len(equipos_empatados) > 1:
                empates.append(equipos_empatados)
            equipos_empatados = [tabla_posiciones[i]]
    
    if len(equipos_empatados) > 1:
        empates.append(equipos_empatados)
    
    return empates

def desempate_olimpico(equipos, partidos, tabla_posiciones):
    pos_inicio = equipos[0]['Pos']  # La posición de inicio para actualizar las posiciones
    desempate_resuelto = False
    
    if len(equipos) == 2:  # Si hay un empate de 2 equipos
        equipo1, equipo2 = equipos[0], equipos[1]
        ganados_e1, ganados_e2 = 0, 0
        puntos_e1, puntos_e2 = 0, 0
        dif_gol_e1, dif_gol_e2 = 0, 0
        
        for partido in partidos:
            if partido['Local'] == equipo1['Equipo'] and partido['Visitante'] == equipo2['Equipo']:
                puntos_e1 += int(partido['Puntos LOCAL'])
                puntos_e2 += int(partido['Puntos VISITA'])
                if puntos_e1 > puntos_e2:
                    ganados_e1 += 1
                else:
                    ganados_e2 += 1
                dif_gol_e1 += int(partido['Puntos LOCAL']) - int(partido['Puntos VISITA'])
                dif_gol_e2 += int(partido['Puntos VISITA']) - int(partido['Puntos LOCAL'])
            elif partido['Local'] == equipo2['Equipo'] and partido['Visitante'] == equipo1['Equipo']:
                puntos_e2 += int(partido['Puntos LOCAL'])
                puntos_e1 += int(partido['Puntos VISITA'])
                if puntos_e1 > puntos_e2:
                    ganados_e1 += 1
                else:
                    ganados_e2 += 1
                dif_gol_e2 += int(partido['Puntos LOCAL']) - int(partido['Puntos VISITA'])
                dif_gol_e1 += int(partido['Puntos VISITA']) - int(partido['Puntos LOCAL'])

        if ganados_e1 != ganados_e2:
            equipos.sort(key=lambda x: ganados_e1 if x['Equipo'] == equipo1['Equipo'] else ganados_e2, reverse=True)
            desempate_resuelto = True
        elif dif_gol_e1 != dif_gol_e2:
            equipos.sort(key=lambda x: dif_gol_e1 if x['Equipo'] == equipo1['Equipo'] else dif_gol_e2, reverse=True)
            desempate_resuelto = True
        elif equipo1["DIF"] != equipo2["DIF"]:
            equipos.sort(key=lambda x: equipo1["DIF"] if x['Equipo'] == equipo1['Equipo'] else equipo2["DIF"], reverse=True)
            desempate_resuelto = True
        
        # Si el desempate resuelve el empate
        if desempate_resuelto:
            for i, equipo in enumerate(equipos, start=pos_inicio):
                equipo['Pos'] = i
            equipos.clear()  # Limpiar el listado de equipos empatados

    elif len(equipos) > 2:  # Si hay un empate de más de 2 equipos
        # Crear una nueva clasificación temporal solo con los partidos entre los equipos empatados
        clasificacion_temporal = {equipo['Equipo']: {'PTS': 0, 'DIF': 0, 'PC': 0, 'PJ': 0} for equipo in equipos}

        for partido in partidos:
            if partido['Local'] in clasificacion_temporal and partido['Visitante'] in clasificacion_temporal:
                local = partido['Local']
                visitante = partido['Visitante']
                puntos_local = int(partido['Puntos LOCAL'])
                puntos_visitante = int(partido['Puntos VISITA'])
                
                clasificacion_temporal[local]['PC'] += puntos_local
                clasificacion_temporal[local]['PJ'] += 1
                clasificacion_temporal[visitante]['PC'] += puntos_visitante
                clasificacion_temporal[visitante]['PJ'] += 1
                
                if puntos_local > puntos_visitante:
                    clasificacion_temporal[local]['PTS'] += 2
                elif puntos_local < puntos_visitante:
                    clasificacion_temporal[visitante]['PTS'] += 2
                else:
                    clasificacion_temporal[local]['PTS'] += 1
                    clasificacion_temporal[visitante]['PTS'] += 1
                
                clasificacion_temporal[local]['DIF'] += puntos_local - puntos_visitante
                clasificacion_temporal[visitante]['DIF'] += puntos_visitante - puntos_local

        # Ordenar la clasificación temporal por puntos, diferencia de goles y promedio de puntos
        equipos.sort(key=lambda x: (
            clasificacion_temporal[x['Equipo']]['PTS'],
            clasificacion_temporal[x['Equipo']]['DIF'],
            clasificacion_temporal[x['Equipo']]['PC'] / clasificacion_temporal[x['Equipo']]['PJ']
        ), reverse=True)

        # Verificar si el desempate se resolvió
        if len(set(clasificacion_temporal[equipo['Equipo']]['PTS'] for equipo in equipos)) > 1:
            desempate_resuelto = True
        
        if desempate_resuelto:
            for i, equipo in enumerate(equipos, start=pos_inicio):
                equipo['Pos'] = i

    return tabla_posiciones, desempate_resuelto

def desempate_coeficiente(equipos, tabla_posiciones):
    pos_inicio = equipos[0]['Pos']  # La posición de inicio para actualizar las posiciones
    desempate_resuelto = False
    
    equipos.sort(key=lambda x: x['PC'] / x['PR'], reverse=True)

    # Verificar si el desempate se resolvió
    if len(set(equipo['PC'] / equipo['PR'] for equipo in equipos)) > 1:
        desempate_resuelto = True
    
    for i, equipo in enumerate(equipos, start=pos_inicio):
        equipo['Pos'] = i

    return tabla_posiciones, desempate_resuelto

def desempate_promedio_victorias(equipos, tabla_posiciones):
    pos_inicio = equipos[0]['Pos']  # La posición de inicio para actualizar las posiciones
    desempate_resuelto = False
    
    equipos.sort(key=lambda x: x['PG'] / x['PJ'], reverse=True)

    # Verificar si el desempate se resolvió
    if len(set(equipo['PG'] / equipo['PJ'] for equipo in equipos)) > 1:
        desempate_resuelto = True
    
    for i, equipo in enumerate(equipos, start=pos_inicio):
        equipo['Pos'] = i 

    return tabla_posiciones, desempate_resuelto

fecha_actual = datetime.now()

# Función para calcular los puntos y la tabla de posiciones
def calcular_puntos_y_posiciones(partidos):
    stats = {}
    # Iterar sobre cada fila del DataFrame
    for partido in partidos:
        local = partido["Local"]
        visitante = partido["Visitante"]
        try:
            puntos_local = int(partido["Puntos LOCAL"])
            puntos_visitante = int(partido["Puntos VISITA"])

            # Verificar si ambos equipos no se presentaron
            if puntos_local == 1 and puntos_visitante == 1:
                if local not in stats:
                    stats[local] = {"Partidos Jugados": 1, "Partidos Ganados": 0, "Partidos Perdidos": 0, "Partidos no presentados": 1, "PUNTOS": 0, "Puntos Convertidos": 0, "Puntos Recibidos": 0}
                else:
                    stats[local]["Partidos Jugados"] += 1
                    stats[local]["Partidos no presentados"] += 1

                if visitante not in stats:
                    stats[visitante] = {"Partidos Jugados": 1, "Partidos Ganados": 0, "Partidos Perdidos": 0, "Partidos no presentados": 1, "PUNTOS": 0, "Puntos Convertidos": 0, "Puntos Recibidos": 0}
                else:
                    stats[visitante]["Partidos Jugados"] += 1
                    stats[visitante]["Partidos no presentados"] += 1

            # Verificar si un equipo ganó y el otro no se presentó
            elif puntos_local == 20 and puntos_visitante == 0:
                if local not in stats:
                    stats[local] = {"Partidos Jugados": 1, "Partidos Ganados": 1, "Partidos Perdidos": 0, "Partidos no presentados": 0, "PUNTOS": 2, "Puntos Convertidos": puntos_local, "Puntos Recibidos": puntos_visitante}
                else:
                    stats[local]["Partidos Jugados"] += 1
                    stats[local]["Partidos Ganados"] += 1
                    stats[local]["PUNTOS"] += 2
                    stats[local]["Puntos Convertidos"] += puntos_local
                    stats[local]["Puntos Recibidos"] += puntos_visitante

                if visitante not in stats:
                    stats[visitante] = {"Partidos Jugados": 1, "Partidos Ganados": 0, "Partidos Perdidos": 0, "Partidos no presentados": 1, "PUNTOS": 0, "Puntos Convertidos": puntos_visitante, "Puntos Recibidos": puntos_local}
                else:
                    stats[visitante]["Partidos Jugados"] += 1
                    stats[visitante]["Partidos no presentados"] += 1
                    stats[visitante]["Puntos Convertidos"] += puntos_visitante
                    stats[visitante]["Puntos Recibidos"] += puntos_local

            # Verificar si un equipo ganó y el otro no se presentó
            elif puntos_visitante == 20 and puntos_local == 0:
                if visitante not in stats:
                    stats[visitante] = {"Partidos Jugados": 1, "Partidos Ganados": 1, "Partidos Perdidos": 0, "Partidos no presentados": 0, "PUNTOS": 2, "Puntos Convertidos": puntos_visitante, "Puntos Recibidos": puntos_local}
                else:
                    stats[visitante]["Partidos Jugados"] += 1
                    stats[visitante]["Partidos Ganados"] += 1
                    stats[visitante]["PUNTOS"] += 2
                    stats[visitante]["Puntos Convertidos"] += puntos_visitante
                    stats[visitante]["Puntos Recibidos"] += puntos_local

                if local not in stats:
                    stats[local] = {"Partidos Jugados": 1, "Partidos Ganados": 0, "Partidos Perdidos": 0, "Partidos no presentados": 1, "PUNTOS": 0, "Puntos Convertidos": puntos_local, "Puntos Recibidos": puntos_visitante}
                else:
                    stats[local]["Partidos Jugados"] += 1
                    stats[local]["Partidos no presentados"] += 1
                    stats[local]["Puntos Convertidos"] += puntos_local
                    stats[local]["Puntos Recibidos"] += puntos_visitante

            # Calcular el ganador y el perdedor
            else:
                if puntos_local > puntos_visitante:
                    ganador = local
                    perdedor = visitante

                    if ganador not in stats:
                        stats[ganador] = {"Partidos Jugados": 1, "Partidos Ganados": 1, "Partidos Perdidos": 0, "Partidos no presentados": 0, "PUNTOS": 2, "Puntos Convertidos": puntos_local, "Puntos Recibidos": puntos_visitante}
                    else:
                        stats[ganador]["Partidos Jugados"] += 1
                        stats[ganador]["Partidos Ganados"] += 1
                        stats[ganador]["PUNTOS"] += 2
                        stats[ganador]["Puntos Convertidos"] += puntos_local
                        stats[ganador]["Puntos Recibidos"] += puntos_visitante

                    if perdedor not in stats:
                        stats[perdedor] = {"Partidos Jugados": 1, "Partidos Ganados": 0, "Partidos Perdidos": 1, "Partidos no presentados": 0, "PUNTOS": 1, "Puntos Convertidos": puntos_visitante, "Puntos Recibidos": puntos_local}
                    else:
                        stats[perdedor]["Partidos Jugados"] += 1
                        stats[perdedor]["Partidos Perdidos"] += 1
                        stats[perdedor]["PUNTOS"] += 1
                        stats[perdedor]["Puntos Convertidos"] += puntos_visitante
                        stats[perdedor]["Puntos Recibidos"] += puntos_local

                elif puntos_local < puntos_visitante:
                    ganador = visitante
                    perdedor = local
                    if ganador not in stats:
                        stats[ganador] = {"Partidos Jugados": 1, "Partidos Ganados": 1, "Partidos Perdidos": 0, "Partidos no presentados": 0, "PUNTOS": 2, "Puntos Convertidos": puntos_visitante, "Puntos Recibidos": puntos_local}
                    else:
                        stats[ganador]["Partidos Jugados"] += 1
                        stats[ganador]["Partidos Ganados"] += 1
                        stats[ganador]["PUNTOS"] += 2
                        stats[ganador]["Puntos Convertidos"] += puntos_visitante
                        stats[ganador]["Puntos Recibidos"] += puntos_local

                    if perdedor not in stats:
                        stats[perdedor] = {"Partidos Jugados": 1, "Partidos Ganados": 0, "Partidos Perdidos": 1, "Partidos no presentados": 0, "PUNTOS": 1, "Puntos Convertidos": puntos_local, "Puntos Recibidos": puntos_visitante}
                    else:
                        stats[perdedor]["Partidos Jugados"] += 1
                        stats[perdedor]["Partidos Perdidos"] += 1
                        stats[perdedor]["PUNTOS"] += 1
                        stats[perdedor]["Puntos Convertidos"] += puntos_local
                        stats[perdedor]["Puntos Recibidos"] += puntos_visitante
                else:
                    continue
       
        except ValueError:
            continue

    # Crear DataFrame con los datos calculados
    df_stats = pd.DataFrame.from_dict(stats, orient='index')
    df_stats.index.name = 'Equipo'
    df_stats.reset_index(inplace=True)
    df_stats["PJ"] = df_stats["Partidos Jugados"]
    df_stats["PTS"] = df_stats["PUNTOS"]
    df_stats["PG"] = df_stats["Partidos Ganados"]
    df_stats["PP"] = df_stats["Partidos Perdidos"]
    df_stats["NP"] = df_stats["Partidos no presentados"]
    df_stats["PC"] = df_stats["Puntos Convertidos"]
    df_stats["PR"] = df_stats["Puntos Recibidos"]
    df_stats["DIF"] = df_stats["PC"] - df_stats["PR"]
    df_stats["%VICT"] = (df_stats["PG"] / df_stats["PJ"]) * 100
    df_stats.fillna(0, inplace=True)
    df_stats.drop(columns=["Partidos Jugados", "PUNTOS", "Partidos Ganados", "Partidos Perdidos", "Partidos no presentados", "Puntos Convertidos", "Puntos Recibidos"], inplace=True)
    
    # Ordenar DataFrame por Puntos y Porcentaje de Victorias
    df_stats.sort_values(by=["PTS", "%VICT"], ascending=[False, False], inplace=True)

    # Asignar posiciones y manejar empates
    df_stats["Pos"] = range(1, len(df_stats) + 1)
    pos_actual = 1
    for i in range(1, len(df_stats)):
        if df_stats.iloc[i]["PTS"] == df_stats.iloc[i-1]["PTS"]:
            df_stats.at[df_stats.index[i], "Pos"] = pos_actual
        else:
            pos_actual = i + 1
            df_stats.at[df_stats.index[i], "Pos"] = pos_actual

    return aplicar_desempates(df_stats.to_dict(orient="records"), partidos)

# Función para combinar datos por nivel y zona geográfica
def combinar_datos_por_nivel_zona(data):
    nueva_estructura = []
    
    # Estructura para almacenar datos intermedios
    niveles_dict = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"subzonas": []}))))

    for fase in data['fases']:
        fase_nombre = fase['fase']
        for grupo in fase['grupos']:
            if fase["torneo"] == "Torneo Formativas 2019":
                if fase_nombre in ["SUR 1RA FASE", "OESTE 1RA FASE", "CENTRO 1RA FASE", "NORTE 1RA FASE"]:
                    nivel_zona = grupo['grupo'].split(' ')[1:3]  # Obtener ZONA, NIVEL, SUBZONA
                    nivel = f"NIVEL {nivel_zona[1]}"
                    try:
                        zona = nivel_zona[0]
                        subzona = nivel_zona[2]

                        for categoria in grupo['categorias']:
                            categoria_nombre = categoria['categoria']
                            niveles_dict[nivel][zona]["1ER FASE"][categoria_nombre]["url"] = categoria['url']

                            partidos = categoria["partidos"]

                            # Corregir el formato de la fecha y filtrar los partidos que no se han jugado
                            partidos_jugados = []
                            partido_error_fecha = []

                            for partido in partidos:
                                try:
                                    fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y%H:%M")
                                except ValueError:
                                    try:
                                        fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y")
                                    except ValueError:
                                        partido_error_fecha.append(partido)
                                if fecha_partido <= fecha_actual and (partido["Puntos LOCAL"] != '' or partido["Puntos VISITA"] != ''):
                                    partidos_jugados.append(partido)

                            if len(partidos_jugados) == 0:       
                                niveles_dict[nivel][zona]["1ER FASE"][categoria_nombre]["partidos"] = partidos
                            else:
                                niveles_dict[nivel][zona]["1ER FASE"][categoria_nombre]["subzonas"].append({
                                    "subzona": subzona,
                                    "partidos": partidos,
                                    "tabla_posiciones": calcular_puntos_y_posiciones(partidos_jugados),
                                })

                    except IndexError:
                            print(IndexError, grupo["grupo"])
                elif fase_nombre in ["CONFERENCIA 1 2DA FASE", "CONFERENCIA 2 2DA FASE"]:
                    nivel_zona = grupo['grupo'].split(' ')  # Obtener SUBZONA, ZONA, NIVEL
                    print(nivel_zona)
                    nivel = f"NIVEL {nivel_zona[3]}"
                    try:
                        zona = nivel_zona[2]
                        subzona = nivel_zona[1]

                        for categoria in grupo['categorias']:
                            categoria_nombre = categoria['categoria']
                            niveles_dict[nivel][zona]["2DA FASE"][categoria_nombre]["url"] = categoria['url']

                            partidos = categoria["partidos"]

                            # Corregir el formato de la fecha y filtrar los partidos que no se han jugado
                            partidos_jugados = []
                            partido_error_fecha = []

                            for partido in partidos:
                                try:
                                    fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y%H:%M")
                                except ValueError:
                                    try:
                                        fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y")
                                    except ValueError:
                                        partido_error_fecha.append(partido)
                                if fecha_partido <= fecha_actual and (partido["Puntos LOCAL"] != '' or partido["Puntos VISITA"] != ''):
                                    partidos_jugados.append(partido)

                            if len(partidos_jugados) == 0:       
                                niveles_dict[nivel][zona]["2DA FASE"][categoria_nombre]["partidos"] = partidos
                            else:
                                niveles_dict[nivel][zona]["2DA FASE"][categoria_nombre]["subzonas"].append({
                                    "subzona": subzona,
                                    "partidos": partidos,
                                    "tabla_posiciones": calcular_puntos_y_posiciones(partidos_jugados),
                                })

                    except IndexError:
                            print(IndexError, grupo["grupo"])
                elif fase_nombre in ["CONFERENCIA SUR 2 2DA FASE"]:
                    nivel_zona = grupo['grupo'].split(' ')  # Obtener ZONA, SUBZONA, NIVEL
                    print(nivel_zona)
                    nivel = f"NIVEL {nivel_zona[3]}"
                    try:
                        zona = nivel_zona[1]
                        subzona = nivel_zona[2]

                        for categoria in grupo['categorias']:
                            categoria_nombre = categoria['categoria']
                            niveles_dict[nivel][zona]["2DA FASE"][categoria_nombre]["url"] = categoria['url']

                            partidos = categoria["partidos"]

                            # Corregir el formato de la fecha y filtrar los partidos que no se han jugado
                            partidos_jugados = []
                            partido_error_fecha = []

                            for partido in partidos:
                                try:
                                    fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y%H:%M")
                                except ValueError:
                                    try:
                                        fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y")
                                    except ValueError:
                                        partido_error_fecha.append(partido)
                                if fecha_partido <= fecha_actual and (partido["Puntos LOCAL"] != '' or partido["Puntos VISITA"] != ''):
                                    partidos_jugados.append(partido)

                            if len(partidos_jugados) == 0:       
                                niveles_dict[nivel][zona]["2DA FASE"][categoria_nombre]["partidos"] = partidos
                            else:
                                niveles_dict[nivel][zona]["2DA FASE"][categoria_nombre]["subzonas"].append({
                                    "subzona": subzona,
                                    "partidos": partidos,
                                    "tabla_posiciones": calcular_puntos_y_posiciones(partidos_jugados),
                                })

                    except IndexError:
                            print(IndexError, grupo["grupo"])
                elif fase_nombre in ["CONFERENCIA 3 SUR 2DA FASE"]:
                    nivel = "NIVEL 3"
                    try:
                        zona = "SUR"

                        for categoria in grupo['categorias']:
                            categoria_nombre = categoria['categoria']
                            niveles_dict[nivel][zona]["2DA FASE"][categoria_nombre]["url"] = categoria['url']

                            partidos = categoria["partidos"]

                            # Corregir el formato de la fecha y filtrar los partidos que no se han jugado
                            partidos_jugados = []
                            partido_error_fecha = []

                            for partido in partidos:
                                try:
                                    fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y%H:%M")
                                except ValueError:
                                    try:
                                        fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y")
                                    except ValueError:
                                        partido_error_fecha.append(partido)
                                if fecha_partido <= fecha_actual and (partido["Puntos LOCAL"] != '' or partido["Puntos VISITA"] != ''):
                                    partidos_jugados.append(partido)

                            if len(partidos_jugados) == 0:       
                                niveles_dict[nivel][zona]["2DA FASE"][categoria_nombre]["partidos"] = partidos
                            else:
                                niveles_dict[nivel][zona]["2DA FASE"][categoria_nombre]["subzonas"].append({
                                    "subzona": "UNICO",
                                    "partidos": partidos,
                                    "tabla_posiciones": calcular_puntos_y_posiciones(partidos_jugados),
                                })

                    except IndexError:
                            print(IndexError, grupo["grupo"])
                elif fase_nombre == "INTERCONFERENCIAS":
                    nivel = "INTERCONFERENCIAS"
                    try:
                        zona = "UNICA"
                        subzona = grupo["grupo"]

                        for categoria in grupo['categorias']:
                            categoria_nombre = categoria['categoria']
                            niveles_dict[nivel][zona]["REGULAR"][categoria_nombre]["url"] = categoria['url']

                            partidos = categoria["partidos"]

                            # Corregir el formato de la fecha y filtrar los partidos que no se han jugado
                            partidos_jugados = []
                            partido_error_fecha = []

                            for partido in partidos:
                                try:
                                    fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y%H:%M")
                                except ValueError:
                                    try:
                                        fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y")
                                    except ValueError:
                                        partido_error_fecha.append(partido)
                                if fecha_partido <= fecha_actual and (partido["Puntos LOCAL"] != '' or partido["Puntos VISITA"] != ''):
                                    partidos_jugados.append(partido)

                            if len(partidos_jugados) == 0:       
                                niveles_dict[nivel][zona]["REGULAR"][categoria_nombre]["partidos"] = partidos
                            else:
                                niveles_dict[nivel][zona]["REGULAR"][categoria_nombre]["subzonas"].append({
                                    "subzona": subzona,
                                    "partidos": partidos,
                                    "tabla_posiciones": calcular_puntos_y_posiciones(partidos_jugados),
                                })

                    except IndexError:
                            print(IndexError, grupo["grupo"])
                else:
                    continue
            if fase["torneo"] == "TORNEO FORMATIVAS 2022":
                if fase_nombre in ["FASE DE CLASIFICACION 1", "FASE DE CLASIFICACION 2", "FASE DE CLASIFICACION 3"]:
                    nivel_fase = fase_nombre.split(' ')[:3]
                    zona, subzona = grupo["grupo"].split(' ')
                    nivel = f"NIVEL {nivel_fase[3]}"
                    try:
                        for categoria in grupo['categorias']:
                            categoria_nombre = categoria['categoria']
                            niveles_dict[nivel][zona]["CLASIFICACION"][categoria_nombre]["url"] = categoria['url']

                            partidos = categoria["partidos"]

                            # Corregir el formato de la fecha y filtrar los partidos que no se han jugado
                            partidos_jugados = []
                            partido_error_fecha = []

                            for partido in partidos:
                                try:
                                    fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y%H:%M")
                                except ValueError:
                                    try:
                                        fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y")
                                    except ValueError:
                                        partido_error_fecha.append(partido)
                                if fecha_partido <= fecha_actual and (partido["Puntos LOCAL"] != '' or partido["Puntos VISITA"] != ''):
                                    partidos_jugados.append(partido)

                            if len(partidos_jugados) == 0:       
                                niveles_dict[nivel][zona]["CLASIFICACION"][categoria_nombre]["partidos"] = partidos
                            else:
                                niveles_dict[nivel][zona]["CLASIFICACION"][categoria_nombre]["subzonas"].append({
                                    "subzona": subzona,
                                    "partidos": partidos,
                                    "tabla_posiciones": calcular_puntos_y_posiciones(partidos_jugados),
                                })

                    except IndexError:
                            print(IndexError, grupo["grupo"])
                elif fase_nombre in ["NIVEL 1", "NIVEL 2", "NIVEL 3"]:
                    nivel_zona = grupo['grupo'].split(' ', 2)[:2]  # Obtener ZONA y SUBZONA
                    nivel = fase_nombre
                    try:
                        zona = nivel_zona[0]
                        subzona = nivel_zona[2]

                        for categoria in grupo['categorias']:
                            categoria_nombre = categoria['categoria']
                            niveles_dict[nivel][zona]["2DA FASE"][categoria_nombre]["url"] = categoria['url']

                            partidos = categoria["partidos"]

                            # Corregir el formato de la fecha y filtrar los partidos que no se han jugado
                            partidos_jugados = []
                            partido_error_fecha = []

                            for partido in partidos:
                                try:
                                    fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y%H:%M")
                                except ValueError:
                                    try:
                                        fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y")
                                    except ValueError:
                                        partido_error_fecha.append(partido)
                                if fecha_partido <= fecha_actual and (partido["Puntos LOCAL"] != '' or partido["Puntos VISITA"] != ''):
                                    partidos_jugados.append(partido)

                            if len(partidos_jugados) == 0:       
                                niveles_dict[nivel][zona]["2DA FASE"][categoria_nombre]["partidos"] = partidos
                            else:
                                niveles_dict[nivel][zona]["2DA FASE"][categoria_nombre]["subzonas"].append({
                                    "subzona": subzona,
                                    "partidos": partidos,
                                    "tabla_posiciones": calcular_puntos_y_posiciones(partidos_jugados),
                                })

                    except IndexError:
                            print(IndexError, grupo["grupo"])
                elif fase_nombre == "INTERCONFERENCIAS":
                    nivel = "INTERCONFERENCIAS"
                    try:
                        zona = "UNICA"
                        subzona = grupo["grupo"]

                        for categoria in grupo['categorias']:
                            categoria_nombre = categoria['categoria']
                            niveles_dict[nivel][zona]["REGULAR"][categoria_nombre]["url"] = categoria['url']

                            partidos = categoria["partidos"]

                            # Corregir el formato de la fecha y filtrar los partidos que no se han jugado
                            partidos_jugados = []
                            partido_error_fecha = []

                            for partido in partidos:
                                try:
                                    fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y%H:%M")
                                except ValueError:
                                    try:
                                        fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y")
                                    except ValueError:
                                        partido_error_fecha.append(partido)
                                if fecha_partido <= fecha_actual and (partido["Puntos LOCAL"] != '' or partido["Puntos VISITA"] != ''):
                                    partidos_jugados.append(partido)

                            if len(partidos_jugados) == 0:       
                                niveles_dict[nivel][zona]["REGULAR"][categoria_nombre]["partidos"] = partidos
                            else:
                                niveles_dict[nivel][zona]["REGULAR"][categoria_nombre]["subzonas"].append({
                                    "subzona": subzona,
                                    "partidos": partidos,
                                    "tabla_posiciones": calcular_puntos_y_posiciones(partidos_jugados),
                                })

                    except IndexError:
                            print(IndexError, grupo["grupo"])
                else:
                    continue
            if fase["torneo"] == "FORMATIVAS 2023":
                if fase_nombre == "FASE REGULAR":
                    # La expresión regular para capturar las partes
                    pattern = r'(\w+)\s(\d+)"(\w)"'
                    # Iterar sobre la lista de cadenas y aplicar la expresión regular
                    for s in grupo["grupo"]:
                        match = re.match(pattern, s)
                        if match:
                            zona = match.group(1)
                            nivel = f"NIVEL {match.group(2)}"
                            subzona = match.group(3)
                        else:
                            print(f'No match found for string: {s}')
                    try:
                        for categoria in grupo['categorias']:
                            categoria_nombre = categoria['categoria']
                            niveles_dict[nivel][zona]["CLASIFICACION"][categoria_nombre]["url"] = categoria['url']

                            partidos = categoria["partidos"]

                            # Corregir el formato de la fecha y filtrar los partidos que no se han jugado
                            partidos_jugados = []
                            partido_error_fecha = []

                            for partido in partidos:
                                try:
                                    fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y%H:%M")
                                except ValueError:
                                    try:
                                        fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y")
                                    except ValueError:
                                        partido_error_fecha.append(partido)
                                if fecha_partido <= fecha_actual and (partido["Puntos LOCAL"] != '' or partido["Puntos VISITA"] != ''):
                                    partidos_jugados.append(partido)

                            if len(partidos_jugados) == 0:       
                                niveles_dict[nivel][zona]["CLASIFICACION"][categoria_nombre]["partidos"] = partidos
                            else:
                                niveles_dict[nivel][zona]["CLASIFICACION"][categoria_nombre]["subzonas"].append({
                                    "subzona": subzona,
                                    "partidos": partidos,
                                    "tabla_posiciones": calcular_puntos_y_posiciones(partidos_jugados),
                                })

                    except IndexError:
                            print(IndexError, grupo["grupo"])
                elif fase_nombre in ["CONFERENCIA 1", "CONFERENCIA 2"]:
                    # La expresión regular para capturar las partes
                    pattern = r'(\w+)\s(\d+)\s?"?(\w)?"?'

                    # Iterar sobre la lista de cadenas y aplicar la expresión regular
                    for s in grupo["grupo"]:
                        match = re.match(pattern, s)
                        if match:
                            zona = match.group(1)
                            nivel = f"NIVEL {match.group(2)}"
                            subzona = match.group(3)
                        else:
                            print(f'No match found for string: {s}')
                    try:
                        for categoria in grupo['categorias']:
                            categoria_nombre = categoria['categoria']
                            niveles_dict[nivel][zona]["2DA FASE"][categoria_nombre]["url"] = categoria['url']

                            partidos = categoria["partidos"]

                            # Corregir el formato de la fecha y filtrar los partidos que no se han jugado
                            partidos_jugados = []
                            partido_error_fecha = []

                            for partido in partidos:
                                try:
                                    fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y%H:%M")
                                except ValueError:
                                    try:
                                        fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y")
                                    except ValueError:
                                        partido_error_fecha.append(partido)
                                if fecha_partido <= fecha_actual and (partido["Puntos LOCAL"] != '' or partido["Puntos VISITA"] != ''):
                                    partidos_jugados.append(partido)

                            if len(partidos_jugados) == 0:       
                                niveles_dict[nivel][zona]["2DA FASE"][categoria_nombre]["partidos"] = partidos
                            else:
                                niveles_dict[nivel][zona]["2DA FASE"][categoria_nombre]["subzonas"].append({
                                    "subzona": subzona,
                                    "partidos": partidos,
                                    "tabla_posiciones": calcular_puntos_y_posiciones(partidos_jugados),
                                })

                    except IndexError:
                            print(IndexError, grupo["grupo"])
                elif fase_nombre == "INTERCONFERENCIAS":
                    nivel = "INTERCONFERENCIAS"
                    try:
                        zona = "UNICA"
                        subzona = grupo["grupo"]

                        for categoria in grupo['categorias']:
                            categoria_nombre = categoria['categoria']
                            niveles_dict[nivel][zona]["REGULAR"][categoria_nombre]["url"] = categoria['url']

                            partidos = categoria["partidos"]

                            # Corregir el formato de la fecha y filtrar los partidos que no se han jugado
                            partidos_jugados = []
                            partido_error_fecha = []

                            for partido in partidos:
                                try:
                                    fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y%H:%M")
                                except ValueError:
                                    try:
                                        fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y")
                                    except ValueError:
                                        partido_error_fecha.append(partido)
                                if fecha_partido <= fecha_actual and (partido["Puntos LOCAL"] != '' or partido["Puntos VISITA"] != ''):
                                    partidos_jugados.append(partido)

                            if len(partidos_jugados) == 0:       
                                niveles_dict[nivel][zona]["REGULAR"][categoria_nombre]["partidos"] = partidos
                            else:
                                niveles_dict[nivel][zona]["REGULAR"][categoria_nombre]["subzonas"].append({
                                    "subzona": subzona,
                                    "partidos": partidos,
                                    "tabla_posiciones": calcular_puntos_y_posiciones(partidos_jugados),
                                })

                    except IndexError:
                            print(IndexError, grupo["grupo"])
                else:
                    continue
            if fase["torneo"] == "FORMATIVAS 2024":
                nivel_zona = grupo['grupo'].split(' ', 3)[:3]  # Obtener NIVEL, ZONA y SUBZONA
                if 'ÚNICO' not in nivel_zona:
                    nivel = nivel_zona[0] + ' ' + nivel_zona[1]
                    try:
                        zona = nivel_zona[2]
                        subzona = grupo['grupo']

                        for categoria in grupo['categorias']:
                            categoria_nombre = categoria['categoria']
                            niveles_dict[nivel][zona][fase_nombre][categoria_nombre]["url"] = categoria['url']

                            partidos = categoria["partidos"]

                            # Corregir el formato de la fecha y filtrar los partidos que no se han jugado
                            partidos_jugados = []
                            partido_error_fecha = []

                            for partido in partidos:
                                try:
                                    fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y%H:%M")
                                except ValueError:
                                    try:
                                        fecha_partido = datetime.strptime(partido["Fecha"], "%d/%m/%Y")
                                    except ValueError:
                                        partido_error_fecha.append(partido)
                                if fecha_partido <= fecha_actual and (partido["Puntos LOCAL"] != '' or partido["Puntos VISITA"] != ''):
                                    partidos_jugados.append(partido)

                            if len(partidos_jugados) == 0:       
                                if fase_nombre == "1ER ETAPA":
                                    niveles_dict[nivel][zona][fase_nombre][categoria_nombre]["subzonas"].append({
                                        "subzona": subzona,
                                        "partidos": partidos
                                    })
                                else:
                                    niveles_dict[nivel][zona]["1ER ETAPA"][categoria_nombre]["partidos"] = partidos
                            else:
                                if fase_nombre == "1ER ETAPA":
                                    niveles_dict[nivel][zona][fase_nombre][categoria_nombre]["subzonas"].append({
                                        "subzona": subzona,
                                        "partidos": partidos,
                                        "tabla_posiciones": calcular_puntos_y_posiciones(partidos_jugados),
                                    })
                                else:
                                    niveles_dict[nivel][zona]["1ER ETAPA"][categoria_nombre]["partidos"] = partidos

                    except IndexError:
                            print(IndexError, grupo["grupo"])

    for nivel, zonas in niveles_dict.items():
        zona_list = []
        for zona, fases in zonas.items():
            fase_list = []
            for fase, categorias in fases.items():
                cat_list = []
                for categoria, datos in categorias.items():
                    try:
                        cat_list.append({
                            "categoria": categoria,
                            "cat_url": datos["url"],
                            "subzonas": datos["subzonas"],
                            "partidos": datos["partidos"]
                        })
                    except KeyError:
                        pass
                if fase == "1ER ETAPA":
                    fase_list.append({
                        "fase": fase,
                        "categorias": cat_list
                    })
            zona_list.append({
                "zona": zona,
                "fases": fase_list
            })
        nueva_estructura.append({
            "nivel": nivel,
            "zonas": zona_list
        })

    return nueva_estructura

def crear_nueva_estructura(data) -> dict:
    competencia = {
        "fases": []
    }

    for categoria in data["categorias"]:
        torneo = data["torneo"]
        for fase in categoria["fases"]:
            # Verificamos si la fase ya existe en la lista de fases de la competencia
            fase_existente = next((f for f in competencia["fases"] if f["fase"] == fase["fase"]), None)
            if fase_existente is None:
                # Si la fase no existe, la agregamos a la lista de fases de la competencia
                fase_dict = {
                    "torneo": torneo,
                    "fase": fase["fase"],
                    "grupos": []
                }
                competencia["fases"].append(fase_dict)
                fase_existente = fase_dict

            for grupo in fase["grupos"]:
                # Verificamos si el grupo ya existe en la fase actual
                grupo_existente = next((g for g in fase_existente["grupos"] if g["grupo"] == grupo["grupo"]), None)
                if grupo_existente is None:
                    # Si el grupo no existe, lo agregamos a la lista de grupos de la fase
                    grupo_dict = {
                        "grupo": grupo["grupo"],
                        "categorias": []
                    }
                    fase_existente["grupos"].append(grupo_dict)
                    grupo_existente = grupo_dict
                try:
                    # Agregamos la información de la categoría y sus partidos al grupo
                    grupo_existente["categorias"].append({
                        "categoria": categoria["cat"],
                        "url": grupo["grupo_url"],
                        "partidos": grupo["partidos"]
                    })
                except KeyError:
                    print(grupo["grupo"])
                    pass
    
    return combinar_datos_por_nivel_zona(competencia)


def main():
    data = cargar_json('categorias.json')
    for torneo in data:
        print(f"Torneo: {torneo['torneo']}, URL: {torneo['url']}")
        estructura = crear_nueva_estructura(torneo)
        print("Los datos han sido reestructurados con éxito")

        ## Guardar los datos actualizados en un nuevo archivo JSON
        with open(f"{torneo['torneo']}.json", "w") as file:
            json.dump(estructura, file, indent=4)
        
if __name__ == "__main__":
    main()
