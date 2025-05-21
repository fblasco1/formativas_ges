# -*- coding: utf-8 -*-
"""
Parseador de Rondas para torneos FEBAMBA.
Deducción de rondas en Playoffs y Final Four.
"""

from typing import Optional
from mapeos.loader import normalizar_equipo


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
) -> Optional[str]:
    """
    Deduce la ronda en Playoffs o Final Four, según año de torneo.
    """
    if fase.upper() == "PLAYOFF":
        if anio == 2022:
            return inferir_ronda_2022_playoff(categoria, nivel, zona, jornada)
        if anio in [2023, 2024]:
            return inferir_ronda_generica_playoff(jornada)

    elif fase.upper() == "CUARTOS NIVEL 3" and anio == 2022:
        return inferir_ronda_2022_cuartos_nivel3(jornada)

    elif fase.upper() == "FINAL FOUR":
        if anio == 2022:
            return inferir_ronda_2022_final_four(
                local, visitante, categoria, nivel, equipos_map
            )
        if anio in [2023, 2024]:
            return inferir_ronda_generica_final_four(
                local, visitante, categoria, nivel, jornada, equipos_map
            )

    return None


def inferir_ronda_2022_playoff(
    categoria: str, nivel: str, zona: str, jornada: str
) -> Optional[str]:
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
    if not jornada.isdigit():
        return None
    j = int(jornada)
    return {1: "CUARTOS DE FINAL", 2: "SEMIFINAL", 3: "FINAL"}.get(j)


def inferir_ronda_2022_final_four(
    local: str, visitante: str, categoria: str, nivel: str, equipos_map
) -> Optional[str]:
    llave = f"{normalizar_equipo(local, equipos_map)}-{normalizar_equipo(visitante, equipos_map)}"
    return (
        "SEMIFINAL"
        if llave in _final_four_semifinales(categoria, nivel, equipos_map)
        else (
            "FINAL"
            if llave in _final_four_finales(categoria, nivel, equipos_map)
            else None
        )
    )


def inferir_ronda_generica_playoff(jornada: str) -> Optional[str]:
    if not jornada.isdigit():
        return None
    return {1: "CUARTOS DE FINAL", 2: "SEMIFINAL", 3: "FINAL"}.get(int(jornada))


def inferir_ronda_generica_final_four(
    local: str, visitante: str, categoria: str, nivel: str, jornada: str, equipos_map
) -> Optional[str]:
    if not jornada.isdigit():
        return None
    llave = f"{normalizar_equipo(local, equipos_map)}-{normalizar_equipo(visitante, equipos_map)}"
    if llave in _final_four_semifinales(categoria, nivel, equipos_map):
        return "SEMIFINAL"
    if llave in _final_four_finales(categoria, nivel, equipos_map):
        return "FINAL"
    return {1: "SEMIFINAL", 2: "FINAL"}.get(int(jornada))


def _map_ronda(jornada: int, estructura: list) -> Optional[str]:
    ronda_map = {
        1: "OCTAVOS DE FINAL",
        2: "CUARTOS DE FINAL",
        3: "SEMIFINAL",
        4: "FINAL",
        5: "FINAL",
    }
    for idx, val in enumerate(estructura, start=1):
        if isinstance(val, tuple) and jornada in val:
            return ronda_map[idx]
        elif jornada == val:
            return ronda_map[idx]
    return None


def _final_four_semifinales(categoria: str, nivel: str, equipos_map) -> set:
    c, n = categoria.upper(), nivel.upper()
    raw = {
        ("JUVENILES", "2"): [
            "COOPERARIOS DE QUILMES-EL TALAR",
            "VICTORIA-ARGENTINOS DE CASTELAR B",
        ],
        ("JUVENILES", "1"): [
            "SAN LORENZO AZUL-RACING CLUB",
            "C S D PRESIDENTE DERQUI-SP.ESCOBAR",
        ],
        ("CADETES", "2"): [
            "SOCIEDAD HEBRAICA ARGENTINA-ARGENTINOS DE CASTELAR B",
            "17 DE AGOSTO-CLUB SOCIAL Y ATLETICO EZEIZA",
        ],
        ("CADETES", "1"): [
            "CAZA Y PESCA A-C S D PRESIDENTE DERQUI",
            "PINOCHO-CAÑUELAS FC - Sub17",
        ],
        ("IFNATILES", "2"): [
            "17 DE AGOSTO-LOS ANDES",
            "SAN MIGUEL-CLUB 3 DE FEBRERO AZUL",
        ],
        ("INFANTILES", "1"): [
            "IMPERIO BLANCO-CLUB GIMNASIA Y ESGRIMA DE LA PLATA",
            "C S D PRESIDENTE DERQUI-CAZA Y PESCA A",
        ],
        ("PREINFANTILES", "2"): [
            "U GRAL.ARMENIA-CLUB SOCIAL ALEJANDRO KORN",
            "SAN MIGUEL-VICTORIA",
        ],
        ("PREINFANTILES", "1"): [
            "QUILMES A.C-COMUNICACIONES",
            "CLUB 3 DE FEBRERO BLANCO-GEI AZUL",
        ],
    }
    return {
        f"{normalizar_equipo(a, equipos_map)}-{normalizar_equipo(b, equipos_map)}"
        for a_b in raw.get((c, n), [])
        for a, b in [a_b.split("-")]
    }


def _final_four_finales(categoria: str, nivel: str, equipos_map) -> set:
    c, n = categoria.upper(), nivel.upper()
    raw = {
        ("JUVENILES", "2"): ["EL TALAR-VICTORIA"],
        ("JUVENILES", "1"): ["SAN LORENZO AZUL-SP.ESCOBAR"],
        ("CADETES", "2"): ["SOCIEDAD HEBRAICA ARGENTINA-CLUB SOCIAL Y ATLETICO EZEIZA"],
        ("CADETES", "1"): ["PINOCHO-CAZA Y PESCA A"],
        ("INFANTILES", "2"): ["SAN MIGUEL-17 DE AGOSTO"],
        ("INFANTILES", "1"): ["CLUB GIMNASIA Y ESGRIMA DE LA PLATA-CAZA Y PESCA A"],
        ("PREINFANTILES", "2"): ["VICTORIA-CLUB SOCIAL ALEJANDRO KORN"],
        ("PREINFANTILES", "1"): ["QUILMES A.C-GEI AZUL"],
    }
    return {
        f"{normalizar_equipo(a, equipos_map)}-{normalizar_equipo(b, equipos_map)}"
        for a_b in raw.get((c, n), [])
        for a, b in [a_b.split("-")]
    }
