import json
import pandas as pd
from collections import defaultdict

# Cargar datos del archivo JSON
with open('formativas_febamba.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

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
                    cat_url = categoria['url']
                    try:
                        niveles_dict[nivel][zona][fase_nombre][categoria_nombre]["url"] = cat_url
                        niveles_dict[nivel][zona][fase_nombre][categoria_nombre]["subzonas"].append({
                            "subzona": subzona,
                            "partidos": categoria['partidos'],
                            "tabla_posiciones": categoria['tabla_posiciones']
                        })
                    except KeyError:
                        print(grupo["grupo"])
            except IndexError:
                    print(grupo["grupo"])
    for nivel, zonas in niveles_dict.items():
        zona_list = []
        for zona, fases in zonas.items():
            fase_list = []
            for fase, categorias in fases.items():
                cat_list = []
                for categoria, datos in categorias.items():
                    cat_list.append({
                        "categoria": categoria,
                        "cat_url": datos["url"],
                        "subzonas": datos["subzonas"]
                    })
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

# Función para calcular la tabla general de cada zona y categoría
def calcular_tabla_general(nueva_estructura):
    for nivel in nueva_estructura:
        for zona in nivel['zonas']:
            for fase in zona['fases']:
                equipos_dict_zona = defaultdict(lambda: {'PJ': 0, 'PG': 0, 'PP': 0, 'NP': 0, 'PTS': 0, 'PC': 0, 'PR': 0})
                
                for categoria in fase['categorias']:
                    equipos_dict_categoria = defaultdict(lambda: {'PJ': 0, 'PG': 0, 'PP': 0, 'NP': 0, 'PTS': 0, 'PC': 0, 'PR': 0})

                    if categoria["categoria"] not in ["U9 MIXTO", "Mini Mixto"]:
                        
                        for subzona in categoria['subzonas']:
                            for equipo in subzona['tabla_posiciones']:
                                nombre_equipo = equipo['Equipo']
                                equipos_dict_zona[nombre_equipo]['PJ'] += equipo['PJ']
                                equipos_dict_zona[nombre_equipo]['PG'] += equipo['PG']
                                equipos_dict_zona[nombre_equipo]['PP'] += equipo['PP']
                                equipos_dict_zona[nombre_equipo]['NP'] += equipo['NP']
                                equipos_dict_zona[nombre_equipo]['PTS'] += equipo['PTS']
                                equipos_dict_zona[nombre_equipo]['PC'] += equipo['PC']
                                equipos_dict_zona[nombre_equipo]['PR'] += equipo['PR']

                                equipos_dict_categoria[nombre_equipo]['PJ'] += equipo['PJ']
                                equipos_dict_categoria[nombre_equipo]['PG'] += equipo['PG']
                                equipos_dict_categoria[nombre_equipo]['PP'] += equipo['PP']
                                equipos_dict_categoria[nombre_equipo]['NP'] += equipo['NP']
                                equipos_dict_categoria[nombre_equipo]['PTS'] += equipo['PTS']
                                equipos_dict_categoria[nombre_equipo]['PC'] += equipo['PC']
                                equipos_dict_categoria[nombre_equipo]['PR'] += equipo['PR']
      
                    else:
                        for subzona in categoria['subzonas']:
                            for equipo in subzona['tabla_posiciones']:
                                nombre_equipo = equipo['Equipo']
                                equipos_dict_zona[nombre_equipo]['PJ'] += equipo['PJ']
                                equipos_dict_zona[nombre_equipo]['PG'] += equipo['PG']
                                equipos_dict_zona[nombre_equipo]['PP'] += equipo['PP']
                                equipos_dict_zona[nombre_equipo]['NP'] += equipo['NP']
                                equipos_dict_zona[nombre_equipo]['PTS'] -= equipo['NP']
                                equipos_dict_zona[nombre_equipo]['PC'] += equipo['PC']
                                equipos_dict_zona[nombre_equipo]['PR'] += equipo['PR']

                                equipos_dict_categoria[nombre_equipo]['PJ'] += equipo['PJ']
                                equipos_dict_categoria[nombre_equipo]['PG'] += equipo['PG']
                                equipos_dict_categoria[nombre_equipo]['PP'] += equipo['PP']
                                equipos_dict_categoria[nombre_equipo]['NP'] += equipo['NP']
                                equipos_dict_categoria[nombre_equipo]['PTS'] -= equipo['NP']
                                equipos_dict_categoria[nombre_equipo]['PC'] += equipo['PC']
                                equipos_dict_categoria[nombre_equipo]['PR'] += equipo['PR']

                    tabla_general_categoria = []
                    for equipo, datos in equipos_dict_categoria.items():
                        datos['DIF'] = datos['PC'] - datos['PR']
                        datos['%VICT'] = round((datos['PG'] / datos['PJ']) * 100) if datos['PJ'] > 0 else 0
                        tabla_general_categoria.append({
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

                    
                    try:
                        # Ordenar la tabla general por puntos, diferencia de goles y porcentaje de victorias
                        tabla_general_categoria_df = pd.DataFrame(tabla_general_categoria).sort_values(by=["PTS", "DIF", "%VICT"], ascending=False).reset_index(drop=True)

                        categoria['tabla_general'] = tabla_general_categoria_df.to_dict(orient="records")
                    except KeyError:
                        print(categoria["categoria"])

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
                
                try:
                    # Ordenar la tabla general por puntos, diferencia de goles y porcentaje de victorias
                    tabla_general_zona_df = pd.DataFrame(tabla_general_zona).sort_values(by=["PTS", "DIF", "%VICT"], ascending=False).reset_index(drop=True)
                    fase['tabla_general'] = tabla_general_zona_df.to_dict(orient="records")
                except KeyError:
                        print(fase["fase"])

def calcular_posiciones(tabla_posiciones, partidos):
    # 1. Desempate Olímpico
    equipos_empatados = encontrar_equipos_empatados(tabla_posiciones)
    tabla_posiciones = desempate_olimpico(equipos_empatados, partidos, tabla_posiciones)

    try:
        # 2. Coeficiente / Gol Average
        tabla_posiciones.sort(key=lambda x: (x['PC'] / x['PR']), reverse=True)

        # 3. Promedio de victorias
        tabla_posiciones.sort(key=lambda x: (x['PG'] / x['PJ']), reverse=True)
    except ZeroDivisionError:
        pass

    return tabla_posiciones

def encontrar_equipos_empatados(tabla_posiciones):
    equipos_empatados = []
    for i in range(len(tabla_posiciones)):
        if i > 0 and tabla_posiciones[i]['PTS'] == tabla_posiciones[i - 1]['PTS']:
            equipos_empatados.append(tabla_posiciones[i])
        else:
            if len(equipos_empatados) > 1:
                return equipos_empatados
            equipos_empatados = []
    if len(equipos_empatados) > 1:
        return equipos_empatados
    return []

def desempate_olimpico(equipos, partidos, tabla_posiciones):
    if len(equipos) == 2:
        equipo1, equipo2 = equipos[0], equipos[1]
        puntos_e1, puntos_e2 = 0, 0
        dif_gol_e1, dif_gol_e2 = 0, 0
        total_gol_e1, total_gol_e2 = 0, 0

        for partido in partidos:
            if partido['Local'] == equipo1['Equipo'] and partido['Visitante'] == equipo2['Equipo']:
                puntos_e1 += int(partido['Puntos LOCAL'])
                puntos_e2 += int(partido['Puntos VISITA'])
                dif_gol_e1 += int(partido['Puntos LOCAL']) - int(partido['Puntos VISITA'])
                dif_gol_e2 += int(partido['Puntos VISITA']) - int(partido['Puntos LOCAL'])
                total_gol_e1 += int(partido['Puntos LOCAL'])
                total_gol_e2 += int(partido['Puntos VISITA'])
            elif partido['Local'] == equipo2['Equipo'] and partido['Visitante'] == equipo1['Equipo']:
                puntos_e2 += int(partido['Puntos LOCAL'])
                puntos_e1 += int(partido['Puntos VISITA'])
                dif_gol_e2 += int(partido['Puntos LOCAL']) - int(partido['Puntos VISITA'])
                dif_gol_e1 += int(partido['Puntos VISITA']) - int(partido['Puntos LOCAL'])
                total_gol_e2 += int(partido['Puntos LOCAL'])
                total_gol_e1 += int(partido['Puntos VISITA'])

        if puntos_e1 != puntos_e2:
            equipos.sort(key=lambda x: puntos_e1 if x['Equipo'] == equipo1['Equipo'] else puntos_e2, reverse=True)
        elif dif_gol_e1 != dif_gol_e2:
            equipos.sort(key=lambda x: dif_gol_e1 if x['Equipo'] == equipo1['Equipo'] else dif_gol_e2, reverse=True)
        elif total_gol_e1 != total_gol_e2:
            equipos.sort(key=lambda x: total_gol_e1 if x['Equipo'] == equipo1['Equipo'] else total_gol_e2, reverse=True)

    elif len(equipos) > 2:
        equipos.sort(key=lambda x: x['Equipo'])  # Ordenar equipos alfabéticamente
        for i, equipo in enumerate(equipos):
            equipo['posicion_temporal'] = i + 1

        partidos_equipos = [partido for partido in partidos if partido['Local'] in [equipo['Equipo'] for equipo in equipos] and partido['Visitante'] in [equipo['Equipo'] for equipo in equipos]]

        for partido in partidos_equipos:
            local = next((equipo for equipo in equipos if equipo['Equipo'] == partido['Local']), None)
            visitante = next((equipo for equipo in equipos if equipo['Equipo'] == partido['Visitante']), None)
            if local and visitante:
                if int(partido['Puntos LOCAL']) > int(partido['Puntos VISITA']):
                    local['PTS'] += 2
                elif int(partido['Puntos LOCAL']) < int(partido['Puntos VISITA']):
                    visitante['PTS'] += 2
                else:
                    local['PTS'] += 1
                    visitante['PTS'] += 1

        equipos.sort(key=lambda x: (x['PTS'], x['DIF'], x['PC'] / x['PJ'], x['posicion_temporal']), reverse=True)

        for equipo in equipos:
            del equipo['posicion_temporal']

    # Actualizar tabla de posiciones con el orden resuelto por desempate olímpico
    for i in range(len(tabla_posiciones)):
        for equipo in equipos:
            if tabla_posiciones[i]['Equipo'] == equipo['Equipo']:
                tabla_posiciones[i] = equipo
    return tabla_posiciones

# Reorganizar los datos
nueva_estructura = combinar_datos_por_nivel_zona(data)

for nivel in nueva_estructura:
    for zona in nivel["zonas"]:
        for fase in zona["fases"]:
            for categoria in fase["categorias"]:
                if categoria["categoria"] not in ["U9 MIXTO", "Mini Mixto"]:
                    for subzona in categoria["subzonas"]:
                        tabla_nueva = calcular_posiciones(subzona["tabla_posiciones"], subzona["partidos"])
                        subzona["tabla_posiciones"] = tabla_nueva


# Calcular tablas generales
calcular_tabla_general(nueva_estructura)

# Guardar la nueva estructura en un archivo JSON
with open('nueva_estructura_formativas_febamba.json', 'w', encoding='utf-8') as f:
    json.dump(nueva_estructura, f, ensure_ascii=False, indent=4)
