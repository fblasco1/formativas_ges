# -*- coding: utf-8 -*-
"""Pesos baseline GES y renivelación."""

from __future__ import annotations

from analisis.Ranking.seasons import anos_con_patron_ronda_clasico, peso_anio_configurado


def peso_anio(anio) -> float:
    return peso_anio_configurado(anio)


def peso_fase_baseline(fase: str, nivel: str) -> float:
    fase_u = str(fase).upper()
    nivel_s = str(nivel)
    if "FINAL FOUR" in fase_u:
        return 1.0
    if "PLAYOFF" in fase_u:
        if nivel_s in ("INTERCONFERENCIA", "INTERCONFERENCIA A", "INTERCONFERENCIA B"):
            return 1.0
        return 0.75
    if "FASE REGULAR" in fase_u:
        return 0.65
    return 1.0


def peso_ronda_baseline(ronda: str, anio: int) -> float:
    ronda_u = str(ronda).upper()
    if ronda_u == "1RA FASE":
        return 1.0
    if ronda_u == "2DA FASE":
        return 2.0 if anos_con_patron_ronda_clasico(anio) else 1.0
    if ronda_u == "3RA FASE":
        return 1.0 if anos_con_patron_ronda_clasico(anio) else 2.0
    if ronda_u == "OCTAVOS DE FINAL":
        return 3.0
    if ronda_u == "CUARTOS DE FINAL":
        return 4.0
    if ronda_u in ("SEMIFINAL", "FINAL"):
        return 6.0
    return 1.0


def peso_nivel_baseline(nivel: str) -> float:
    nivel_u = str(nivel).upper()
    if nivel_u in ("INTERCONFERENCIA A", "INTERCONFERENCIA"):
        return 2.0
    if "INTERCONFERENCIA B" in nivel_u:
        return 1.5
    if nivel_u == "1":
        return 1.0
    if nivel_u == "2":
        return 0.85
    if nivel_u == "3":
        return 0.75
    return 1.0


def peso_etapa_renivelacion(fase: str, ronda: str, anio: int) -> float:
    """Matriz renivelación: Regular=1 … Final/Final Four=6."""
    anio_i = int(anio)
    ronda_u = str(ronda).upper()
    fase_u = str(fase).upper()

    if anio_i in (2025, 2026) and ronda_u == "1RA FASE":
        return 0.5

    if "FINAL FOUR" in fase_u or ronda_u == "FINAL":
        return 6.0
    if ronda_u == "SEMIFINAL":
        return 4.0
    if ronda_u == "CUARTOS DE FINAL":
        return 3.0
    if ronda_u == "OCTAVOS DE FINAL":
        return 2.0
    return 1.0


def peso_nivel_renivelacion(nivel: str, ronda: str, anio: int) -> float:
    anio_i = int(anio)
    ronda_u = str(ronda).upper()
    if anio_i in (2025, 2026) and ronda_u == "1RA FASE":
        return 1.0

    nivel_u = str(nivel).upper()
    if nivel_u in ("INTERCONFERENCIA A", "INTERCONFERENCIA"):
        return 6.0
    if "INTERCONFERENCIA B" in nivel_u:
        return 3.0
    if nivel_u == "1":
        return 2.0
    if nivel_u == "2":
        return 0.5
    if nivel_u == "3":
        return 0.333
    return 1.0
