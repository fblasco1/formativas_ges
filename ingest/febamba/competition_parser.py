# -*- coding: utf-8 -*-
"""
Página de competencia GES (solo ``competicionescabb.gesdeportiva.es``).
Categorías (DDLCategorias) y combos fase/grupo — sin widgetscab.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from ingest.ges.extractor import GesDeportivaExtractor


class CompetitionParser:
    """Envoltorio explícito sobre el extractor GES para la página de competencia."""

    def __init__(self, ges: GesDeportivaExtractor) -> None:
        self._ges = ges

    def categorias(self, id_competencia: int) -> Dict[str, str]:
        return self._ges.get_ids_categorias(id_competencia)

    def fases_y_grupos(
        self, id_competencia: int, id_categoria: Optional[int] = None
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        return self._ges.get_ids_fases_grupos(id_competencia, id_categoria=id_categoria)
