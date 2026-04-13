# -*- coding: utf-8 -*-
"""
Scraper ETL FeBAMBA — extracción de partidos de torneos formativos.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from bs4 import BeautifulSoup

from mapeos.loader import (
    cargar_mapeo_categorias,
    cargar_mapeo_equipos,
    normalizar_equipo,
)
from parsers.fases import parsear_fase
from parsers.grupos import parsear_grupo
from parsers.jornadas import parsear_jornada
from parsers.rondas import inferir_ronda
from utils.logger import get_logger
from utils.requester import hacer_solicitud
from utils.torneos_febamba import inferir_anio

logger = get_logger("FebambaScraper")


class FebambaScraper:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.categorias_map = cargar_mapeo_categorias()
        self.equipos_map = cargar_mapeo_equipos()
        self.partidos_acumulados: List[Dict[str, Any]] = []

    def scrap_torneo(self, torneo_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Scrapea todo un torneo: categorías, fases, grupos y partidos."""
        self.partidos_acumulados = []
        nombre = str(torneo_info.get("torneo") or "")
        year = inferir_anio(nombre)
        if year is None:
            year = torneo_info.get("Anio")
        if year is None:
            logger.error(
                "No se pudo determinar el año del torneo %r (usar nombre con 20xx o clave Anio)",
                nombre,
            )
            return []

        url_inicial = torneo_info["url"]
        logger.info(
            "Iniciando scraping: %s (%s)",
            nombre,
            year,
        )
        html = hacer_solicitud(url_inicial)
        if not html:
            logger.error("No se pudo obtener página inicial %s", url_inicial)
            return []

        soup = BeautifulSoup(html, "html.parser")
        categorias_select = soup.find("select", {"name": "DDLCategorias"})
        if not categorias_select:
            logger.warning("No se encontró selector de categorías en %s", url_inicial)
            return []

        for option in categorias_select.find_all("option"):
            cat_web = option.text.strip()
            cat_id = option.get("value")
            if not cat_id or cat_id == "0" or "Seleccionar" in cat_web:
                continue

            if cat_web.lower() == "mosquitos":
                logger.info("Saltando categoría: Mosquitos")
                continue

            cat_mapa = self.categorias_map.get(cat_web, None)
            if cat_mapa is None:
                cat_mapa = next(
                    (
                        v
                        for k, v in self.categorias_map.items()
                        if k.lower() == cat_web.lower()
                    ),
                    cat_web,
                )
            logger.info(
                "Categoría: %s → %s (id=%s)",
                cat_web,
                cat_mapa,
                cat_id,
            )

            partidos_categoria = self._scrap_fases_categoria(
                year, cat_mapa, url_inicial, cat_id
            )
            self.partidos_acumulados.extend(partidos_categoria)

            logger.info("Partidos acumulados: %s", len(self.partidos_acumulados))
            time.sleep(2)

        return self.partidos_acumulados

    def _scrap_fases_categoria(
        self, year: int, cat_mapa: str, url_torneo: str, cat_id: str
    ) -> List[Dict[str, Any]]:
        """Scrapea todas las fases de una categoría."""
        url_fases = f"{url_torneo}&categoria={cat_id}"
        html = hacer_solicitud(url_fases)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        fases_select = soup.find("select", {"name": "DDLFases"})
        if not fases_select:
            logger.error("No se encontró DDLFases en %s", url_fases)
            return []

        partidos_categoria: List[Dict[str, Any]] = []

        for option in fases_select.find_all("option"):
            fase_id = option.get("value")
            fase_text = option.text.strip()

            if not fase_id or fase_id == "0" or "Seleccionar" in fase_text:
                continue

            partidos_fase = self._scrap_grupos_fase(
                year, cat_mapa, url_fases, fase_id, fase_text
            )
            partidos_categoria.extend(partidos_fase)

            time.sleep(1)

        return partidos_categoria

    def _scrap_grupos_fase(
        self,
        year: int,
        cat_mapa: str,
        url_fase: str,
        fase_id: str,
        fase_text: str,
    ) -> List[Dict[str, Any]]:
        """Scrapea todos los grupos de una fase."""
        url_grupos = f"{url_fase}&fase={fase_id}"
        html = hacer_solicitud(url_grupos)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        grupos_select = soup.find("select", {"name": "DDLGrupos"})

        partidos_fase: List[Dict[str, Any]] = []

        if not grupos_select:
            fase_info = parsear_fase(year, fase_text, None)
            partidos_grupo = self._scrap_partidos_grupo(
                url_grupos, year, cat_mapa, fase_info, None, None, fase_text
            )
            partidos_fase.extend(partidos_grupo)
        else:
            for option in grupos_select.find_all("option"):
                grupo_id = option.get("value")
                grupo_text = option.text.strip()

                if not grupo_id or grupo_id == "0" or "Seleccionar" in grupo_text:
                    continue

                fase_info = parsear_fase(year, fase_text, grupo_text)
                grupo_info = parsear_grupo(year, fase_text, grupo_text)
                url_grupo = f"{url_grupos}&grupo={grupo_id}"

                partidos_grupo = self._scrap_partidos_grupo(
                    url_grupo,
                    year,
                    cat_mapa,
                    fase_info,
                    grupo_info,
                    grupo_text,
                    fase_text,
                )
                partidos_fase.extend(partidos_grupo)

                time.sleep(0.5)

        return partidos_fase

    def _scrap_partidos_grupo(
        self,
        url_grupo: str,
        year: int,
        cat_mapa: str,
        fase_info: Dict[str, Any],
        grupo_info: Dict[str, Any] | None,
        grupo_ddl: str | None = None,
        fase_text_ddl: str | None = None,
    ) -> List[Dict[str, Any]]:
        """Scrapea partidos de un grupo específico."""
        ginfo = grupo_info or {}
        html = hacer_solicitud(url_grupo)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        tab_pane = soup.find(
            "div", id="ctl00_ContentPlaceHolder1_UpdatePanel1"
        ) or soup.find("div", id="calendario")

        if not tab_pane:
            logger.warning("No se encontró div de partidos en %s", url_grupo)
            return []

        tables = tab_pane.find_all("table", class_="tabla") or tab_pane.find_all(
            "table"
        )
        if not tables:
            logger.warning("No se encontraron tablas de partidos en %s", url_grupo)
            return []

        partidos: List[Dict[str, Any]] = []

        for table in tables:
            jornada_tag = table.find_previous_sibling("h4") or table.find_previous("h4")
            ronda, jornada, fecha = parsear_jornada(jornada_tag.text.strip())

            for row in table.find_all("tr")[1:]:
                cells = row.find_all("td")
                if len(cells) < 4:
                    continue

                local_raw, pts_local_raw, pts_visitante_raw, visitante_raw = [
                    c.text.strip() for c in cells[:4]
                ]

                if not pts_local_raw or not pts_visitante_raw:
                    continue

                nivel_pre = (
                    fase_info.get("nivel", "Desconocido")
                    if fase_info.get("nivel") != "Desconocido"
                    else ginfo.get("nivel", "Desconocido")
                )
                _zg = ginfo.get("zona", "Desconocida")
                if ginfo.get("zona_refina") and _zg not in (
                    "Desconocida",
                    "Desconocido",
                    None,
                    "",
                ):
                    zona_pre = _zg
                else:
                    zona_pre = (
                        fase_info["zona"]
                        if fase_info["zona"] != "Desconocida"
                        else ginfo.get("zona", "Desconocida")
                    )
                fase_pre = (
                    ginfo["fase"] if "fase" in ginfo else fase_info.get("fase", "")
                )

                ronda_inferida = inferir_ronda(
                    year,
                    cat_mapa,
                    nivel_pre,
                    zona_pre,
                    jornada,
                    fase_pre or "",
                    local_raw,
                    visitante_raw,
                    self.equipos_map,
                    grupo_ddl=grupo_ddl,
                    fase_ddl=fase_text_ddl,
                )

                ronda_val = None
                llave_val = None
                nivel_val = None
                zona_inferida = None
                if isinstance(ronda_inferida, dict):
                    ronda_val = ronda_inferida.get("ronda") if ronda == "" else ronda
                    llave_val = ronda_inferida.get("llave")
                    nivel_val = ronda_inferida.get("nivel")
                    zona_inferida = ronda_inferida.get("zona")
                else:
                    ronda_val = ronda_inferida if ronda == "" else ronda
                    llave_val = None
                    nivel_val = None

                fase_partido = (
                    ginfo["fase"] if "fase" in ginfo else fase_info.get("fase")
                )
                fase_actual = (fase_partido or "").upper()

                if ginfo.get("zona_refina") and _zg not in (
                    "Desconocida",
                    "Desconocido",
                    None,
                    "",
                ):
                    zona_partido = _zg
                else:
                    zona_partido = (
                        fase_info["zona"]
                        if fase_info["zona"] != "Desconocida"
                        else ginfo.get("zona", "Desconocida")
                    )
                if (
                    zona_inferida
                    and str(zona_inferida) not in ("", "Desconocida", "Desconocido")
                ):
                    zona_partido = str(zona_inferida)

                _ng = ginfo.get("nivel", "Desconocido")
                if ginfo.get("nivel_refina") and _ng not in (
                    "Desconocido",
                    None,
                    "",
                ):
                    nivel_partido = _ng
                else:
                    nivel_partido = (
                        nivel_val
                        if nivel_val is not None and nivel_val != "Desconocido"
                        else (
                            fase_info["nivel"]
                            if fase_info["nivel"] != "Desconocido"
                            else ginfo.get("nivel", "Desconocido")
                        )
                    )

                # H4 (SEMIFINAL/FINAL/…) e inferir_ronda tienen prioridad sobre ronda DDL (p. ej. Final)
                if ronda:
                    ronda_partido = ronda
                elif ronda_val is not None and str(ronda_val) not in (
                    "",
                    "Desconocida",
                ):
                    ronda_partido = str(ronda_val)
                elif fase_info.get("ronda") not in (None, "", "Desconocida"):
                    ronda_partido = str(fase_info["ronda"])
                else:
                    ronda_partido = "Desconocida"

                partido: Dict[str, Any] = {
                    "anio": year,
                    "categoria": cat_mapa,
                    "fase": fase_partido,
                    "ronda": ronda_partido,
                    "nivel": nivel_partido,
                    "zona": zona_partido,
                    "grupo": (
                        llave_val
                        if fase_actual in ["PLAYOFF", "FINAL FOUR"] and llave_val
                        else (
                            fase_info["grupo"]
                            if fase_info.get("grupo") not in [None, "Desconocido"]
                            else ginfo.get("grupo", "Desconocido")
                        )
                    ),
                    "jornada": jornada,
                    "fecha": fecha,
                    "local": normalizar_equipo(local_raw, self.equipos_map),
                    "ptsL": pts_local_raw,
                    "visitante": normalizar_equipo(visitante_raw, self.equipos_map),
                    "ptsV": pts_visitante_raw,
                }

                if partido["fase"] == "Playoff" and (
                    partido["categoria"] == "MINI" or partido["categoria"] == "PREMINI"
                ):
                    continue
                partidos.append(partido)

        return partidos
