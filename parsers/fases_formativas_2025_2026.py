# -*- coding: utf-8 -*-
"""Reglas de parseo de fase para formativas 2025 y 2026 (GES)."""

from __future__ import annotations

import re
from typing import Dict, Optional

ZONAS = ("CENTRO", "NORTE", "SUR", "OESTE")


def debe_omitir_fase(fase_text: str) -> bool:
    """Fases que no deben ingresar al dataset."""
    u = fase_text.upper().strip()
    if "CLASIFICACION LFF" in u:
        return True
    # Liga Próximo: encuentros calendario, no formativas
    if "ENCUENTRO" in u and ("1ER" in u or "2DO" in u or "2º" in u or "1°" in u):
        return True
    return False


def _base() -> Dict[str, str]:
    return {
        "fase": "Desconocida",
        "ronda": "Desconocida",
        "nivel": "Desconocido",
        "zona": "Desconocida",
        "grupo": "Desconocido",
    }


def parsear_fase_2025(fase_text: str) -> Dict[str, str]:
    u = fase_text.upper().strip()
    out = _base()

    if "1ER ETAPA" in u and "LFF" in u:
        out.update(fase="Fase Regular", ronda="Copa Febamba", nivel="NIVELACION")
        return out

    if "2DO SEMESTRE" in u or "2º SEMESTRE" in u:
        out.update(fase="Fase Regular", ronda="2da Fase", nivel="Desconocido")
        return out

    m_ff = re.search(r"FINAL\s+FOUR\s*(\d)", u)
    if m_ff:
        out.update(fase="Final Four", ronda="Desconocida", nivel=m_ff.group(1))
        return out

    if u == "INTERCONFERENCIAS" or (
        "INTERCONFERENCIAS" in u and "INTERCONFERENCIA A" not in u and "INTERCONFERENCIA B" not in u
    ):
        out.update(fase="Playoff", ronda="Final", nivel="INTERCONFERENCIA", zona="INTERCONFERENCIA")
        return out

    if "INTERCONFERENCIA A" in u:
        out.update(fase="Playoff", nivel="INTERCONFERENCIA A", zona="INTERCONFERENCIA")
        return out

    if "INTERCONFERENCIA B" in u:
        out.update(fase="Playoff", nivel="INTERCONFERENCIA B", zona="INTERCONFERENCIA")
        return out

    if "PLAY OFF INTERCONFERENCIA" in u or "PLAYOFF INTERCONFERENCIA" in u:
        nivel = "INTERCONFERENCIA A" if " A" in u or u.endswith(" A") else "INTERCONFERENCIA B" if " B" in u else "INTERCONFERENCIA"
        out.update(fase="Playoff", nivel=nivel, zona="INTERCONFERENCIA")
        return out

    if "TRIANGULAR FINAL" in u:
        out.update(fase="Playoff", ronda="Triangular Final", nivel="Desconocido", zona="SUR")
        return out

    # NIVEL NORTE 2A, NIVEL SUR 2B, NIVEL 2 NORTE A, etc.
    m_nz = re.search(
        r"NIVEL\s+(?:(NORTE|SUR|OESTE|CENTRO)\s+)?(\d)\s*([ABC])?",
        u,
    )
    if m_nz and "FINAL FOUR" not in u:
        zona_f = m_nz.group(1) or ""
        nivel_f = m_nz.group(2)
        out.update(fase="Playoff", ronda="Desconocida", nivel=nivel_f)
        if zona_f:
            out["zona"] = zona_f
        return out

    m_nivel = re.search(r"^NIVEL\s+(\d)\s*$", u) or re.search(r"^NIVEL\s+(\d)\s+", u)
    if m_nivel and "FINAL FOUR" not in u:
        out.update(fase="Playoff", nivel=m_nivel.group(1))
        return out

    # NORTE 2 A, OESTE 2 B como nombre de fase
    m_reg = re.search(r"^(NORTE|SUR|OESTE|CENTRO)\s+(\d)\s*([ABC])?\s*$", u)
    if m_reg:
        out.update(fase="Playoff", nivel=m_reg.group(2), zona=m_reg.group(1))
        return out

    if "SEMIFINAL" in u:
        out.update(fase="Playoff", ronda="Semifinal")
        return out

    return out


def parsear_fase_2026(fase_text: str) -> Dict[str, str]:
    u = fase_text.upper().strip()
    out = _base()

    # 1ra nivelación: acceso Inter A, Inter B y Nivel 1
    if ("TORNEO DE CLASIFICACION" in u or "TORNEO CLASIFICACION" in u) and "RECLASIFIC" not in u:
        out.update(
            fase="Fase Regular",
            ronda="Torneo Clasificacion",
            nivel="CLASIFICACION",
        )
        return out

    # 2da nivelación: acceso Nivel 1, 2 y 3 (sin interconferencia)
    if "RECLASIFICATOR" in u or (
        "RECLASIFICACION" in u and "TORNEO DE CLASIFICACION" not in u
    ):
        out.update(
            fase="Fase Regular",
            ronda="Torneo Reclasificatorio",
            nivel="RECLASIFICACION",
        )
        return out

    return out
