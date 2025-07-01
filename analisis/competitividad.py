import os
import sys
import pandas as pd
import numpy as np

# Agrega el directorio padre al path de Python
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.open_csv import leer_csv_con_encoding_detectado


def cargar_partidos(files):
    dfs = []
    for f in files:
        try:
            df = leer_csv_con_encoding_detectado(f, sep=';')
            df['año'] = f.split('_')[-1].split('.')[0]
            dfs.append(df)
        except Exception as e:
            print(f"Error cargando {f}: {e}")
    return pd.concat(dfs, ignore_index=True)

def filtrar_categorias(df):
    categorias_validas = ["PREINFANTILES", "INFANTILES", "CADETES", "JUVENILES"]
    regiones_invalidas = ["Desconocida", "Desconocido"]
    df = df[df["categoria"].isin(categorias_validas)].copy()
    df = df[~df["zona"].isin(regiones_invalidas)]
    return df[df["categoria"].isin(categorias_validas)].copy()

def agregar_columnas_analiticas(df):
    df["region"] = df["zona"]
    df["diferencia"] = df["ptsL"] - df["ptsV"]
    df["ganador"] = df.apply(lambda x: x["local"] if x["ptsL"] > x["ptsV"] else x["visitante"], axis=1)
    return df

def win_pct_por_equipo_region(df):
    partidos = pd.concat([
        df[["año", "region", "local", "ptsL", "visitante", "ptsV", "ganador"]].rename(columns={"local": "equipo", "ptsL": "puntos", "visitante": "rival", "ptsV": "puntos_rival"}),
        df[["año", "region", "visitante", "ptsV", "local", "ptsL", "ganador"]].rename(columns={"visitante": "equipo", "ptsV": "puntos", "local": "rival", "ptsL": "puntos_rival"})
    ], ignore_index=True)
    partidos["win"] = partidos["equipo"] == partidos["ganador"]
    win_pct = partidos.groupby(["año", "region", "equipo"]).agg(
        win_pct=("win", "mean"),
        partidos=("win", "count")
    ).reset_index()
    return win_pct

def indice_herfindahl(series):
    participaciones = series.value_counts(normalize=True)
    return (participaciones ** 2).sum()

def exportar_analisis(df, win_pct, outdir="outputs"):
    import os
    os.makedirs(outdir, exist_ok=True)
    win_pct.to_csv(f"{outdir}/win_pct_por_equipo_region.csv", index=False)
    desv = win_pct.groupby(["año", "region"])["win_pct"].std().unstack()
    desv.to_csv(f"{outdir}/desviacion_win_pct.csv")
    ajustados = df[df["diferencia"].abs() < 20].groupby(["año", "region"]).size() / df.groupby(["año", "region"]).size()
    ajustados = ajustados.unstack()
    ajustados.to_csv(f"{outdir}/partidos_ajustados.csv")
    herf = win_pct.groupby(["año", "region"]).apply(lambda x: indice_herfindahl(x["equipo"]))
    herf = herf.unstack()
    herf.to_csv(f"{outdir}/herfindahl_ganadores.csv")

def resumen_agregado_regional(df, win_pct, outdir="outputs"):
    resumen = []
    # Paridad interna: desviación estándar promedio del win_pct
    paridad = win_pct.groupby("region")["win_pct"].std().to_dict()
    # Clas. Interconf: % de equipos de cada región que clasifican a INTERCONFERENCIA
    clasificados = df[df["nivel"].str.contains("INTERCONFERENCIA", na=False)]
    total_equipos = df[df["fase"] == "FASE REGULAR"].groupby(["region", "año"])['local'].nunique().groupby("region").mean()
    clas_por_region = clasificados.groupby(["region", "año"])['local'].nunique().groupby("region").mean()
    clas_pct = (clas_por_region / total_equipos).fillna(0).to_dict()
    # Campeones: contar ganadores en finales por región
    finales = df[df["ronda"].str.contains("FINAL", na=False)]
    campeones = finales.groupby("region")["ganador"].nunique().to_dict()
    # HHI Títulos: Herfindahl de títulos por región
    hhi_titulos = finales.groupby("region")["ganador"].apply(lambda x: indice_herfindahl(x)).to_dict()
    # Evolución: diferencia de win_pct promedio entre primer y último año
    años = sorted(win_pct["año"].unique())
    evol = {}
    for region, subdf in win_pct.groupby("region"):
        if len(años) > 1:
            ini = subdf[subdf["año"] == años[0]]["win_pct"].mean()
            fin = subdf[subdf["año"] == años[-1]]["win_pct"].mean()
            delta = fin - ini
            if delta > 0.01:
                tendencia = "Mejora"
            elif delta < -0.01:
                tendencia = "Empeora"
            else:
                tendencia = "Estable"
        else:
            tendencia = "-"
        evol[region] = tendencia
    # Armar resumen
    for region in sorted(set(win_pct["region"])):
        resumen.append({
            "Región": region,
            "Paridad Interna": f"{paridad.get(region, 0):.2f}",
            "Clas. Interconf": f"{100*clas_pct.get(region, 0):.1f}%",
            "Campeones": campeones.get(region, 0),
            "HHI Títulos": f"{hhi_titulos.get(region, 0):.2f}",
            "Evolución (Δ)": evol.get(region, '-')
        })
    resumen_df = pd.DataFrame(resumen)
    resumen_df.to_csv(f"{outdir}/resumen_agregado_regional.csv", index=False)
    return resumen_df

def main():
    PARTIDOS_FILES = [
        'Data/partidos_2019.csv',
        'Data/partidos_2022.csv',
        'Data/partidos_2023.csv',
        'Data/partidos_2024.csv',
    ]
    df = cargar_partidos(PARTIDOS_FILES)
    df = filtrar_categorias(df)
    df = agregar_columnas_analiticas(df)
    win_pct = win_pct_por_equipo_region(df)
    exportar_analisis(df, win_pct)
    resumen_agregado_regional(df, win_pct)

if __name__ == "__main__":
    main()
