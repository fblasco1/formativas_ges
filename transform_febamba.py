import json
from datetime import datetime
import pandas as pd
from collections import defaultdict

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
            nivel_zona = grupo['grupo'].split(' ', 3)[:3]  # Obtener NIVEL, ZONA y SUBZONA
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
                        #if categoria == "U17 Masculino":
                        #    for dato in datos["subzonas"]:
                        #        if dato["subzona"] == 'NIVEL 1 OESTE LFF "B"':
                        #            print(categoria + " " + dato["subzona"])
                        #            print(dato["partidos"])
                        #            print(dato["tabla_posiciones"])
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
        for fase in categoria["fases"]:
            # Verificamos si la fase ya existe en la lista de fases de la competencia
            fase_existente = next((f for f in competencia["fases"] if f["fase"] == fase["fase"]), None)
            if fase_existente is None:
                # Si la fase no existe, la agregamos a la lista de fases de la competencia
                fase_dict = {
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
           
def calcular_tabla_general(grupo):
    for nivel in grupo:
        for zona in nivel['zonas']:
            for fase in zona['fases']:
                equipos_dict_zona = defaultdict(lambda: {'PJ': 0, 'PG': 0, 'PP': 0, 'NP': 0, 'PTS': 0, 'PC': 0, 'PR': 0})

                for categoria in fase['categorias']:
                    # Crear un DataFrame vacío para la tabla general de la categoría
                    tabla_general_categoria = pd.DataFrame(columns=["Equipo", "PJ", "PG", "PP", "NP", "PTS", "PC", "PR", "DIF", "%VICT"])

                    # Procesar cada subzona de la categoría
                    for subzona in categoria["subzonas"]:
                        df_categoria = pd.DataFrame(subzona["tabla_posiciones"])

                        # Ajustar puntos para U9 MIXTO y U11 MIXTO
                        if categoria["categoria"] in ["U9 MIXTO", "Mini Mixto"]:
                            df_categoria["PTS"] = 0 - df_categoria["NP"]
                        
                        # Agregar los datos a la tabla general de la categoría
                        tabla_general_categoria = pd.concat([tabla_general_categoria, df_categoria])

                    # Agrupar por equipo y recalcular las estadísticas
                    tabla_general_categoria = tabla_general_categoria.groupby("Equipo").sum()
                    tabla_general_categoria["DIF"] = tabla_general_categoria["PC"] - tabla_general_categoria["PR"]
                    tabla_general_categoria["%VICT"] = (tabla_general_categoria["PG"] / tabla_general_categoria["PJ"]) * 100
                    tabla_general_categoria = tabla_general_categoria.reset_index()

                    # Procesar los partidos interzonales
                    for partido in categoria.get('partidos', []):
                        local = partido["Local"]
                        visitante = partido["Visitante"]
                        try:
                            puntos_local = int(partido["Puntos LOCAL"])
                            puntos_visitante = int(partido["Puntos VISITA"])

                            # Verificar si ambos equipos no se presentaron
                            if puntos_local == 1 and puntos_visitante == 1:
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == local, "NP"] += 1
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == local, "PJ"] += 1
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == visitante, "NP"] += 1
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == visitante, "PJ"] += 1 
                                
                                if categoria['categoria'] in ["U9 MIXTO", "Mini Mixto"]:
                                    tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == local, "PTS"] -= 1
                                    tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == visitante, "PTS"] -= 1
                                    
                            # Verificar si un equipo ganó y el otro no se presentó
                            elif puntos_local == 20 and puntos_visitante == 0:
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == local, "PJ"] += 1
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == local, "PG"] += 1
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == local, "PTS"] += 2
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == local, "PC"] += puntos_local
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == local, "DIF"] += puntos_local - puntos_visitante
                                
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == visitante, "NP"] += 1
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == visitante, "PJ"] += 1
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == visitante, "DIF"] += puntos_visitante - puntos_local
                                
                                if categoria['categoria'] in ["U9 MIXTO", "Mini Mixto"]:
                                    tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == visitante, "PTS"] -= 1
                                    
                            elif puntos_visitante == 20 and puntos_local == 0:
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == visitante, "PJ"] += 1
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == visitante, "PG"] += 1
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == visitante, "PTS"] += 2
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == visitante, "PC"] += puntos_visitante
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == visitante, "DIF"] += puntos_visitante - puntos_local
                                
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == local, "NP"] += 1
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == local, "PJ"] += 1
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == local, "DIF"] += puntos_local - puntos_visitante
                                
                                if categoria['categoria'] in ["U9 MIXTO", "Mini Mixto"]:
                                    tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == local, "PTS"] -= 1
                                    
                            else:
                                if puntos_local > puntos_visitante:
                                    ganador = local
                                    perdedor = visitante
                                else:
                                    ganador = visitante
                                    perdedor = local

                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == ganador, "PJ"] += 1
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == ganador, "PG"] += 1
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == ganador, "PTS"] += 2
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == ganador, "PC"] += max(puntos_local, puntos_visitante)
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == ganador, "PR"] += min(puntos_local, puntos_visitante)
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == ganador, "DIF"] += abs(puntos_local - puntos_visitante)

                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == perdedor, "PJ"] += 1
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == perdedor, "PP"] += 1
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == perdedor, "PC"] += min(puntos_local, puntos_visitante)
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == perdedor, "PR"] += max(puntos_local, puntos_visitante)
                                tabla_general_categoria.loc[tabla_general_categoria["Equipo"] == perdedor, "DIF"] += min(puntos_local, puntos_visitante) - max(puntos_local, puntos_visitante)
                        except ValueError:
                            continue

                    # Ordenar y almacenar la tabla general de la categoría
                    tabla_general_categoria = tabla_general_categoria.sort_values(by=["PTS", "DIF", "%VICT"], ascending=False).reset_index(drop=True)
                    categoria["tabla_general"] = tabla_general_categoria.to_dict(orient="records")

                    # Agregar estadísticas a la tabla general de la zona
                    for _, equipo in tabla_general_categoria.iterrows():
                        nombre_equipo = equipo['Equipo']
                        equipos_dict_zona[nombre_equipo]['PJ'] += equipo['PJ']
                        equipos_dict_zona[nombre_equipo]['PG'] += equipo['PG']
                        equipos_dict_zona[nombre_equipo]['PP'] += equipo['PP']
                        equipos_dict_zona[nombre_equipo]['NP'] += equipo['NP']
                        equipos_dict_zona[nombre_equipo]['PTS'] += equipo['PTS']
                        equipos_dict_zona[nombre_equipo]['PC'] += equipo['PC']
                        equipos_dict_zona[nombre_equipo]['PR'] += equipo['PR']

                # Crear la tabla general de la zona
                tabla_general_zona = []
                for equipo, datos in equipos_dict_zona.items():
                    datos['DIF'] = datos['PC'] - datos['PR']
                    datos['%VICT'] = round((datos['PG'] / datos['PJ']) * 100) if datos['PJ'] > 0 else 0
                    tabla_general_zona.append({
                        "Equipo": equipo,
                        "PJ": datos['PJ'],
                        "PG": datos['PG'],
                        "PP": datos['PP'],
                        "NP": datos['NP'],
                        "PTS": datos['PTS'],
                        "PC": datos['PC'],
                        "PR": datos['PR'],
                        "DIF": datos['DIF'],
                        "%VICT": datos['%VICT']
                    })

                # Ordenar y almacenar la tabla general de la zona
                tabla_general_zona_df = pd.DataFrame(tabla_general_zona).sort_values(by=["PTS", "DIF", "%VICT"], ascending=False).reset_index(drop=True)
                fase['tabla_general'] = tabla_general_zona_df.to_dict(orient="records")

# Función para calcular la tabla general
#def calcular_tabla_general(categoria):
#    # Crear un DataFrame vacío para la tabla general
#    tabla_general = pd.DataFrame(columns=["Equipo", "PJ", "PG", "PP", "NP", "PTS", "PC", "PR", "DIF", "%VICT"])
#
#    # Iterar sobre cada categoría en el grupo
#    for subzona in categoria["subzonas"]:
#        df_categoria = pd.DataFrame(subzona["tabla_posiciones"])
#
#        # Ajustar puntos para U9 MIXTO y U11 MIXTO
#        if categoria["categoria"] in ["U9 MIXTO", "Mini Mixto"]:
#            df_categoria["PTS"] = 0-df_categoria["NP"]
#        
#        # Agregar los datos a la tabla general
#        tabla_general = pd.concat([tabla_general, df_categoria])
#
#    # Agrupar por equipo y recalcular las estadísticas
#    tabla_general = tabla_general.groupby("Equipo").sum()
#    tabla_general["DIF"] = tabla_general["PC"] - tabla_general["PR"]
#    tabla_general["%VICT"] = (tabla_general["PG"] / tabla_general["PJ"]) * 100
#    tabla_general = tabla_general.reset_index()
#
#    for partido in categoria['partidos']:
#        local = partido["Local"]
#        visitante = partido["Visitante"]
#        try:
#            puntos_local = int(partido["Puntos LOCAL"])
#            puntos_visitante = int(partido["Puntos VISITA"])
#
#            # Verificar si ambos equipos no se presentaron
#            if puntos_local == 1 and puntos_visitante == 1:
#                if categoria['categoria'] in ["U9 MIXTO", "Mini Mixto"]:
#                    tabla_general.loc[local]['NP'] += 1
#                    tabla_general.loc[local]['PJ'] += 1
#                    tabla_general.loc[local]['PTS'] -= 1
#                    tabla_general.loc[visitante]['NP'] += 1
#                    tabla_general.loc[visitante]['PJ'] += 1
#                    tabla_general.loc[visitante]['PTS'] -= 1
#                else:
#                    tabla_general.loc[local]['NP'] += 1
#                    tabla_general.loc[local]['PJ'] += 1
#                    tabla_general.loc[visitante]['NP'] += 1
#                    tabla_general.loc[visitante]['PJ'] += 1 
#            
#            # Verificar si un equipo ganó y el otro no se presentó
#            elif puntos_local == 20 and puntos_visitante == 0:
#                if categoria['categoria'] in ["U9 MIXTO", "Mini Mixto"]:
#                    tabla_general.loc[local]['PJ'] += 1
#                    tabla_general.loc[local]['PG'] += 1
#                    tabla_general.loc[local]['PTS'] += 2
#                    tabla_general.loc[local]['PC'] += puntos_local
#                    tabla_general.loc[local]['DIF'] += puntos_local - puntos_visitante
#                    tabla_general.loc[visitante]['NP'] += 1
#                    tabla_general.loc[visitante]['PJ'] += 1
#                    tabla_general.loc[visitante]['PTS'] -= 1
#                    tabla_general.loc[visitante]['DIF'] += puntos_visitante - puntos_local
#                else:
#                    tabla_general.loc[local]['PTS'] += 2
#                    tabla_general.loc[local]['PG'] += 1
#                    tabla_general.loc[local]['PJ'] += 1
#                    tabla_general.loc[local]['PC'] += puntos_local
#                    tabla_general.loc[local]['DIF'] += puntos_local - puntos_visitante
#                    tabla_general.loc[visitante]['NP'] += 1
#                    tabla_general.loc[visitante]['PJ'] += 1 
#                    tabla_general.loc[visitante]['DIF'] += puntos_visitante - puntos_local
#                
#            
#            elif puntos_visitante == 20 and puntos_local == 0:
#                if categoria['categoria'] in ["U9 MIXTO", "Mini Mixto"]:
#                    tabla_general.loc[visitante]['PJ'] += 1
#                    tabla_general.loc[visitante]['PG'] += 1
#                    tabla_general.loc[visitante]['PTS'] += 2
#                    tabla_general.loc[visitante]['PC'] += puntos_local
#                    tabla_general.loc[visitante]['DIF'] += puntos_local - puntos_visitante
#                    tabla_general.loc[local]['NP'] += 1
#                    tabla_general.loc[local]['PJ'] += 1
#                    tabla_general.loc[local]['PTS'] -= 1
#                    tabla_general.loc[local]['DIF'] += puntos_visitante - puntos_local
#                else:
#                    tabla_general.loc[visitante]['PTS'] += 2
#                    tabla_general.loc[visitante]['PG'] += 1
#                    tabla_general.loc[visitante]['PJ'] += 1
#                    tabla_general.loc[visitante]['PC'] += puntos_local
#                    tabla_general.loc[visitante]['DIF'] += puntos_visitante - puntos_local
#                    tabla_general.loc[local]['NP'] += 1
#                    tabla_general.loc[local]['PJ'] += 1 
#                    tabla_general.loc[local]['DIF'] += puntos_local - puntos_visitante
#                
#            else:
#                if puntos_local > puntos_visitante:
#                    ganador = local
#                    perdedor = visitante
#                    tabla_general.loc[ganador]["PJ"] += 1
#                    tabla_general.loc[ganador]["PG"] += 1
#                    tabla_general.loc[ganador]["PTS"] += 2
#                    tabla_general.loc[ganador]["PC"] += puntos_local
#                    tabla_general.loc[ganador]["PR"] += puntos_visitante
#                    tabla_general.loc[ganador]["DIF"] += puntos_local - puntos_visitante
#
#                    tabla_general.loc[perdedor]["PJ"] += 1
#                    tabla_general.loc[perdedor]["PP"] += 1
#                    tabla_general.loc[perdedor]["PTS"] += 1
#                    tabla_general.loc[perdedor]["PC"] += puntos_visitante
#                    tabla_general.loc[perdedor]["PR"] += puntos_local
#                    tabla_general.loc[perdedor]["DIF"] += puntos_visitante - puntos_local
#                elif puntos_visitante < puntos_local:
#                    ganador = visitante
#                    perdedor = local
#                    tabla_general.loc[ganador]["PJ"] += 1
#                    tabla_general.loc[ganador]["PG"] += 1
#                    tabla_general.loc[ganador]["PTS"] += 2
#                    tabla_general.loc[ganador]["PC"] += puntos_visitante
#                    tabla_general.loc[ganador]["PR"] += puntos_local
#                    tabla_general.loc[ganador]["DIF"] += puntos_visitante - puntos_local
#
#                    tabla_general.loc[perdedor]["PJ"] += 1
#                    tabla_general.loc[perdedor]["PP"] += 1
#                    tabla_general.loc[perdedor]["PTS"] += 1
#                    tabla_general.loc[perdedor]["PC"] += puntos_local
#                    tabla_general.loc[perdedor]["PR"] += puntos_visitante
#                    tabla_general.loc[perdedor]["DIF"] += puntos_local - puntos_visitante
#                else:
#                    continue
#        except ValueError:
#            continue
#        
#    tabla_general["%VICT"] = (tabla_general["PG"] / tabla_general["PJ"]) * 100
#    # Ordenar la tabla general por puntos, diferencia de goles y porcentaje de victorias
#    tabla_general = tabla_general.sort_values(by=["PTS", "DIF", "%VICT"], ascending=False).reset_index(drop=True)
#
#    return tabla_general

#### Reestructurar la informacion extraida.
# Cargar el JSON con los datos de los partidos
with open("competencia.json", "r") as file:
    datos_partidos = json.load(file)

data = crear_nueva_estructura(datos_partidos)
calcular_tabla_general(data)

print("Los datos han sido reestructurados con éxito")

#for nivel in data:
#    for zona in nivel['zonas']:
#        for fase in zona['fases']:
#            for categoria in fase['categorias']:
#                # Calcular la tabla general
#                try:
#                    tabla_general = calcular_tabla_general(categoria)
#                    categoria["tabla_general"] = tabla_general.to_dict(orient="records")
#                except KeyError:
#                    print(categoria)

## Guardar los datos actualizados en un nuevo archivo JSON
with open("formativas_febamba.json", "w") as file:
    json.dump(data, file, indent=4)