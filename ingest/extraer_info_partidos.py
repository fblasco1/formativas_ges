from typing import Dict, List, Optional

"""
Compat/wrapper histórico.

Este módulo se mantiene por compatibilidad; la implementación core vive en
`ingest.ges.extractor` (y el shim `ingest.extractors`).
"""

from ingest.ges.extractor import Extractor, ExtractorFactory


def get_ids_categorias(
    id_competencia: int,
    extractor: Optional[Extractor] = None,
) -> Dict[str, str]:
    extractor = extractor or ExtractorFactory.create()
    return extractor.get_ids_categorias(id_competencia)


def get_info_partidos(
    id_categoria: int,
    fecha_inicio: str,
    fecha_fin: str,
    key: str = "c93924c3-1e13-4bf5-8f86-6386aeebba20",
    id_fase: int = -1,
    id_grupo: int = -1,
    extractor: Optional[Extractor] = None,
) -> List[Dict[str, str]]:
    extractor = extractor or ExtractorFactory.create()
    return extractor.get_info_partidos(id_categoria, fecha_inicio, fecha_fin, key, id_fase=id_fase, id_grupo=id_grupo)
