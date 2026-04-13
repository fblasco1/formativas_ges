# -*- coding: utf-8 -*-
"""
Parseo de DDLGrupos para FeBAMBA 2025 (2do semestre, NIVEL 1–3 playoff, interconferencias).
"""

from __future__ import annotations

import re
from typing import Any

LLAVE_PLAYOFF_EQUIPOS = "LLAVE DE PLAYOFF EQUIPOS"


def _collapse(grupo: str) -> str:
    return re.sub(r"\s+", " ", grupo.strip().upper())


def _fase_norm(fase: str) -> str:
    return re.sub(r"\s+", " ", fase.upper().strip())


def _es_2do_semestre(fase: str) -> bool:
    u = fase.upper()
    return "2DO" in u and "SEMESTRE" in u


def _nivel_fase_playoff(fase_fn: str) -> str | None:
    if fase_fn == "NIVEL 1":
        return "1"
    if fase_fn == "NIVEL 2":
        return "2"
    if fase_fn == "NIVEL 3":
        return "3"
    return None


def _zona_playoff_nivel2_desde_fase(fase_fn: str) -> str | None:
    """Fases GES tipo NIVEL SUR 2C / NIVEL 2 SUR B — zona fija, nivel 2 viene de la fase."""
    if re.fullmatch(r"NIVEL SUR 2[ABC]", fase_fn):
        return "SUR"
    if re.fullmatch(r"NIVEL OESTE 2[AB]", fase_fn):
        return "OESTE"
    if re.fullmatch(r"NIVEL NORTE 2[AB]", fase_fn):
        return "NORTE"
    if fase_fn == "NIVEL SUR C 2":
        return "SUR"
    if re.fullmatch(r"NIVEL 2 SUR [AB]", fase_fn):
        return "SUR"
    if fase_fn == "NIVEL 2 OESTE B":
        return "OESTE"
    if fase_fn == "NIVEL 2 A OESTE":
        return "OESTE"
    if re.fullmatch(r"NIVEL 2 NORTE [AB]", fase_fn):
        return "NORTE"
    return None


def _es_interconf_a_fase(fase_fn: str) -> bool:
    return fase_fn in (
        "INTERCONFERENCIA A",
        "PLAY OFF INTERCONFERENCIA A",
    )


def _es_interconf_b_fase(fase_fn: str) -> bool:
    return fase_fn == "INTERCONFERENCIA B"


def _normalizar_tipos_grupo_ges(grupo: str) -> str:
    """Typo GES: 0ESTE→OESTE; ÚNICOSUR…→ quita prefijo ÚNICO pegado."""
    x = grupo.upper().strip().replace("0ESTE", "OESTE")
    x = re.sub(r"^(ÚNICO|UNICO)(?=[A-ZÑ0-9])", "", x)
    return _collapse(x)


def _es_grupo_unico_ges(g: str) -> bool:
    return bool(re.fullmatch(r"ÚNICO|UNICO", g))


def _match_interconferencias_tanda(grupo: str) -> tuple[str, str, str] | None:
    """INTERCONFERENCIAS A1 / A 3 / B 2 -> (nivel, zona, número de grupo)."""
    g = _collapse(grupo)
    m = re.match(r"^INTERCONFERENCIAS\s+A\s*(\d)$", g)
    if m:
        return ("INTERCONFERENCIAS A", "INTERCONFERENCIA", m.group(1))
    m = re.match(r"^INTERCONFERENCIAS\s+B\s*(\d)$", g)
    if m:
        return ("INTERCONFERENCIAS B", "INTERCONFERENCIA", m.group(1))
    return None


_SEMESTRE_REGLAS: list[tuple[re.Pattern[str], str, str, str]] = [
    (re.compile(r"^NORTE\s+2\s+B$", re.I), "2", "NORTE", "B"),
    (re.compile(r"^NORTE\s+2\s+A$", re.I), "2", "NORTE", "A"),
    (re.compile(r"^OESTE\s+2\s+B$", re.I), "2", "OESTE", "B"),
    (re.compile(r"^OESTE\s+2\s+A$", re.I), "2", "OESTE", "A"),
    (re.compile(r"^SUR\s+2\s+C$", re.I), "2", "SUR", "C"),
    (re.compile(r"^SUR\s+2\s+B$", re.I), "2", "SUR", "B"),
    (re.compile(r"^SUR\s+2\s+A$", re.I), "2", "SUR", "A"),
    (re.compile(r"^SUR\s+2C$", re.I), "2", "SUR", "C"),
    (re.compile(r"^SUR\s+2B$", re.I), "2", "SUR", "B"),
    (re.compile(r"^SUR\s+2A$", re.I), "2", "SUR", "A"),
    (re.compile(r"^CENTRO\s+3$", re.I), "3", "CENTRO", "UNICO"),
    (re.compile(r"^NORTE\s+3$", re.I), "3", "NORTE", "UNICO"),
    (re.compile(r"^OESTE\s+3$", re.I), "3", "OESTE", "UNICO"),
    (re.compile(r"^SUR\s+3$", re.I), "3", "SUR", "UNICO"),
    (re.compile(r"^CENTRO\s+2$", re.I), "2", "CENTRO", "UNICO"),
    (re.compile(r"^CENTRO\s+1$", re.I), "1", "CENTRO", "UNICO"),
    (re.compile(r"^NORTE\s+1$", re.I), "1", "NORTE", "UNICO"),
    (re.compile(r"^SUR\s+1$", re.I), "1", "SUR", "UNICO"),
    (re.compile(r"^OESTE\s+1$", re.I), "1", "OESTE", "UNICO"),
]


def _fallback_sin_match() -> dict[str, Any]:
    return {
        "nivel": "Desconocido",
        "zona": "Desconocida",
        "grupo": "Desconocido",
    }


def _try_playoff_nivel_geografico(niv: str, g: str) -> dict[str, Any] | None:
    """
    Playoffs NIVEL 1/2/3 (fase genérica): zona+N, subgrupo 2A/2 B con o sin espacio.
    Letra de subzona no se persiste en grupo (siempre Desconocido).
    """
    for zname in ("OESTE", "SUR", "CENTRO", "NORTE"):
        if g == zname or g == f"{zname} {niv}":
            return {
                "nivel": niv,
                "zona": zname,
                "grupo": LLAVE_PLAYOFF_EQUIPOS,
                "zona_refina": True,
            }
    m_spaced = re.match(r"^(OESTE|SUR|CENTRO|NORTE)\s+(\d)\s+([A-Z])$", g)
    if m_spaced and m_spaced.group(2) == niv:
        return {
            "nivel": niv,
            "zona": m_spaced.group(1),
            "grupo": "Desconocido",
            "zona_refina": True,
        }
    m_compact = re.match(r"^(OESTE|SUR|CENTRO|NORTE)\s*(\d)([A-Z])$", g)
    if m_compact and m_compact.group(2) == niv:
        return {
            "nivel": niv,
            "zona": m_compact.group(1),
            "grupo": "Desconocido",
            "zona_refina": True,
        }
    return None


def _parse_grupo_bajo_fase_nivel2_variante(
    zona_fase: str, grupo_raw: str
) -> dict[str, Any]:
    """Fase ya acotada a zona (NIVEL SUR 2C, NIVEL 2 SUR B, …)."""
    gr = _normalizar_tipos_grupo_ges(grupo_raw)
    if not gr or _es_grupo_unico_ges(gr):
        return _fallback_sin_match()
    hit = _try_playoff_nivel_geografico("2", gr)
    if hit is not None:
        return {**hit, "grupo": "Desconocido"}
    m_sb = re.match(r"^(SUR|NORTE|OESTE|CENTRO)\s+([A-Z])$", gr)
    if m_sb and m_sb.group(1) == zona_fase:
        return {
            "nivel": "Desconocido",
            "zona": zona_fase,
            "grupo": "Desconocido",
            "zona_refina": True,
        }
    if re.fullmatch(rf"{re.escape(zona_fase)} C 2", gr) or re.fullmatch(
        rf"{re.escape(zona_fase)} 2 C", gr
    ):
        return {
            "nivel": "Desconocido",
            "zona": zona_fase,
            "grupo": "Desconocido",
            "zona_refina": True,
        }
    return _fallback_sin_match()


def parsear_grupo_2025(fase: str, grupo: str) -> dict[str, Any]:
    """
    Devuelve nivel, zona, grupo y opcionalmente fase, zona_refina, nivel_refina.

    Si no hay regla aplicable: nivel/grupo Desconocido, zona Desconocida (como el resto del ETL).
    """
    if not grupo:
        return _fallback_sin_match()

    fase_fn = _fase_norm(fase)
    fase_u = fase.upper().strip()
    g0 = _collapse(grupo)

    if fase_fn == "INTERCONFERENCIAS":
        if g0 == "INTERCONFERENCIA A":
            return {
                "nivel": "INTERCONFERENCIAS A",
                "zona": "Desconocida",
                "grupo": "Desconocido",
            }
        if g0 == "INTERCONFERENCIA B":
            return {
                "nivel": "INTERCONFERENCIAS B",
                "zona": "Desconocida",
                "grupo": "Desconocido",
            }

    if "1ER ETAPA" in fase_u:
        match = re.search(r"([A-ZÑ\s\-]+?)\s*(\d+)$", grupo.upper().strip())
        if match:
            zona_raw = match.group(1).strip().replace("  ", " ")
            return {
                "nivel": "NIVELACION",
                "zona": zona_raw,
                "grupo": match.group(2),
            }

    tanda = _match_interconferencias_tanda(g0)
    if tanda and (
        _es_2do_semestre(fase_u) or fase_fn == "INTERCONFERENCIAS"
    ):
        nivel, zona, gnum = tanda
        return {"nivel": nivel, "zona": zona, "grupo": gnum}

    if _es_2do_semestre(fase_u):
        for rx, nivel, zona, gr in _SEMESTRE_REGLAS:
            if rx.match(g0):
                return {"nivel": nivel, "zona": zona, "grupo": gr}

    zona_n2 = _zona_playoff_nivel2_desde_fase(fase_fn)
    if zona_n2 is not None:
        return _parse_grupo_bajo_fase_nivel2_variante(zona_n2, grupo)

    niv_playoff = _nivel_fase_playoff(fase_fn)
    if niv_playoff is not None:
        gn = _normalizar_tipos_grupo_ges(grupo)
        hit = _try_playoff_nivel_geografico(niv_playoff, gn)
        if hit is not None:
            return hit

    if _es_interconf_b_fase(fase_fn):
        if g0 == "LLAVE 1":
            return {
                "nivel": "INTERCONFERENCIAS B",
                "zona": "INTERCONFERENCIA (B1/B4)",
                "grupo": LLAVE_PLAYOFF_EQUIPOS,
                "zona_refina": True,
            }
        if g0 == "LLAVE 2":
            return {
                "nivel": "INTERCONFERENCIAS B",
                "zona": "INTERCONFERENCIA (B2/B3)",
                "grupo": LLAVE_PLAYOFF_EQUIPOS,
                "zona_refina": True,
            }

    if _es_interconf_a_fase(fase_fn):
        if g0 == "LLAVE 1":
            return {
                "nivel": "INTERCONFERENCIAS A",
                "zona": "INTERCONFERENCIA (A2/A4)",
                "grupo": LLAVE_PLAYOFF_EQUIPOS,
                "fase": "Desconocida",
                "zona_refina": True,
            }
        if g0 == "LLAVE 2":
            return {
                "nivel": "NIVELACION",
                "zona": "INTERCONFERENCIA (A1/A3)",
                "grupo": "Desconocido",
                "zona_refina": True,
                "nivel_refina": True,
            }

    return _fallback_sin_match()
