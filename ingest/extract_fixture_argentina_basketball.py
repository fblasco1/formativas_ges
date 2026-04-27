"""
Compat/shim: módulo histórico `ingest.extract_fixture_argentina_basketball`.

La implementación se movió a `ingest.argbasket.fixture`.
"""

from ingest.argbasket.fixture import (  # noqa: F401
    BASE_URL_DEFAULT,
    DEFAULT_FIELDNAMES,
    extraer_hora_inicio_fin_desde_en_vivo_html,
    fetch_cargar_fixture_html,
    fetch_partido_en_vivo_html,
    get_fixture_partidos_argentina_basketball,
    parse_tabla_calendarios,
    write_csv,
)

__all__ = [
    "BASE_URL_DEFAULT",
    "DEFAULT_FIELDNAMES",
    "fetch_cargar_fixture_html",
    "fetch_partido_en_vivo_html",
    "extraer_hora_inicio_fin_desde_en_vivo_html",
    "parse_tabla_calendarios",
    "get_fixture_partidos_argentina_basketball",
    "write_csv",
]

