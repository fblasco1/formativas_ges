# -*- coding: utf-8 -*-
"""
Funciones auxiliares para manipulación de DataFrames en el ETL de FEBAMBA.
"""

import pandas as pd
from typing import List


def crear_dataframe_partidos(partidos: List[dict]) -> pd.DataFrame:
    """
    Crea un DataFrame estándar a partir de una lista de diccionarios de partidos.

    Args:
        partidos (List[dict]): Lista de partidos scrappeados.

    Returns:
        pd.DataFrame: DataFrame limpio y listo para análisis.
    """
    df = pd.DataFrame(partidos)

    # Normalización básica de columnas (si es necesario)
    if "fecha" in df.columns:
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")

    return df


def guardar_dataframe(df: pd.DataFrame, path: str, formato: str = "csv"):
    """
    Guarda un DataFrame en formato CSV o Parquet.

    Args:
        df (pd.DataFrame): DataFrame a guardar.
        path (str): Ruta de destino (sin extensión).
        formato (str): Formato deseado ('csv' o 'parquet').
    """
    if formato == "csv":
        df.to_csv(f"{path}.csv", index=False, encoding="utf-8")
    elif formato == "parquet":
        df.to_parquet(f"{path}.parquet", index=False)
    else:
        raise ValueError("Formato no soportado. Usar 'csv' o 'parquet'.")
