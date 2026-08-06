# -*- coding: utf-8 -*-
"""Lectura de CSV con detección de encoding (chardet opcional)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

_ENCODINGS = ("utf-8-sig", "utf-8", "latin-1", "cp1252")


def _detect_encoding(path: str | Path) -> str:
    try:
        import chardet
    except ImportError:
        return "utf-8-sig"
    raw = Path(path).read_bytes()
    result = chardet.detect(raw)
    enc = result.get("encoding") if result else None
    return enc or "utf-8-sig"


def leer_csv_con_encoding_detectado(path, sep):
    path = str(path)
    enc = _detect_encoding(path)
    try:
        return pd.read_csv(path, encoding=enc, sep=sep)
    except (UnicodeDecodeError, LookupError):
        pass
    for fallback in _ENCODINGS:
        try:
            return pd.read_csv(path, encoding=fallback, sep=sep)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, encoding="latin-1", sep=sep, encoding_errors="replace")
