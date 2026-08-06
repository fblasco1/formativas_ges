# -*- coding: utf-8 -*-
"""
Categorías FeBAMBA y mapeo a buckets de renivelación.

Equivalencia institucional (columnas del ranking):
  U13  → INFANTILES   (reemplaza PREINFANTILES)
  U15  → CADETES      (reemplaza INFANTILES)
  U17  → JUVENILES    (reemplaza CADETES)
  U19/U21 → LIGA PROXIMO (reemplaza JUVENILES)

PREINFANTILES ya no existe en GES; cualquier fila con esa etiqueta se parsea al bucket
INFANTILES (U13). No renombrar la columna en CSV 2023-24: ahí ``INFANTILES`` = U15.

Etiquetas en CSV:
  - 2023-2024 (histórico): PREINFANTILES, INFANTILES, CADETES, JUVENILES
  - 2025+ (actual):       INFANTILES MASCULINO, CADETES MASCULINO, …
"""

from __future__ import annotations

import re
from typing import Optional

PENALIZACION_FORFAIT_TIRA = 1000

# Columnas del ranking = buckets U con nombre FeBAMBA actual
CATEGORIAS_COMPETITIVAS: tuple[str, ...] = (
    "INFANTILES",      # U13
    "CADETES",         # U15
    "JUVENILES",       # U17
    "LIGA PROXIMO",    # U19 / U21
)

# Etiqueta GES discontinuada → mismo bucket que INFANTILES MASCULINO (cualquier año)
_PREINFANTILES_A_BUCKET = "INFANTILES"

# CSV 2023-2024 (sin MASCULINO ni LIGA PROXIMO): desplazamiento +1
_LEGACY_CSV_A_BUCKET: dict[str, str] = {
    "PREINFANTILES": _PREINFANTILES_A_BUCKET,
    "PREINFANTILES MASCULINO": _PREINFANTILES_A_BUCKET,
    "INFANTILES": "CADETES",
    "INFANTILES MASCULINO": "CADETES",  # solo si apareciera en años viejos
    "CADETES": "JUVENILES",
    "CADETES MASCULINO": "JUVENILES",
    "JUVENILES": "LIGA PROXIMO",
    "JUVENILES MASCULINO": "LIGA PROXIMO",
}

# CSV 2025+ (formato MASCULINO / LIGA PROXIMO): nombre alineado al bucket
_NUEVO_CSV_A_BUCKET: dict[str, str] = {
    "INFANTILES": "INFANTILES",
    "INFANTILES MASCULINO": "INFANTILES",
    "CADETES": "CADETES",
    "CADETES MASCULINO": "CADETES",
    "JUVENILES": "JUVENILES",
    "JUVENILES MASCULINO": "JUVENILES",
    "LIGA PROXIMO": "LIGA PROXIMO",
    "LIGA PROXIMO MASCULINO": "LIGA PROXIMO",
}

_U_A_BUCKET: dict[str, str] = {
    "9": "INFANTILES",   # mini: no competitivo, pero por si aparece U9
    "10": "INFANTILES",
    "11": "INFANTILES",
    "13": "INFANTILES",
    "15": "CADETES",
    "17": "JUVENILES",
    "19": "LIGA PROXIMO",
    "21": "LIGA PROXIMO",
}

_NO_COMPETITIVAS = frozenset(
    {
        "MINI",
        "MINI MASCULINO",
        "MINI MIXTO",
        "PREMINI",
        "PRE MINI",
        "PREMINI MASCULINO",
        "PRE MINI MASCULINO",
        "MOSQUITOS",
    }
)


def _normalizar_texto(categoria: str) -> str:
    return categoria.upper().strip()


def bucket_renivelacion(categoria: str, anio: int | None = None) -> Optional[str]:
    """
    Devuelve el bucket de columna (INFANTILES / CADETES / JUVENILES / LIGA PROXIMO).

    Usa el año para desambiguar INFANTILES/CADETES/JUVENILES cuando el CSV
    trae nombres viejos (2023-2024) vs nuevos (2025+).
    """
    if not isinstance(categoria, str) or not categoria.strip():
        return None
    cat = _normalizar_texto(categoria)

    if cat in _NO_COMPETITIVAS:
        return None

    # PREINFANTILES (histórico o error de scrape): siempre U13 / INFANTILES
    if cat.startswith("PREINFANTIL"):
        return _PREINFANTILES_A_BUCKET

    # Formato nuevo explícito
    if cat in _NUEVO_CSV_A_BUCKET and (
        "MASCULINO" in cat or "LIGA PROXIMO" in cat
    ):
        return _NUEVO_CSV_A_BUCKET[cat]

    if anio is not None and int(anio) >= 2025:
        return _NUEVO_CSV_A_BUCKET.get(cat) or _LEGACY_CSV_A_BUCKET.get(cat)

    # 2023-2024 y fallback: nombres legacy desplazados
    if cat in _LEGACY_CSV_A_BUCKET:
        return _LEGACY_CSV_A_BUCKET[cat]

    if cat in _NUEVO_CSV_A_BUCKET:
        return _NUEVO_CSV_A_BUCKET[cat]

    m = re.search(r"\bU\s*-?\s*(\d+)\b", cat, re.IGNORECASE)
    if m:
        return _U_A_BUCKET.get(m.group(1))

    return None


def categoria_canonica(categoria: str, anio: int | None = None) -> Optional[str]:
    """Alias de ``bucket_renivelacion`` (nombre de columna acumulada)."""
    return bucket_renivelacion(categoria, anio)


def es_categoria_competitiva(categoria: str, anio: int | None = None) -> bool:
    return bucket_renivelacion(categoria, anio) is not None


def sufijo_columna(categoria: str) -> str:
    return categoria.replace(" ", "_")


def columna_puntos(prefijo: str, categoria: str) -> str:
    return f"{prefijo}_{sufijo_columna(categoria)}"


def es_forfait_perdedor(pts_propio: int, pts_rival: int) -> bool:
    return pts_propio == 0 and pts_rival == 20


def banda_u(categoria: str, anio: int | None = None) -> Optional[str]:
    return bucket_renivelacion(categoria, anio)


BANDAS_COMPETITIVAS = frozenset(CATEGORIAS_COMPETITIVAS)
