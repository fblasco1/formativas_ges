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
                        datos['DIF'] = datos['PR'] - datos['PC']
                        datos['%VICT'] = (datos['PG'] / datos['PJ']) * 100 if datos['PJ'] > 0 else 0
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
                    datos['DIF'] = datos['PR'] - datos['PC']
                    datos['%VICT'] = (datos['PG'] / datos['PJ']) * 100 if datos['PJ'] > 0 else 0
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

# Reorganizar los datos
nueva_estructura = combinar_datos_por_nivel_zona(data)

# Calcular tablas generales
calcular_tabla_general(nueva_estructura)

# Guardar la nueva estructura en un archivo JSON
with open('nueva_estructura_formativas_febamba.json', 'w', encoding='utf-8') as f:
    json.dump(nueva_estructura, f, ensure_ascii=False, indent=4)
