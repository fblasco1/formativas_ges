"""Liga Federal Formativa U15 (Cadetes) — IDs GES y argentina.basketball."""

from __future__ import annotations

BASE_URL = "https://argentina.basketball"

# GES competicionescabb: LA LIGA FEDERAL CADETES (no confundir con Liga Federal mayores).
LFF_GES_COMPETENCIA_ID = 1619

# id_categoria en DDLCategorias / widget ``.../partidos/{id}/-3/7``.
LFF_GES_ID_CATEGORIA: dict[str, int] = {
    "masc": 4643,
    "fem": 4644,
}

# Torneo/detalle/comparativa en argentina.basketball (mismo número que GES id_categoria).
LFF_U15_TORNEO_COMP_CAT_ID: dict[str, int] = {
    "masc": 4643,
    "fem": 4644,
}

# CargarFixture en argentina.basketball apunta a Liga Federal MAYORES (no usar para Cadetes).
LFF_U15_FIXTURE_COMP_CAT_ID: dict[str, int] = {
    "masc": 5117,
    "fem": 5118,
}

LFF_TORNEO_TO_FIXTURE_COMP_CAT_ID: dict[int, int] = {
    4643: 5117,
    4644: 5118,
}

LFF_FIXTURE_TO_TORNEO_COMP_CAT_ID: dict[int, int] = {
    5117: 4643,
    5118: 4644,
}

LFF_U15_DETALLE_URL: dict[str, str] = {
    "masc": (
        f"{BASE_URL}/detalle-torneo/liga-federal-masculina/4643/"
        "liga-federal-formativa-cadetes-masculina"
    ),
    "fem": (
        f"{BASE_URL}/detalle-torneo/liga-federal-femenina/4644/"
        "liga-federal-formativa-cadetes-femenina"
    ),
}

LFF_DETALLE_TORNEO_PATH: dict[str, str] = {
    "masc": "detalle-torneo/liga-federal-masculina/",
    "fem": "detalle-torneo/liga-federal-femenina/",
}
