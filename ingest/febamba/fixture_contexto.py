"""
Normaliza fase / zona / grupo según reglas de `parsers/` (rama develop).

Usa el texto de los combos GES (`competicion.aspx` + widget) y el año de torneo
inferido desde `temporada` (ej. \"2024\", \"2024/2025\" → 2024).
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from parsers.fases import parsear_fase
from parsers.grupos import parsear_grupo

_DESCONOCIDO = frozenset({"Desconocido", "Desconocida", "Desconocidos"})


def year_from_temporada(temporada: str) -> int:
    t = (temporada or "").strip()
    m = re.search(r"(\d{4})", t)
    if m:
        return int(m.group(1))
    return 2024


def _es_placeholder_fase(nombre: str) -> bool:
    u = (nombre or "").strip().upper()
    return u in {"", "TODAS", "TODOS", "-1"}


def _es_placeholder_grupo(nombre: str) -> bool:
    u = (nombre or "").strip().upper()
    return u in {"", "TODOS", "TODAS", "-1"}


def _limpiar(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s in _DESCONOCIDO:
        return None
    return s


def merge_contexto_torneo(
    temporada: str,
    fase_combo_ges: str,
    grupo_combo_ges: str,
) -> Dict[str, Optional[str]]:
    """
    Devuelve claves alineadas con columnas `partidos`:
    - fase, grupo: nombres normalizados (FeBAMBA / develop)
    - fase_ges, grupo_ges: texto original del fixture GES (combos)
    - zona, ronda, nivel: desglose develop
    """
    f_raw = (fase_combo_ges or "").strip()
    g_raw = (grupo_combo_ges or "").strip()
    year = year_from_temporada(temporada)

    out: Dict[str, Optional[str]] = {
        "fase_ges": None,
        "grupo_ges": None,
        "fase": None,
        "grupo": None,
        "zona": None,
        "ronda": None,
        "nivel": None,
    }

    if _es_placeholder_fase(f_raw) and _es_placeholder_grupo(g_raw):
        return out

    if not _es_placeholder_fase(f_raw):
        out["fase_ges"] = f_raw
    if not _es_placeholder_grupo(g_raw):
        out["grupo_ges"] = g_raw

    f_eff = "" if _es_placeholder_fase(f_raw) else f_raw
    g_eff = "" if _es_placeholder_grupo(g_raw) else g_raw

    pf: Optional[Dict[str, str]] = None
    if f_eff:
        pf = parsear_fase(year, f_eff)
        out["fase"] = _limpiar(pf.get("fase"))
        out["ronda"] = _limpiar(pf.get("ronda"))
        out["nivel"] = _limpiar(pf.get("nivel"))
        out["zona"] = _limpiar(pf.get("zona"))

    if g_eff:
        pg = parsear_grupo(year, f_eff, g_eff)
        out["grupo"] = _limpiar(pg.get("grupo"))
        zn = _limpiar(pg.get("zona"))
        if zn:
            out["zona"] = zn
        nv = _limpiar(pg.get("nivel"))
        if nv:
            out["nivel"] = nv
    elif pf:
        out["grupo"] = _limpiar(pf.get("grupo"))

    if pf and not out["nivel"]:
        out["nivel"] = _limpiar(pf.get("nivel"))

    return out
