# -*- coding: utf-8 -*-
"""
Parseador de Rondas para torneos FEBAMBA.
Deducción de rondas en Playoffs y Final Four.
"""

import re
from typing import Any, Dict, Optional

from mapeos.loader import normalizar_equipo


def _collapse_grupo_ddl(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().upper())


_NORTE_AB_OESTE_AB_DDL: frozenset[str] = frozenset(
    ("NORTE/AB-OESTE AB", "NORTE AB/OESTE AB")
)


def _es_norte_ab_oeste_ab_2025(fase_ddl: str | None, grupo_ddl: str | None) -> bool:
    """True si la fase o el grupo DDL es el cruce NORTE AB / OESTE AB (2025)."""
    fd = _collapse_grupo_ddl(fase_ddl) if fase_ddl else ""
    gd = _collapse_grupo_ddl(grupo_ddl) if grupo_ddl else ""
    return fd in _NORTE_AB_OESTE_AB_DDL or gd in _NORTE_AB_OESTE_AB_DDL


def _zona_final_four_2_playoff_2025(llave_u: str) -> str | None:
    """Zona por llave en cruce NORTE AB vs OESTE AB (2025)."""
    u = llave_u.upper()
    if "COLEGIALES" in u and "LAS HERAS" in u:
        return "NORTE"
    if "NOLTING" in u and "CEPA" in u:
        return "OESTE"
    return None


def inferir_ronda(
    anio: int,
    categoria: str,
    nivel: str,
    zona: str,
    jornada: str,
    fase: str,
    local: str,
    visitante: str,
    equipos_map,
    grupo_ddl: str | None = None,
    fase_ddl: str | None = None,
) -> Optional[Dict[str, Any]]:
    """
    Deducción de ronda, nivel y llave para partidos de Playoffs y Final Four.
    Devuelve un dict con las claves: 'ronda', 'nivel' y 'llave'.
    """
    llave = f"{normalizar_equipo(local, equipos_map)}-{normalizar_equipo(visitante, equipos_map)}"
    if fase.upper() == "PLAYOFF":
        if anio == 2025 and _es_norte_ab_oeste_ab_2025(fase_ddl, grupo_ddl):
            ronda_map = {1: "SEMIFINAL", 2: "FINAL"}
            ronda_ff = (
                ronda_map.get(int(jornada))
                if jornada.isdigit()
                else None
            )
            zona_ff = _zona_final_four_2_playoff_2025(llave)
            out: Dict[str, Any] = {
                "ronda": ronda_ff,
                "nivel": nivel,
                "llave": llave,
            }
            if zona_ff:
                out["zona"] = zona_ff
            return out
        if anio == 2025:
            # Mismo criterio que 2023/2024: llave local-visitante para rellenar grupo en CSV.
            ronda = inferir_ronda_generica_playoff(jornada)
            return {"ronda": ronda, "nivel": nivel, "llave": llave}
        if anio == 2022:
            ronda = inferir_ronda_2022_playoff(categoria, nivel, zona, jornada)
            return {"ronda": ronda, "nivel": nivel, "llave": llave}
        if anio in [2023, 2024]:
            ronda = inferir_ronda_generica_playoff(jornada)
            return {"ronda": ronda, "nivel": nivel, "llave": llave}
        if anio == 2019:
            # Solo configurar la llave, la ronda ya se parseó en fase_info
            return {"llave": llave, "nivel": nivel}
    elif fase.upper() == "CUARTOS NIVEL 3" and anio == 2022:
        ronda = inferir_ronda_2022_cuartos_nivel3(jornada)
        return {"ronda": ronda, "nivel": nivel, "llave": llave}
    elif fase.upper() == "FINAL FOUR":
        if anio == 2022:
            return inferir_ronda_2022_final_four(llave, categoria, equipos_map)
        if anio in [2019, 2023, 2024, 2025]:
            ronda = inferir_ronda_generica_final_four(llave, categoria, jornada, equipos_map)
            return {"ronda": ronda, "nivel": None, "llave": llave}
    return None


def inferir_ronda_2022_playoff(
    categoria: str, nivel: str, zona: str, jornada: str
) -> Optional[str]:
    """
    Deducción de ronda para Playoff 2022 según categoría, nivel, zona y jornada.
    """
    if not jornada.isdigit():
        return None
    j = int(jornada)
    c, n, z = categoria.upper(), nivel.upper(), zona.upper()

    if c == "JUVENILES":
        if n in ["INTERCONFERENCIA", "1"]:
            return _map_ronda(j, [1, 2, 3, 4])
        if n == "2":
            return (
                _map_ronda(j, [1, (2, 3), 4, 5])
                if z == "OESTE"
                else _map_ronda(j, [1, 2, 3, 5])
            )
        if n == "3":
            return (
                _map_ronda(j, [None, 2, 3, 4])
                if z == "CENTRO"
                else _map_ronda(j, [1, 2])
            )

    if c == "CADETES":
        if n in ["INTERCONFERENCIA", "1", "2"]:
            return _map_ronda(j, [1, 2, 3, 4])
        if n == "3":
            return (
                _map_ronda(j, [None, 2, 3, 4])
                if z == "CENTRO"
                else _map_ronda(j, [1, 2])
            )

    if c == "INFANTILES":
        if n in ["INTERCONFERENCIA", "1", "2"]:
            return _map_ronda(j, [1, 2, 3, 4])
        if n == "3" and z == "SUR":
            return _map_ronda(j, [1, 2])

    return None


def inferir_ronda_2022_cuartos_nivel3(jornada: str) -> Optional[str]:
    """
    Deducción de ronda para cuartos nivel 3 en 2022.
    """
    if not jornada.isdigit():
        return None
    j = int(jornada)
    return {1: "CUARTOS DE FINAL", 2: "SEMIFINAL", 3: "FINAL"}.get(j)


def inferir_ronda_2022_final_four(
    llave: str, categoria: str, equipos_map
) -> Optional[Dict]:
    """
    Busca la llave en todos los niveles de la categoría para FINAL FOUR 2022.
    Devuelve dict con 'nivel', 'ronda' y 'llave'.
    """
    semifinales_raw = {
        "JUVENILES": [
            ("2", "COOPERARIOS DE QUILMES-EL TALAR"),
            ("2", "VICTORIA-ARGENTINOS DE CASTELAR B"),
            ("1", "SAN LORENZO AZUL-RACING CLUB"),
            ("1", "C S D PRESIDENTE DERQUI-SP.ESCOBAR"),
        ],
        "CADETES": [
            ("2", "SOCIEDAD HEBRAICA ARGENTINA-ARGENTINOS DE CASTELAR B"),
            ("2", "17 DE AGOSTO-CLUB SOCIAL Y ATLETICO EZEIZA"),
            ("1", "CAZA Y PESCA A-C S D PRESIDENTE DERQUI"),
            ("1", "PINOCHO-CAÑUELAS FC - Sub17"),
        ],
        "IFNATILES": [
            ("2", "17 DE AGOSTO-LOS ANDES"),
            ("2", "SAN MIGUEL-CLUB 3 DE FEBRERO AZUL"),
        ],
        "INFANTILES": [
            ("1", "IMPERIO BLANCO-CLUB GIMNASIA Y ESGRIMA DE LA PLATA"),
            ("1", "C S D PRESIDENTE DERQUI-CAZA Y PESCA A"),
        ],
        "PREINFANTILES": [
            ("2", "U GRAL.ARMENIA-CLUB SOCIAL ALEJANDRO KORN"),
            ("2", "SAN MIGUEL-VICTORIA"),
            ("1", "QUILMES A.C-COMUNICACIONES"),
            ("1", "CLUB 3 DE FEBRERO BLANCO-GEI AZUL"),
        ],
    }
    finales_raw = {
        "JUVENILES": [
            ("2", "EL TALAR-VICTORIA"),
            ("1", "SAN LORENZO AZUL-SP.ESCOBAR"),
        ],
        "CADETES": [
            ("2", "SOCIEDAD HEBRAICA ARGENTINA-CLUB SOCIAL Y ATLETICO EZEIZA"),
            ("1", "PINOCHO-CAZA Y PESCA A"),
        ],
        "INFANTILES": [
            ("2", "SAN MIGUEL-17 DE AGOSTO"),
            ("1", "CLUB GIMNASIA Y ESGRIMA DE LA PLATA-CAZA Y PESCA A"),
        ],
        "PREINFANTILES": [
            ("2", "VICTORIA-CLUB SOCIAL ALEJANDRO KORN"),
            ("1", "QUILMES A.C-GEI AZUL"),
        ],
    }
    c = categoria.upper()
    # Buscar en semifinales
    for n, a_b in semifinales_raw.get(c, []):
        a, b = a_b.split("-", 1)
        llave_norm = f"{normalizar_equipo(a, equipos_map)}-{normalizar_equipo(b, equipos_map)}"
        if llave == llave_norm:
            return {"nivel": n, "ronda": "SEMIFINAL", "llave": llave}
    # Buscar en finales si no se encontró en semifinales
    for n, a_b in finales_raw.get(c, []):
        a, b = a_b.split("-", 1)
        llave_norm = f"{normalizar_equipo(a, equipos_map)}-{normalizar_equipo(b, equipos_map)}"
        if llave == llave_norm:
            return {"nivel": n, "ronda": "FINAL", "llave": llave}
    return None


def inferir_ronda_generica_playoff(jornada: str) -> Optional[str]:
    """
    Deducción genérica de ronda para playoff según jornada.
    """
    if not jornada.isdigit():
        return None
    return {1: "CUARTOS DE FINAL", 2: "SEMIFINAL", 3: "FINAL"}.get(int(jornada))


def inferir_ronda_generica_final_four(
    llave: str, categoria: str, jornada: str, equipos_map
) -> Optional[str]:
    """
    Deducción genérica de ronda para Final Four según llave y jornada.
    """
    if not jornada.isdigit():
        return None
    # No se usa nivel, se busca en todos los niveles de la categoría
    semifinales_raw = {
        "JUVENILES": [
            "COOPERADORES DE QUILMES-EL TALAR",
            "VICTORIA-ARGENTINOS DE CASTELAR B",
            "SAN LORENZO AZUL-RACING CLUB",
            "C S D PRESIDENTE DERQUI-SP.ESCOBAR",
        ],
        "CADETES": [
            "SOCIEDAD HEBRAICA ARGENTINA-ARGENTINOS DE CASTELAR B",
            "17 DE AGOSTO-CLUB SOCIAL Y ATLETICO EZEIZA",
            "CAZA Y PESCA A-C S D PRESIDENTE DERQUI",
            "PINOCHO-CAÑUELAS FC - Sub17",
        ],
        "IFNATILES": [
            "17 DE AGOSTO-LOS ANDES",
            "SAN MIGUEL-CLUB 3 DE FEBRERO AZUL",
        ],
        "INFANTILES": [
            "IMPERIO BLANCO-CLUB GIMNASIA Y ESGRIMA DE LA PLATA",
            "C S D PRESIDENTE DERQUI-CAZA Y PESCA A",
        ],
        "PREINFANTILES": [
            "U GRAL.ARMENIA-CLUB SOCIAL ALEJANDRO KORN",
            "SAN MIGUEL-VICTORIA",
            "QUILMES A.C-COMUNICACIONES",
            "CLUB 3 DE FEBRERO BLANCO-GEI AZUL",
        ],
    }
    finales_raw = {
        "JUVENILES": [
            "EL TALAR-VICTORIA",
            "SAN LORENZO AZUL-SP.ESCOBAR",
        ],
        "CADETES": [
            "SOCIEDAD HEBRAICA ARGENTINA-CLUB SOCIAL Y ATLETICO EZEIZA",
            "PINOCHO-CAZA Y PESCA A",
        ],
        "INFANTILES": [
            "SAN MIGUEL-17 DE AGOSTO",
            "CLUB GIMNASIA Y ESGRIMA DE LA PLATA-CAZA Y PESCA A",
        ],
        "PREINFANTILES": [
            "VICTORIA-CLUB SOCIAL ALEJANDRO KORN",
            "QUILMES A.C-GEI AZUL",
        ],
    }
    c = categoria.upper()
    semifinales = {
        f"{normalizar_equipo(a, equipos_map)}-{normalizar_equipo(b, equipos_map)}"
        for a_b in semifinales_raw.get(c, [])
        for a, b in [a_b.split("-", 1)]
    }
    finales = {
        f"{normalizar_equipo(a, equipos_map)}-{normalizar_equipo(b, equipos_map)}"
        for a_b in finales_raw.get(c, [])
        for a, b in [a_b.split("-", 1)]
    }
    if llave in semifinales:
        return "SEMIFINAL"
    if llave in finales:
        return "FINAL"
    return {1: "SEMIFINAL", 2: "FINAL"}.get(int(jornada))


def _map_ronda(jornada: int, estructura: list) -> Optional[str]:
    """
    Mapea el número de jornada a la ronda correspondiente según la estructura.
    """
    ronda_map = {
        1: "OCTAVOS DE FINAL",
        2: "CUARTOS DE FINAL",
        3: "SEMIFINAL",
        4: "FINAL",
    }
    for idx, val in enumerate(estructura, start=1):
        if isinstance(val, tuple) and jornada in val:
            return ronda_map[idx]
        elif jornada == val:
            return ronda_map[idx]
    return None
