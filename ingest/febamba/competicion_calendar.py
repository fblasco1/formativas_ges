# -*- coding: utf-8 -*-
"""
Calendario / resultados embebidos en ``competicion.aspx`` (sin widgetscab).

Recorre categoría → fase → grupo vía postbacks ASP.NET WebForms y parsea las
tablas con columnas Local / Visitante / Fecha.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple

from bs4 import BeautifulSoup
from bs4.element import Tag

from ingest.errors import ParseError
from ingest.http_client import HttpClient

_COMP_URL = "https://competicionescabb.gesdeportiva.es/competicion.aspx"


def _default_headers(referer: str) -> Dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Origin": "https://competicionescabb.gesdeportiva.es",
        "Referer": referer,
        "Content-Type": "application/x-www-form-urlencoded",
    }


def _collect_form_payload(form: Tag) -> Dict[str, str]:
    data: Dict[str, str] = {}
    for inp in form.find_all(["input", "select", "textarea"]):
        name = inp.get("name")
        if not name:
            continue
        if inp.name == "input":
            t = (inp.get("type") or "").lower()
            if t in ("checkbox", "radio") and not inp.get("checked"):
                continue
            data[name] = inp.get("value") or ""
        elif inp.name == "select":
            sel = inp.find("option", selected=True)
            if sel is not None and sel.get("value") is not None:
                data[name] = str(sel.get("value"))
            else:
                first = inp.find("option")
                data[name] = str(first.get("value")) if first and first.get("value") is not None else ""
        else:
            data[name] = inp.get_text() or ""
    return data


def _find_select(soup: BeautifulSoup, *ids: str) -> Optional[Tag]:
    for sid in ids:
        sel = soup.find("select", {"id": sid})
        if sel:
            return sel
    return None


def _select_options(sel: Tag) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for opt in sel.find_all("option"):
        val = opt.get("value")
        if val is None or str(val).strip() in {"", "0"}:
            continue
        out.append((opt.get_text(strip=True), str(val).strip()))
    return out


def _strip_prefijo_jornada(nombre: str) -> str:
    """Quita prefijos tipo ``'1 '`` que a veces antepone la tabla de resultados."""
    return re.sub(r"^\d+\s+", "", (nombre or "").strip()).strip()


def _parse_partido_tables(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """
    Extrae filas (Fecha, Local, Visitante) de tablas de jornada / resultados.
    Ignora clasificación, equipos, etc.
    """
    rows: List[Dict[str, str]] = []
    for table in soup.find_all("table"):
        tr0 = table.find("tr")
        if not tr0:
            continue
        headers = [c.get_text(strip=True) for c in tr0.find_all(["th", "td"])]
        if not headers or not any(headers):
            continue
        hnorm = "|".join(headers)
        if "Club" in hnorm and "Localidad" in hnorm:
            continue
        if "PJ" in headers or "PG" in headers or "PF" in headers:
            continue

        if headers[0] == "Fecha" or (headers[0] and "Fecha" in headers[0]):
            idx_vis = None
            for i, h in enumerate(headers):
                if h == "Visitante":
                    idx_vis = i
                    break
            if idx_vis is None:
                idx_vis = 6 if len(headers) > 6 else len(headers) - 1
            for tr in table.find_all("tr")[1:]:
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
                if len(cells) <= max(1, idx_vis):
                    continue
                fe, lo, vi = cells[0], cells[1], cells[idx_vis]
                if not fe or not lo or not vi:
                    continue
                if lo.upper() == "LOCAL" or vi.upper() == "VISITANTE":
                    continue
                if re.fullmatch(r"\d+", lo) or re.fullmatch(r"\d+", vi):
                    continue
                lo, vi = _strip_prefijo_jornada(lo), _strip_prefijo_jornada(vi)
                rows.append({"Fecha": fe, "Local": lo, "Visitante": vi})
            continue

        if headers[0] == "Local" and any(h == "Visitante" for h in headers):
            idx: Dict[str, int] = {}
            for i, h in enumerate(headers):
                if h:
                    idx[h] = i
            il = idx.get("Local", 0)
            iv = idx.get("Visitante", 3)
            ife = idx.get("Fecha", 4)
            for tr in table.find_all("tr")[1:]:
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
                if len(cells) <= max(il, iv, ife):
                    continue
                lo, vi, fe = cells[il], cells[iv], cells[ife]
                if not fe or not lo or not vi:
                    continue
                if lo.upper() == "LOCAL" or vi.upper() == "VISITANTE":
                    continue
                if re.fullmatch(r"\d+", lo) or re.fullmatch(r"\d+", vi):
                    continue
                lo, vi = _strip_prefijo_jornada(lo), _strip_prefijo_jornada(vi)
                rows.append({"Fecha": fe, "Local": lo, "Visitante": vi})

    return rows


class CompeticionCalendarScraper:
    """POSTs encadenados sobre ``competicion.aspx``."""

    def __init__(self, client: HttpClient, *, sleep_s: float = 0.35) -> None:
        self._client = client
        self._sleep_s = sleep_s

    def _get(self, competencia: int) -> Tuple[str, BeautifulSoup, Tag]:
        url = f"{_COMP_URL}?competencia={competencia}"
        resp = self._client.request("GET", url, headers=_default_headers(url), timeout=25)
        text = resp.text
        if "charset" not in (resp.headers.get("content-type") or "").lower():
            enc = resp.apparent_encoding or resp.encoding or "utf-8"
            resp.encoding = enc
            text = resp.text
        soup = BeautifulSoup(text, "html.parser")
        form = soup.find("form")
        if not form:
            raise ParseError("competicion.aspx: no se encontró <form>")
        return url, soup, form

    def _post(self, url: str, form: Tag, event_target: str, overrides: Dict[str, str]) -> Tuple[BeautifulSoup, Tag]:
        time.sleep(self._sleep_s)
        payload = _collect_form_payload(form)
        payload["__EVENTTARGET"] = event_target
        payload["__EVENTARGUMENT"] = ""
        payload.update(overrides)
        resp = self._client.request(
            "POST",
            url,
            headers=_default_headers(url),
            data=payload,
            timeout=30,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        form2 = soup.find("form")
        if not form2:
            raise ParseError("Respuesta POST sin <form>")
        return soup, form2

    def iter_skeleton_rows(
        self,
        competencia: int,
        *,
        id_categoria: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        """
        Por cada (categoría, fase, grupo) devuelve filas dict con:
        fecha, local, visitante, fase_ges, grupo_ges, id_fase, id_grupo, id_categoria.
        """
        url, soup, form = self._get(competencia)
        sel_cat = soup.find("select", {"id": "DDLCategorias"})
        if not sel_cat:
            raise ParseError("No hay DDLCategorias en competicion.aspx")

        categorias = _select_options(sel_cat)
        if id_categoria is not None:
            categorias = [(n, v) for n, v in categorias if int(v) == int(id_categoria)]
            if not categorias:
                raise ParseError(f"Categoría {id_categoria} no encontrada en la competencia {competencia}")

        for nombre_cat, val_cat in categorias:
            soup_c, form_after_cat = self._post(
                url, form, "DDLCategorias", {"DDLCategorias": str(val_cat)}
            )
            form = form_after_cat
            sel_fase = _find_select(
                soup_c, "DDLFases", "DDLFase", "DDLFASE", "DDLFaseCompeticion"
            )
            fases = _select_options(sel_fase) if sel_fase else []
            if not fases:
                fases = [("TODAS", "-1")]

            for nombre_fase, val_fase in fases:
                if str(val_fase) == "-1":
                    soup_f, form_f = soup_c, form_after_cat
                else:
                    soup_f, form_f = self._post(
                        url, form_after_cat, "DDLFases", {"DDLFases": str(val_fase)}
                    )
                sel_grupo_f = _find_select(
                    soup_f, "DDLGrupos", "DDLGrupo", "DDLGRUPO", "DDLGrupoCompeticion"
                )
                grupos = _select_options(sel_grupo_f) if sel_grupo_f else [("TODOS", "-1")]

                form_cursor = form_f
                for nombre_grupo, val_grupo in grupos:
                    if str(val_grupo) == "-1":
                        soup_g = soup_f
                    else:
                        soup_g, form_cursor = self._post(
                            url, form_cursor, "DDLGrupos", {"DDLGrupos": str(val_grupo)}
                        )
                    for row in _parse_partido_tables(soup_g):
                        row["fase_ges"] = nombre_fase
                        row["grupo_ges"] = nombre_grupo
                        row["id_fase"] = str(val_fase)
                        row["id_grupo"] = str(val_grupo)
                        row["id_categoria"] = str(val_cat)
                        row["nombre_categoria"] = nombre_cat
                        yield row


def scrape_skeleton_desde_competicion(
    competencia: int,
    *,
    id_categoria: Optional[int] = None,
    client: Optional[HttpClient] = None,
    sleep_s: float = 0.35,
) -> List[Dict[str, Any]]:
    """Lista materializada (puede ser grande)."""
    c = client or HttpClient()
    sc = CompeticionCalendarScraper(c, sleep_s=sleep_s)
    return list(sc.iter_skeleton_rows(competencia, id_categoria=id_categoria))
