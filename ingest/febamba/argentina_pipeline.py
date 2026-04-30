# -*- coding: utf-8 -*-
"""
Orquestación temporada >= 2026: fixture argentina.basketball + contexto torneo
desde competicion.aspx (fase/grupo), cruce opcional con calendario widget GES.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List, Tuple

from ingest.errors import NetworkError, ParseError
from ingest.febamba.fixture_contexto import merge_contexto_torneo
from ingest.febamba.fixture_parser_arg import ArgentinaFixtureParser
from ingest.febamba.natural_key import (
    extract_fecha_dd_mm_yyyy,
    merge_torneo_ctx_from_ges_skeleton,
)
from ingest.febamba.runtime_ctx import get_comp_cat_argentina_id
from ingest.ges.extractor import GesDeportivaExtractor


def _infer_estado(fecha_prog: str, pts_local: str, pts_visit: str) -> str:
    estado = "PENDIENTE"
    try:
        fe = extract_fecha_dd_mm_yyyy(fecha_prog)
        if not fe:
            return estado
        fecha_dt = datetime.strptime(fe, "%d/%m/%Y")
        pl = (pts_local or "").strip().replace("\n", "")
        pv = (pts_visit or "").strip().replace("\n", "")
        pl_num = int(pl) if pl and pl.replace("-", "").isdigit() else None
        pv_num = int(pv) if pv and pv.replace("-", "").isdigit() else None
        if fecha_dt.date() < datetime.now().date() and pl_num is not None and pv_num is not None:
            estado = "COMPLETO"
    except Exception:
        pass
    return estado


def ges_shape_from_argentina_row(
    row: Dict[str, str],
    *,
    id_fase: str,
    id_grupo: str,
    torneo_ctx: Dict,
) -> Dict[str, str]:
    tok = (row.get("id_partido_token") or "").strip()
    fe = extract_fecha_dd_mm_yyyy(row.get("Fecha_Programada") or "")
    fecha_display = fe or (row.get("Fecha_Programada") or "").strip()
    pl = row.get("PTS_LOCAL") or ""
    pv = row.get("PTS_VISITANTE") or ""
    return {
        "ID_PARTIDO": tok,
        "Fecha": fecha_display,
        "Local": (row.get("Local") or "").strip(),
        "Visitante": (row.get("Visitante") or "").strip(),
        "PTS_LOCAL": pl,
        "PTS_VISITANTE": pv,
        "DIF_PTS": row.get("DIF_PTS") or "",
        "Estado": _infer_estado(row.get("Fecha_Programada") or "", pl, pv),
        "URL": (row.get("URL_Estadisticas") or "").strip(),
        "ID_FASE": str(id_fase),
        "ID_GRUPO": str(id_grupo),
        "TORNEO_CTX": torneo_ctx,
    }


def _use_ges_widget_skeleton_merge() -> bool:
    v = os.environ.get("FEBAMBA_GES_WIDGET_CALENDAR", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def collect_partidos_temporada_2026(
    *,
    ges: GesDeportivaExtractor,
    temporada: str,
    id_categoria: int,
    fecha_inicio: str,
    fecha_fin: str,
    widget_key: str,
    fases: Dict[str, str],
    grupos: Dict[str, str],
    session,
) -> List[Dict[str, str]]:
    """
    1) Descarga fixture completo (argentina.basketball) por ventanas de fechas.
    2) Opcional: si ``FEBAMBA_GES_WIDGET_CALENDAR=1``, cruza filas del widget GES
       (misma clave natural) para rellenar fase_ges / grupo_ges / zona / nivel / ronda.
    3) Sin skeleton GES, ``TORNEO_CTX`` queda vacío salvo lo que añadas luego en BD.
    """
    comp_cat_id = get_comp_cat_argentina_id(id_categoria)
    parser = ArgentinaFixtureParser(session=session, timeout_s=60, chunk_days=45)
    raw_rows = parser.fetch_all_chunked(comp_cat_id, fecha_inicio, fecha_fin)

    by_token: Dict[str, Dict] = {}
    for r in raw_rows:
        tok = (r.get("id_partido_token") or "").strip()
        if not tok:
            continue
        by_token[tok] = {
            "_arg_row": r,
            "TORNEO_CTX": {},
            "ID_FASE": "-1",
            "ID_GRUPO": "-1",
        }

    if _use_ges_widget_skeleton_merge() and widget_key:
        fases_iter = list(fases.items()) or [("TODAS", "-1")]
        grupos_iter = list(grupos.items()) or [("TODOS", "-1")]
        for nombre_fase, id_fase in fases_iter:
            for nombre_grupo, id_grupo in grupos_iter:
                try:
                    # Llamada explícita a la implementación del widget en la clase base
                    # (FebambaDualSourceExtractor sobrescribe get_info_partidos para Argentina).
                    sub = GesDeportivaExtractor.get_info_partidos(
                        ges,
                        id_categoria,
                        fecha_inicio,
                        fecha_fin,
                        widget_key,
                        int(id_fase) if str(id_fase).lstrip("-").isdigit() else -1,
                        int(id_grupo) if str(id_grupo).lstrip("-").isdigit() else -1,
                    )
                except (NetworkError, ParseError, Exception):
                    continue
                ctx = merge_contexto_torneo(temporada, nombre_fase, nombre_grupo)
                merge_torneo_ctx_from_ges_skeleton(
                    by_token,
                    sub,
                    ctx,
                    str(id_fase),
                    str(id_grupo),
                )

    out: List[Dict[str, str]] = []
    for tok in sorted(by_token.keys()):
        entry = by_token[tok]
        r = entry["_arg_row"]
        ctx = entry.get("TORNEO_CTX") or {}
        out.append(
            ges_shape_from_argentina_row(
                r,
                id_fase=str(entry.get("ID_FASE", "-1")),
                id_grupo=str(entry.get("ID_GRUPO", "-1")),
                torneo_ctx=ctx,
            )
        )
    return out
