# -*- coding: utf-8 -*-
"""
Clave natural para cruzar calendario GES (sin id_partido) con fixture argentina.basketball.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

_RE_FECHA_DDMMYYYY = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")


def normalize_team_name(name: str) -> str:
    t = (name or "").replace("\n", " ").replace("\xa0", " ")
    t = " ".join(t.split())
    return t.upper()


def extract_fecha_dd_mm_yyyy(text: str) -> str:
    """
    Extrae 'DD/MM/YYYY' desde textos tipo 'lun 27/04/2026 20:00' o '27/04/2026'.
    Si no hay match, devuelve la primera porción sin espacios extra.
    """
    s = (text or "").strip()
    if not s:
        return ""
    m = _RE_FECHA_DDMMYYYY.search(s)
    if m:
        return m.group(1)
    head = s.split()[0]
    if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", head):
        return head
    return head


def natural_match_key(fecha_dd_mm_yyyy: str, local: str, visitante: str) -> str:
    fe = (fecha_dd_mm_yyyy or "").strip()
    return f"{fe}|{normalize_team_name(local)}|{normalize_team_name(visitante)}"


def natural_key_from_db_partido_row(row: Dict[str, object]) -> str:
    """Misma clave que GES/fixture usando columnas ``fecha``, ``local``, ``visitante`` de BD."""
    fecha_raw = str(row.get("fecha") or "").strip()
    fe = extract_fecha_dd_mm_yyyy(fecha_raw)
    loc = str(row.get("local") or "")
    vis = str(row.get("visitante") or "")
    if not fe or not loc or not vis:
        return ""
    return natural_match_key(fe, loc, vis)


def natural_key_from_ges_partido_row(row: Dict[str, str]) -> str:
    fecha_raw = (row.get("Fecha") or "").strip()
    fe = extract_fecha_dd_mm_yyyy(fecha_raw)
    return natural_match_key(
        fe, row.get("Local") or "", row.get("Visitante") or ""
    )


def natural_key_from_argentina_fixture_row(row: Dict[str, str]) -> str:
    fe = extract_fecha_dd_mm_yyyy(row.get("Fecha_Programada") or "")
    loc = row.get("Local") or ""
    vis = row.get("Visitante") or ""
    if not fe or not loc or not vis:
        return ""
    return natural_match_key(fe, loc, vis)


def index_argentina_rows_by_natural_key(
    rows: List[Dict[str, str]],
) -> Dict[str, Dict[str, str]]:
    """Última fila gana si hay colisión (mismo cruce en distintas ventanas de fecha)."""
    idx: Dict[str, Dict[str, str]] = {}
    for r in rows:
        k = natural_key_from_argentina_fixture_row(r)
        if k:
            idx[k] = r
    return idx


def merge_torneo_ctx_from_ges_skeleton(
    argentina_by_token: Dict[str, Dict],
    ges_rows: List[Dict[str, str]],
    ctx_torneo: Dict,
    id_fase: str,
    id_grupo: str,
) -> None:
    """
    Para cada fila del calendario GES (widget u otra fuente), si la clave natural
    coincide con un partido ya indexado por token argentino, actualiza TORNEO_CTX
    e IDs de fase/grupo si antes estaban vacíos o eran placeholders.
    """
    nk_to_tokens: Dict[str, List[str]] = {}
    for tok, item in argentina_by_token.items():
        nk = natural_key_from_argentina_fixture_row(item["_arg_row"])
        nk_to_tokens.setdefault(nk, []).append(tok)

    for s in ges_rows:
        nk = natural_key_from_ges_partido_row(s)
        for tok in nk_to_tokens.get(nk, ()):
            entry = argentina_by_token[tok]
            prev = entry.get("TORNEO_CTX") or {}
            if not (prev.get("fase_ges") or prev.get("grupo_ges")) and (
                ctx_torneo.get("fase_ges") or ctx_torneo.get("grupo_ges")
            ):
                entry["TORNEO_CTX"] = ctx_torneo
                entry["ID_FASE"] = str(id_fase)
                entry["ID_GRUPO"] = str(id_grupo)
