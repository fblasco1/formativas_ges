import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pandas as pd
from utils.open_csv import leer_csv_con_encoding_detectado

#Lee y devuelve una lista de equipos.
def crear_ranking_base(data):
    # Normaliza los nombres de los equipos
    data["local"] = data["local"].str.strip().str.upper()
    data["visitante"] = data["visitante"].str.strip().str.upper()
    # Eliminar filas con valores nulos en las columnas 'local' y 'visitante' o NaN
    data = data.dropna(subset=["local", "visitante"])
    # Eliminar filas donde los equipos dice Libre
    data = data[~data["local"].str.contains("LIBRE", case=False, na=False)]

    return data, pd.DataFrame({"Equipo": data["local"].unique(), "Puntos": 0})

def asignar_basis_points(row):
    try:
        ptsL = int(row["ptsL"])
        ptsV = int(row["ptsV"])
    
        # Casos especiales
        if ptsL == 20 and ptsV == 0:
#            print(f"[LOG] Partido: {row['local']} {ptsL}-{ptsV} {row['visitante']} | BP: 700-0")
            return (700, 0)
        if ptsL == 0 and ptsV == 20:
#            print(f"[LOG] Partido: {row['local']} {ptsL}-{ptsV} {row['visitante']} | BP: 0-700")
            return (0, 700)
        if ptsL == 0 and ptsV == 0:
#            print(f"[LOG] Partido: {row['local']} {ptsL}-{ptsV} {row['visitante']} | BP: 0-0")
            return (0, 0)

        diff = abs(ptsL - ptsV)
        if ptsL > ptsV:
            if diff >= 20:
#                print(f"[LOG] Partido: {row['local']} {ptsL}-{ptsV} {row['visitante']} | BP: 750-250")
                return (750, 250)
            elif diff >= 10:
#                print(f"[LOG] Partido: {row['local']} {ptsL}-{ptsV} {row['visitante']} | BP: 700-300")
                return (700, 300)
            else:
#               print(f"[LOG] Partido: {row['local']} {ptsL}-{ptsV} {row['visitante']} | BP: 650-350")
                return (650, 350)
        elif ptsV > ptsL:
            if diff >= 20:
#                print(f"[LOG] Partido: {row['local']} {ptsL}-{ptsV} {row['visitante']} | BP: 250-750")
                return (250, 750)
            elif diff >= 10:
#                print(f"[LOG] Partido: {row['local']} {ptsL}-{ptsV} {row['visitante']} | BP: 300-700")
                return (300, 700)
            else:
#                print(f"[LOG] Partido: {row['local']} {ptsL}-{ptsV} {row['visitante']} | BP: 350-650")
                return (350, 650)
        else:
#            print(f"[LOG] Partido: {row['local']} {ptsL}-{ptsV} {row['visitante']} | BP: 0-0")
            return (0, 0)
    except ValueError:
        print(f"[LOG] Error al procesar el partido: {row}")
        return (0, 0)

def peso_por_anio(anio):
    pesos = {2019: 0.25, 2022: 0.5, 2023: 0.75, 2024: 1}
    return pesos.get(int(anio), 1)

def peso_por_fase(fase, nivel):
    fase = str(fase).upper()
    if "FINAL FOUR" in fase:
        return 1
    elif "PLAYOFF" in fase:
        if nivel in ["INTERCONFERENCIA", "INTERCONFERENCIA A", "INTERCONFERENCIA B"]:
            return 1
        else:
            return 0.75
    elif "FASE REGULAR" in fase:
        return 0.65
    return 1

def peso_por_ronda(ronda, anio):
    ronda = str(ronda).upper()
    if ronda in ["1RA FASE"]:
        return 1
    if ronda in ["2DA FASE"]:
        if anio in [2019,2022,2023]:
            return 2
        else:
            return 1
    if ronda in ["3RA FASE"]:
        if anio in [2019,2022,2023]:
            return 1
        else:
            return 2
    if ronda == "OCTAVOS DE FINAL":
        return 3
    if ronda == "CUARTOS DE FINAL":
        return 4
    if ronda == "SEMIFINAL":
        return 6
    if ronda == "FINAL":
        return 6
    return 1

def peso_por_nivel(nivel):
    nivel = str(nivel).upper()
    if nivel in ["INTERCONFERENCIA A", "INTERCONFERENCIA"]:
        return 2
    if "INTERCONFERENCIA B" in nivel:
        return 1.5
    if nivel == "1":
        return 1
    if nivel == "2":
        return 0.85
    if nivel == "3":
        return 0.75
    return 1

def get_team_positions(ranking_df):
    # Returns a dict: team_name -> position (1-based)
    return {row["Equipo"]: i+1 for i, row in ranking_df.iterrows()}

def calculate_orp_vectorized(df, prev_ranking):
    team_pos = get_team_positions(prev_ranking)
    n = len(prev_ranking)
    avg = (n + 1) / 2 if n > 0 else 0

    def orp_local(row):
        vis_pos = team_pos.get(row["visitante"], avg)
        return 1.5 * (avg - vis_pos)
    def orp_visit(row):
        loc_pos = team_pos.get(row["local"], avg)
        return 1.5 * (avg - loc_pos)

    df["ORP_LOCAL"] = df.apply(orp_local, axis=1)
    df["ORP_VISITA"] = df.apply(orp_visit, axis=1)
    return df

def process_year(data, prev_ranking, year):
    df = data[data["anio"] == year].copy()
    # BP assignment (vectorized)
    bp = df.apply(asignar_basis_points, axis=1, result_type="expand")
    df["BP_LOCAL"], df["BP_VISITA"] = bp[0], bp[1]
    # ORP assignment (vectorized)
    df = calculate_orp_vectorized(df, prev_ranking)
    # Weights
    df["peso_nivel"] = df["nivel"].apply(peso_por_nivel)
    df["peso_anio"] = df["anio"].apply(peso_por_anio)
    df["peso_ronda"] = df.apply(lambda row: peso_por_ronda(row["ronda"], row["anio"]), axis=1)
    df["peso_fase"] = df.apply(lambda row: peso_por_fase(row["fase"], row["nivel"]), axis=1)
    # Final points
    df["LocalSuma"] = df["peso_fase"]*df["peso_ronda"]*df["peso_anio"]*df["peso_nivel"]*(df["BP_LOCAL"]+df["ORP_LOCAL"])
    df["VisitaSuma"] = df["peso_fase"]*df["peso_ronda"]*df["peso_anio"]*df["peso_nivel"]*(df["BP_VISITA"]+df["ORP_VISITA"])
    # Aggregate
    local = df.groupby("local").agg({"LocalSuma": "sum"}).reset_index().rename(columns={"local": "Equipo", "LocalSuma": "Puntos"})
    visitante = df.groupby("visitante").agg({"VisitaSuma": "sum"}).reset_index().rename(columns={"visitante": "Equipo", "VisitaSuma": "Puntos"})
    ranking = pd.concat([local, visitante]).groupby("Equipo", as_index=False).agg({"Puntos": "sum"})
    ranking = ranking.sort_values(by="Puntos", ascending=False).reset_index(drop=True)
    return df, ranking

def process_all_years(data, years, ranking_init=None):
    rankings = {}
    ranking_total = ranking_init.copy() if ranking_init is not None else None
    for i, year in enumerate(years):
        print(f"Procesando año {year}...")
        if i == 0 or ranking_total is None:
            # Primer año: sin ORP
            df = data[data["anio"] == year].copy()
            bp = df.apply(asignar_basis_points, axis=1, result_type="expand")
            df["BP_LOCAL"], df["BP_VISITA"] = bp[0], bp[1]
            df["ORP_LOCAL"] = 0
            df["ORP_VISITA"] = 0
        else:
            df = data[data["anio"] == year].copy()
            bp = df.apply(asignar_basis_points, axis=1, result_type="expand")
            df["BP_LOCAL"], df["BP_VISITA"] = bp[0], bp[1]
            df = calculate_orp_vectorized(df, ranking_total)
        # Weights
        df["peso_nivel"] = df["nivel"].apply(peso_por_nivel)
        df["peso_anio"] = df["anio"].apply(peso_por_anio)
        df["peso_ronda"] = df.apply(lambda row: peso_por_ronda(row["ronda"], row["anio"]), axis=1)
        df["peso_fase"] = df.apply(lambda row: peso_por_fase(row["fase"], row["nivel"]), axis=1)
        # Final points
        df["LocalSuma"] = df["peso_fase"]*df["peso_ronda"]*df["peso_anio"]*df["peso_nivel"]*(df["BP_LOCAL"]+df["ORP_LOCAL"])
        df["VisitaSuma"] = df["peso_fase"]*df["peso_ronda"]*df["peso_anio"]*df["peso_nivel"]*(df["BP_VISITA"]+df["ORP_VISITA"])
        # Aggregate
        local = df.groupby("local").agg({"LocalSuma": "sum"}).reset_index().rename(columns={"local": "Equipo", "LocalSuma": "Puntos"})
        visitante = df.groupby("visitante").agg({"VisitaSuma": "sum"}).reset_index().rename(columns={"visitante": "Equipo", "VisitaSuma": "Puntos"})
        ranking = pd.concat([local, visitante]).groupby("Equipo", as_index=False).agg({"Puntos": "sum"})
        ranking = ranking.sort_values(by="Puntos", ascending=False).reset_index(drop=True)
        rankings[year] = (df, ranking)
        # Actualizar ranking_total sumando el ranking de este año
        if ranking_total is None:
            ranking_total = ranking.copy()
        else:
            ranking_total = pd.concat([ranking_total, ranking]).groupby("Equipo", as_index=False).agg({"Puntos": "sum"})
            ranking_total = ranking_total.sort_values(by="Puntos", ascending=False).reset_index(drop=True)
        # Guardar archivos
        df.to_csv(f"Data/procesada/{year}.csv", index=False)
        ranking.to_csv(f"Data/procesada/Ranking{year}.csv", index=False)
        ranking_total.to_csv(f"Data/procesada/Ranking2019-{year}.csv", index=False)
    return rankings, ranking_total

data = leer_csv_con_encoding_detectado("Data/procesada/19-24.csv", ";")
data, ranking_base = crear_ranking_base(data)
data = data[~data["categoria"].str.upper().isin(["MINI", "PREMINI"])]
years = [2019, 2022, 2023, 2024]
process_all_years(data, years, ranking_init=ranking_base)
