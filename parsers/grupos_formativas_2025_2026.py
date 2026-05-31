# -*- coding: utf-8 -*-
"""Reglas de parseo de grupo (DDLGrupos) para formativas 2025 y 2026."""

from __future__ import annotations

import re
from typing import Dict, Tuple

ZONAS = ("CENTRO", "NORTE", "SUR", "OESTE")


def _parse_zona_nivel_grupo_regular(grupo: str) -> Tuple[str, str, str]:
    """
    Ej: CENTRO 4, NORTE 2 A, SUR 6, NORTE 2B, CENTRO OESTE 4
    """
    g = grupo.upper().strip().replace("  ", " ")
    g = g.replace("0ESTE", "OESTE")

    m = re.match(r"^(" + "|".join(ZONAS) + r")(?:\s+(" + "|".join(ZONAS) + r"))?\s+(\d+)\s*([ABC])?$", g)
    if m:
        z1, z2, num, letra = m.group(1), m.group(2), m.group(3), m.group(4) or ""
        zona = f"{z1}-{z2}" if z2 else z1
        return "Desconocido", zona, f"{num}{letra}".strip()

    m2 = re.match(r"^(" + "|".join(ZONAS) + r")\s+(\d+)\s*([ABC])?$", g)
    if m2:
        return "Desconocido", m2.group(1), f"{m2.group(2)}{m2.group(3) or ''}"

    m3 = re.match(r"^(" + "|".join(ZONAS) + r")\s+(\d+)$", g)
    if m3:
        return "Desconocido", m3.group(1), m3.group(2)

    return "Desconocido", "Desconocido", grupo.strip()


def _parse_inter_llave(grupo: str) -> Tuple[str, str, str]:
    """INTERCONFERENCIAS A1, LLAVE 2, INTERCONFERENCIA A 3."""
    g = grupo.upper().strip()
    m = re.search(r"INTERCONFERENCIAS?\s*([AB])\s*(\d+)", g)
    if m:
        return f"INTERCONFERENCIA {m.group(1)}", "INTERCONFERENCIA", m.group(2)
    m2 = re.search(r"LLAVE\s*(\d+)", g)
    if m2:
        return "Desconocido", "INTERCONFERENCIA", m2.group(1)
    if "INTERCONFERENCIA A" in g:
        return "INTERCONFERENCIA A", "INTERCONFERENCIA", g
    if "INTERCONFERENCIA B" in g:
        return "INTERCONFERENCIA B", "INTERCONFERENCIA", g
    return "Desconocido", "INTERCONFERENCIA", g


def parsear_grupo_2025(fase: str, grupo: str) -> Dict[str, str]:
    f = fase.upper().strip()
    g = grupo.upper().strip()
    nivel, zona, grupo_final = "Desconocido", "Desconocido", "Desconocido"

    if "1ER ETAPA" in f:
        nivel = "NIVELACION"
        _, zona, grupo_final = _parse_zona_nivel_grupo_regular(grupo)
        return {"nivel": nivel, "zona": zona, "grupo": grupo_final}

    if "2DO SEMESTRE" in f or "2º SEMESTRE" in f:
        if "INTERCONFERENCIA" in g or "INTERCONFERENCIAS" in g:
            nivel, zona, grupo_final = _parse_inter_llave(grupo)
        else:
            n, z, gf = _parse_zona_nivel_grupo_regular(grupo)
            # NORTE 2 A → nivel 2
            m = re.match(r"^(" + "|".join(ZONAS) + r")\s+(\d+)\s*([ABC])?$", g.replace("  ", " "))
            if m:
                nivel, zona, grupo_final = m.group(2), m.group(1), f"{m.group(2)}{m.group(3) or ''}"
            else:
                nivel, zona, grupo_final = n, z, gf
        return {"nivel": nivel, "zona": zona, "grupo": grupo_final}

    if "FINAL FOUR" in f:
        m = re.search(r"FINAL\s+FOUR\s*(\d)", f)
        nivel = m.group(1) if m else "Desconocido"
        if "/" in g or "-" in g:
            grupo_final = g
        else:
            _, zona, grupo_final = _parse_zona_nivel_grupo_regular(grupo)
        return {"nivel": nivel, "zona": zona if zona != "Desconocido" else "Desconocida", "grupo": grupo_final}

    if "INTERCONFERENCIA" in f or "PLAY OFF INTERCONFERENCIA" in f:
        nivel, zona, grupo_final = _parse_inter_llave(grupo)
        if "INTERCONFERENCIA A" in f:
            nivel = "INTERCONFERENCIA A"
        elif "INTERCONFERENCIA B" in f:
            nivel = "INTERCONFERENCIA B"
        return {"nivel": nivel, "zona": "INTERCONFERENCIA", "grupo": grupo_final}

    if f == "INTERCONFERENCIAS" or ("INTERCONFERENCIAS" in f and " A" not in f and " B" not in f):
        nivel, zona, grupo_final = _parse_inter_llave(grupo)
        return {"nivel": nivel or "INTERCONFERENCIA", "zona": "INTERCONFERENCIA", "grupo": grupo_final}

    if "TRIANGULAR FINAL" in f:
        return {"nivel": "Desconocido", "zona": "SUR", "grupo": grupo.strip()}

    if f.startswith("NIVEL ") or re.match(r"^(NORTE|SUR|OESTE|CENTRO)\s", f):
        m = re.search(r"NIVEL\s+(?:(NORTE|SUR|OESTE|CENTRO)\s+)?(\d)", f)
        if m:
            nivel = m.group(2)
            if m.group(1):
                zona = m.group(1)
        elif re.match(r"^NIVEL\s+(\d)\s*$", f):
            nivel = re.match(r"^NIVEL\s+(\d)\s*$", f).group(1)
        m2 = re.match(r"^(" + "|".join(ZONAS) + r")\s+(\d+)", f)
        if m2:
            zona, nivel = m2.group(1), m2.group(2)
        n, z, gf = _parse_zona_nivel_grupo_regular(grupo)
        if z != "Desconocido":
            zona = z
        if n != "Desconocido":
            nivel = n
        grupo_final = gf
        return {"nivel": nivel, "zona": zona, "grupo": grupo_final}

    return {"nivel": nivel, "zona": zona, "grupo": grupo_final or grupo.strip()}


def parsear_grupo_2026(fase: str, grupo: str) -> Dict[str, str]:
    f = fase.upper().strip()
    g = grupo.upper().strip()
    nivel = "Desconocido"
    zona, grupo_final = "Desconocido", "Desconocido"

    if "TORNEO DE CLASIFICACION" in f or (
        "CLASIFICACION" in f and "RECLASIFIC" not in f and "LFF" not in f
    ):
        nivel = "CLASIFICACION"
    elif "RECLASIFIC" in f:
        nivel = "RECLASIFICACION"

    if nivel != "Desconocido":
        _, zona, grupo_final = _parse_zona_nivel_grupo_regular(grupo)
        m = re.match(r"^(" + "|".join(ZONAS) + r")\s+(\d+)$", g.replace("  ", " "))
        if m:
            zona, grupo_final = m.group(1), m.group(2)
        return {"nivel": nivel, "zona": zona, "grupo": grupo_final or g}

    return {"nivel": nivel, "zona": zona, "grupo": grupo_final or grupo.strip()}
