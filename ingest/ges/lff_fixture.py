# -*- coding: utf-8 -*-
"""
Fixture Liga Federal Cadetes (U15) vía GES.

Fuentes (en orden):
  1. Widget ``widgetscab…/widget/informacion/partidos/{id_categoria}/-3/7`` (POST con fechas).
  2. Calendario embebido en ``competicion.aspx`` (postbacks fase/grupo).

El ``4643`` del widget es ``id_categoria`` GES (Cadetes masculina), no el compCatId de
argentina.basketball que devuelve Liga Federal mayores vía CargarFixture.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ingest.argbasket.lff_constants import LFF_GES_COMPETENCIA_ID, LFF_GES_ID_CATEGORIA
from ingest.febamba.competicion_calendar import CompeticionCalendarScraper
from ingest.ges.extractor import GesDeportivaExtractor
from ingest.ges.partido_ids import synthetic_partido_id
from ingest.http_client import HttpClient


def _clave_partido(fecha: str, local: str, visitante: str) -> Tuple[str, str, str]:
    return (fecha.strip(), local.strip(), visitante.strip())


def _widget_a_fila(
    p: Dict[str, str],
    *,
    nombre_fase: str,
    nombre_grupo: str,
    id_categoria: int,
    id_competencia: int,
) -> Dict[str, str]:
    fecha = (p.get("Fecha") or "").strip()
    local = (p.get("Local") or "").strip()
    visitante = (p.get("Visitante") or "").strip()
    pid = (p.get("ID_PARTIDO") or "").strip()
    if not pid and fecha and local and visitante:
        pid = synthetic_partido_id(id_competencia, id_categoria, fecha, local, visitante)
    return {
        "id_partido_token": pid,
        "Local": local,
        "Visitante": visitante,
        "PTS_LOCAL": (p.get("PTS_LOCAL") or "").strip(),
        "PTS_VISITANTE": (p.get("PTS_VISITANTE") or "").strip(),
        "DIF_PTS": (p.get("DIF_PTS") or "").strip(),
        "Fecha_Programada": fecha,
        "hora_inicio_partido": "",
        "hora_fin_partido": "",
        "URL_Estadisticas": (p.get("URL") or "").strip(),
        "id_categoria": str(id_categoria),
        "id_competencia": str(id_competencia),
        "id_fase": (p.get("ID_FASE") or "").strip(),
        "id_grupo": (p.get("ID_GRUPO") or "").strip(),
        "fase_ges": nombre_fase,
        "grupo_ges": nombre_grupo,
        "fuente": "widget",
    }


def _calendar_a_fila(
    row: Dict[str, object],
    *,
    id_competencia: int,
) -> Dict[str, str]:
    fecha = str(row.get("Fecha") or "").strip()
    local = str(row.get("Local") or "").strip()
    visitante = str(row.get("Visitante") or "").strip()
    id_cat = int(str(row.get("id_categoria") or "0") or "0")
    pid = synthetic_partido_id(id_competencia, id_cat, fecha, local, visitante)
    return {
        "id_partido_token": pid,
        "Local": local,
        "Visitante": visitante,
        "PTS_LOCAL": "",
        "PTS_VISITANTE": "",
        "DIF_PTS": "",
        "Fecha_Programada": fecha,
        "hora_inicio_partido": "",
        "hora_fin_partido": "",
        "URL_Estadisticas": "",
        "id_categoria": str(row.get("id_categoria") or ""),
        "id_competencia": str(id_competencia),
        "id_fase": str(row.get("id_fase") or ""),
        "id_grupo": str(row.get("id_grupo") or ""),
        "fase_ges": str(row.get("fase_ges") or ""),
        "grupo_ges": str(row.get("grupo_ges") or ""),
        "fuente": "competicion",
    }


def fetch_lff_cadetes_fixture_ges(
    genero: str,
    *,
    fecha_inicio: str,
    fecha_fin: str,
    widget_key: str,
    id_competencia: int = LFF_GES_COMPETENCIA_ID,
    client: Optional[HttpClient] = None,
    prefer_widget: bool = True,
    include_calendar: bool = True,
) -> List[Dict[str, str]]:
    """
    Devuelve filas de fixture Cadetes desde GES.

    Recorre todas las fases/grupos de la categoría e intenta el widget; si no hay filas
    del widget, incorpora el esqueleto de ``competicion.aspx``.
    """
    if genero not in LFF_GES_ID_CATEGORIA:
        raise ValueError(f"genero debe ser masc|fem, recibido: {genero!r}")

    id_categoria = LFF_GES_ID_CATEGORIA[genero]
    http = client or HttpClient()
    ges = GesDeportivaExtractor(http)
    fases, grupos = ges.get_ids_fases_grupos(id_competencia, id_categoria=id_categoria)
    fases_iter = list(fases.items()) or [("TODAS", "-1")]
    grupos_iter = list(grupos.items()) or [("TODOS", "-1")]

    out: Dict[Tuple[str, str, str], Dict[str, str]] = {}

    if prefer_widget:
        for nombre_fase, id_fase in fases_iter:
            for nombre_grupo, id_grupo in grupos_iter:
                try:
                    batch = ges.get_info_partidos(
                        id_categoria,
                        fecha_inicio,
                        fecha_fin,
                        key=widget_key,
                        id_fase=int(id_fase) if str(id_fase).lstrip("-").isdigit() else -1,
                        id_grupo=int(id_grupo) if str(id_grupo).lstrip("-").isdigit() else -1,
                    )
                except Exception:
                    continue
                for p in batch:
                    fila = _widget_a_fila(
                        p,
                        nombre_fase=nombre_fase,
                        nombre_grupo=nombre_grupo,
                        id_categoria=id_categoria,
                        id_competencia=id_competencia,
                    )
                    if not fila["Local"] or not fila["Visitante"]:
                        continue
                    out[_clave_partido(fila["Fecha_Programada"], fila["Local"], fila["Visitante"])] = fila

    if include_calendar:
        scraper = CompeticionCalendarScraper(http, sleep_s=0.25)
        for row in scraper.iter_skeleton_rows(id_competencia, id_categoria=id_categoria):
            fila = _calendar_a_fila(row, id_competencia=id_competencia)
            key = _clave_partido(fila["Fecha_Programada"], fila["Local"], fila["Visitante"])
            if key in out:
                # Enriquecer metadatos de fase/grupo si el widget ya tenía el partido.
                prev = out[key]
                if not prev.get("fase_ges"):
                    prev["fase_ges"] = fila["fase_ges"]
                if not prev.get("grupo_ges"):
                    prev["grupo_ges"] = fila["grupo_ges"]
                continue
            out[key] = fila

    return sorted(out.values(), key=lambda r: (r.get("Fecha_Programada") or "", r.get("Local") or ""))
