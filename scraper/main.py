# -*- coding: utf-8 -*-
"""
Scraper principal del ETL de FEBAMBA.
Extrae partidos de torneos formativos.
"""

import time
from bs4 import BeautifulSoup
from typing import List, Dict

from mapeos.loader import (
    cargar_mapeo_categorias,
    cargar_mapeo_equipos,
    normalizar_equipo,
)
from parsers.fases import parsear_fase
from parsers.grupos import parsear_grupo
from parsers.jornadas import parsear_jornada
from utils.logger import get_logger
from utils.requester import hacer_solicitud

logger = get_logger("FebambaScraper")


class FebambaScraper:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.categorias_map = cargar_mapeo_categorias()
        self.equipos_map = cargar_mapeo_equipos()
        self.partidos_acumulados = []

    def scrap_torneo(self, torneo_info: Dict) -> List[Dict]:
        """Scrapea todo un torneo: categorías, fases, grupos y partidos."""
        year = torneo_info["Anio"]
        comp_id = torneo_info["id"]
        url_inicial = torneo_info["url"]

        logger.info(
            f"\n--- Iniciando scraping para Torneo: {torneo_info['torneo']} ({year}) ---"
        )
        html = hacer_solicitud(url_inicial)
        if not html:
            logger.error(f"No se pudo obtener página inicial {url_inicial}")
            return []

        soup = BeautifulSoup(html, "html.parser")
        categorias_select = soup.find("select", {"name": "DDLCategorias"})
        if not categorias_select:
            logger.warning(f"No se encontró selector de categorías en {url_inicial}")
            return []

        for option in categorias_select.find_all("option"):
            cat_web = option.text.strip()
            cat_id = option.get("value")
            if not cat_id or cat_id == "0" or "Seleccionar" in cat_web:
                continue

            if cat_web == "Mosquitos":
                logger.info("Saltando categoría: Mosquitos")
                continue

            cat_mapa = self.categorias_map.get(cat_web, cat_web)
            logger.info(
                f"Procesando Categoría: {cat_web} ➔ Mapeada como {cat_mapa}, ID: {cat_id}"
            )

            partidos_categoria = self._scrap_fases_categoria(
                year, cat_mapa, url_inicial, cat_id
            )
            self.partidos_acumulados.extend(partidos_categoria)

            logger.info(f"Partidos acumulados: {len(self.partidos_acumulados)}")
            time.sleep(2)

        return self.partidos_acumulados

    def _scrap_fases_categoria(self, year, cat_mapa, url_torneo, cat_id) -> List[Dict]:
        """Scrapea todas las fases de una categoría."""
        url_fases = f"{url_torneo}&categoria={cat_id}"
        html = hacer_solicitud(url_fases)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        fases_select = soup.find("select", {"name": "DDLFases"})
        if not fases_select:
            logger.error(f"No se encontró DDLFases en {url_fases}")
            return []

        partidos_categoria = []

        for option in fases_select.find_all("option"):
            fase_id = option.get("value")
            fase_text = option.text.strip()

            if not fase_id or fase_id == "0" or "Seleccionar" in fase_text:
                continue

            fase_info = parsear_fase(year, fase_text)
            partidos_fase = self._scrap_grupos_fase(
                year, cat_mapa, url_fases, fase_info, fase_id
            )
            partidos_categoria.extend(partidos_fase)

            time.sleep(1)

        return partidos_categoria

    def _scrap_grupos_fase(
        self, year, cat_mapa, url_fase, fase_info, fase_id
    ) -> List[Dict]:
        """Scrapea todos los grupos de una fase."""
        url_grupos = f"{url_fase}&fase={fase_id}"
        html = hacer_solicitud(url_grupos)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        grupos_select = soup.find("select", {"name": "DDLGrupos"})

        partidos_fase = []

        if not grupos_select:
            # Si no hay grupos, scrapeamos directamente
            partidos_grupo = self._scrap_partidos_grupo(
                url_grupos, year, cat_mapa, fase_info, None
            )
            partidos_fase.extend(partidos_grupo)
        else:
            for option in grupos_select.find_all("option"):
                grupo_id = option.get("value")
                grupo_text = option.text.strip()

                if not grupo_id or grupo_id == "0" or "Seleccionar" in grupo_text:
                    continue

                grupo_info = parsear_grupo(year, fase_info.get("fase", ""), grupo_text)
                url_grupo = f"{url_grupos}&grupo={grupo_id}"

                partidos_grupo = self._scrap_partidos_grupo(
                    url_grupo, year, cat_mapa, fase_info, grupo_info
                )
                partidos_fase.extend(partidos_grupo)

                time.sleep(0.5)

        return partidos_fase

    def _scrap_partidos_grupo(
        self, url_grupo, year, cat_mapa, fase_info, grupo_info
    ) -> List[Dict]:
        """Scrapea partidos de un grupo específico."""
        html = hacer_solicitud(url_grupo)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        tab_pane = soup.find(
            "div", id="ctl00_ContentPlaceHolder1_UpdatePanel1"
        ) or soup.find("div", id="calendario")

        if not tab_pane:
            logger.warning(f"No se encontró div de partidos en {url_grupo}")
            return []

        tables = tab_pane.find_all("table", class_="tabla") or tab_pane.find_all(
            "table"
        )
        if not tables:
            logger.warning(f"No se encontraron tablas de partidos en {url_grupo}")
            return []

        partidos = []

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

                partido = {
                    "anio": year,
                    "categoria": cat_mapa,
                    "fase": fase_info.get("fase"),
                    "ronda": fase_info.get("ronda"),
                    "nivel": (
                        grupo_info.get("nivel")
                        if grupo_info
                        else fase_info.get("nivel")
                    ),
                    "zona": (
                        grupo_info.get("zona") if grupo_info else fase_info.get("zona")
                    ),
                    "grupo": grupo_info.get("grupo") if grupo_info else "UNICO",
                    "jornada": jornada,
                    "fecha": fecha,
                    "local": normalizar_equipo(local_raw, self.equipos_map),
                    "ptsL": pts_local_raw,
                    "visitante": normalizar_equipo(visitante_raw, self.equipos_map),
                    "ptsV": pts_visitante_raw,
                }

                partidos.append(partido)

        return partidos
