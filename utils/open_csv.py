# -*- coding: utf-8 -*-
"""Lectura de CSV con detección de encoding (chardet) y separador."""

from __future__ import annotations

import chardet
import pandas as pd


def _detect_encoding(path: str) -> str:
    with open(path, "rb") as file:
        raw = file.read()
    result = chardet.detect(raw)
    enc = result.get("encoding") or "utf-8"
    return enc


def leer_csv_con_encoding_detectado(path: str, sep: str = ",") -> pd.DataFrame:
    """Lee CSV usando encoding inferido por chardet."""
    encoding = _detect_encoding(path)
    return pd.read_csv(path, encoding=encoding, sep=sep)


def leer_csv_autodetect(path: str) -> pd.DataFrame:
    """Prueba separadores comunes (',', ';', tab) manteniendo el mismo encoding."""
    encoding = _detect_encoding(path)
    best: pd.DataFrame | None = None
    for sep in (",", ";", "\t"):
        try:
            df = pd.read_csv(path, encoding=encoding, sep=sep)
            if df.shape[1] > 1 or len(df) == 0:
                return df
            best = df
        except Exception:
            continue
    if best is not None:
        return best
    return pd.read_csv(path, encoding=encoding, sep=",")
