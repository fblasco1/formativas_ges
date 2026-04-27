"""
Compat/shim: módulo histórico `ingest.pipeline_fixture_argentina_basketball`.

La implementación se movió a `ingest.argbasket.pipeline_fixture`.
"""

from ingest.argbasket.pipeline_fixture import (  # noqa: F401
    COMP_CAT_ID_A_CATEGORIA,
    CONSOLIDADO_FIELDNAMES,
    generar_fixture_consolidado,
    write_csv,
)

__all__ = [
    "COMP_CAT_ID_A_CATEGORIA",
    "CONSOLIDADO_FIELDNAMES",
    "generar_fixture_consolidado",
    "write_csv",
]

