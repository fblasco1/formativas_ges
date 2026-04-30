# -*- coding: utf-8 -*-
"""
Extractor temporada >= 2026: calendario vía ``argentina.basketball`` (ver ``argentina_pipeline``);
boxscore vía ``/liga-federal/partido/estadisticas/`` sin ``widgetscab``.
La página de competencia GES (categorías / fases) sigue en la clase base.
"""

from __future__ import annotations

from typing import List, Optional

from ingest.febamba.argentina_pipeline import ges_shape_from_argentina_row
from ingest.febamba.fixture_parser_arg import ArgentinaFixtureParser
from ingest.febamba.runtime_ctx import get_comp_cat_argentina_id
from ingest.febamba.stats_parser_arg import ArgentinaStatsParser
from ingest.ges.extractor import GesDeportivaExtractor
from ingest.ges.partido_ids import es_id_sintetico
from ingest.http_client import HttpClient


class FebambaDualSourceExtractor(GesDeportivaExtractor):
    """Mantiene scraping de ``competicion.aspx``; reemplaza widget de calendario/acta 2026+."""

    def __init__(self, client: HttpClient, temporada: str) -> None:
        super().__init__(client)
        self._stats = ArgentinaStatsParser(session=client._session, timeout_s=60)

    def get_info_partidos(
        self,
        id_categoria: int,
        fecha_inicio: str,
        fecha_fin: str,
        key: str,
        id_fase: int = -1,
        id_grupo: int = -1,
    ) -> List[dict[str, str]]:
        """
        Listado desde argentina.basketball (sin widgetscab).
        ``key`` se ignora aquí; sirve para scripts que reutilizan la misma firma.
        """
        comp_cat_id = get_comp_cat_argentina_id(int(id_categoria))
        parser = ArgentinaFixtureParser(session=self._client._session, timeout_s=60)
        raw = parser.fetch_all_chunked(comp_cat_id, fecha_inicio, fecha_fin)
        out: List[dict[str, str]] = []
        for row in raw:
            if not (row.get("id_partido_token") or "").strip():
                continue
            out.append(
                ges_shape_from_argentina_row(
                    row,
                    id_fase=str(id_fase),
                    id_grupo=str(id_grupo),
                    torneo_ctx={},
                )
            )
        return out

    def get_boxscore(self, id_partido: str) -> Optional[dict[str, object]]:
        if not (id_partido or "").strip() or es_id_sintetico(id_partido):
            return None
        return self._stats.fetch_boxscore_payload(id_partido.strip())
