# -*- coding: utf-8 -*-
"""
Parseador de Jornadas para partidos de torneos FEBAMBA.
Interpreta el título de jornada para extraer ronda, jornada y fecha.
"""

import re
from typing import Tuple


def parsear_jornada(texto_jornada: str) -> Tuple[str, str, str]:
    """
    Parseo inteligente del texto de jornada.

    Args:
        texto_jornada (str): Texto completo del H4 (ej: 'SEMIFINAL Jornada 1 - 10/12/2023').

    Returns:
        Tuple[str, str, str]: (ronda, jornada, fecha)
            - ronda: 'CUARTOS DE FINAL', 'SEMIFINAL', 'FINAL' o '' si no hay ronda explícita.
            - jornada: número de jornada como string ('1', '2', etc.) o '' si no encontrado.
            - fecha: fecha en formato texto (ej: '30/06/2019') o '' si no encontrado.
    """
    texto = texto_jornada.strip().upper()

    ronda = ""
    jornada = ""
    fecha = ""

    if "-" in texto:
        partes = texto.split("-", 1)
        info_jornada = partes[0].strip()
        fecha = partes[1].strip()
    else:
        info_jornada = texto
        fecha = ""

    # Buscar ronda si está
    ronda_search = re.search(r"(CUARTOS DE FINAL|SEMIFINAL|FINAL)", info_jornada)
    if ronda_search:
        ronda = ronda_search.group(1)

    # Buscar jornada
    jornada_search = re.search(r"JORNADA\s*(\d+)", info_jornada)
    if jornada_search:
        jornada = jornada_search.group(1)

    return ronda, jornada, fecha
