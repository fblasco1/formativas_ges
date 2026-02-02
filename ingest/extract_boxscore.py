from typing import Dict, List, Optional, Tuple

from bs4.element import Tag

from ingest.extractors import Extractor, ExtractorFactory, GesDeportivaExtractor


def clean_shot_value(td: Tag) -> str:
    return GesDeportivaExtractor.clean_shot_value(td)


def parse_table(table: Tag) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    return GesDeportivaExtractor.parse_table(table)


def get_boxscore(
    id_partido: str,
    extractor: Optional[Extractor] = None,
) -> Optional[Dict[str, object]]:
    extractor = extractor or ExtractorFactory.create()
    return extractor.get_boxscore(id_partido)
