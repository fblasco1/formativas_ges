from typing import Dict, List, Optional

from ingest.extractors import Extractor, ExtractorFactory


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
    extractor: Optional[Extractor] = None,
) -> List[Dict[str, str]]:
    extractor = extractor or ExtractorFactory.create()
    return extractor.get_info_partidos(id_categoria, fecha_inicio, fecha_fin, key)
