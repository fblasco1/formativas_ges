import json
from datetime import datetime
import pandas as pd

def reestructured_data(data) -> dict:
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
    
    return competencia
        
    

# Función para calcular los puntos y la tabla de posiciones
def calcular_puntos_y_posiciones(df):
    stats = {}
    # Iterar sobre cada fila del DataFrame
    for _, row in df.iterrows():
        local = row["Local"]
        visitante = row["Visitante"]
        try:
            puntos_local = int(row["Puntos LOCAL"])
            puntos_visitante = int(row["Puntos VISITA"])

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
                elif puntos_local < puntos_visitante:
                    ganador = visitante
                    perdedor = local
                else:
                    continue
                
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
        except ValueError:
            print(row)
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

    # Ordenar la tabla de posiciones por puntos, diferencia de goles y porcentaje de victorias
    df_stats = df_stats.sort_values(by=["PTS", "%VICT", "DIF"], ascending=False).reset_index(drop=True)

    return df_stats


# Función para calcular la tabla general
def calcular_tabla_general(grupo):
    # Crear un DataFrame vacío para la tabla general
    tabla_general = pd.DataFrame(columns=["Equipo", "PJ", "PG", "PP", "NP", "PTS", "PC", "PR", "DIF", "%VICT"])

    # Iterar sobre cada categoría en el grupo
    for categoria in grupo["categorias"]:
        df_categoria = pd.DataFrame(categoria["tabla_posiciones"])

        # Ajustar puntos para U9 MIXTO y U11 MIXTO
        if categoria["categoria"] in ["U9 MIXTO", "Mini Mixto"]:
            df_categoria["PTS"] = 0-df_categoria["NP"]
        
        # Agregar los datos a la tabla general
        tabla_general = pd.concat([tabla_general, df_categoria])

    # Agrupar por equipo y recalcular las estadísticas
    tabla_general = tabla_general.groupby("Equipo").sum()
    tabla_general["DIF"] = tabla_general["PC"] - tabla_general["PR"]
    tabla_general["%VICT"] = (tabla_general["PG"] / tabla_general["PJ"]) * 100
    tabla_general = tabla_general.reset_index()

    # Ordenar la tabla general por puntos, diferencia de goles y porcentaje de victorias
    tabla_general = tabla_general.sort_values(by=["PTS", "DIF", "%VICT"], ascending=False).reset_index(drop=True)

    return tabla_general


#### Reestructurar la informacion extraida.
# Cargar el JSON con los datos de los partidos
with open("competencia.json", "r") as file:
    datos_partidos = json.load(file)

data = reestructured_data(datos_partidos)

## Guardar los datos actualizados en un nuevo archivo JSON
with open("datos_estructurados.json", "w") as file:
    json.dump(data, file, indent=4)

print("Los datos han sido reestructurados con éxito")

fecha_actual = datetime.now()

# Calcular tabla de posiciones para cada categoría
for fase in data["fases"]:
    for grupo in fase["grupos"]:
        for categoria in grupo["categorias"]:
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
                if fecha_partido <= fecha_actual:
                    partidos_jugados.append(partido)

            df = pd.DataFrame(partidos_jugados)
            print(partido_error_fecha)

            if len(partidos_jugados) == 0:       
                print("No se jugaron partidos")
            else:
                df_posiciones = calcular_puntos_y_posiciones(df)
                categoria["tabla_posiciones"] = df_posiciones.to_dict(orient="records")

print("Tabla de posiciones correctamente realizada")

for fase in data["fases"]:
    for grupo in fase["grupos"]:
        # Calcular la tabla general
        try:
            tabla_general = calcular_tabla_general(grupo)
            grupo["tabla_general"] = tabla_general.to_dict(orient="records")
        except KeyError:
            print(grupo)

# Guardar la estructura actualizada en un archivo JSON
with open("formativas_febamba.json", "w") as file:
    json.dump(data, file, indent=4)
  
print("Tabla General correctamente realizada")