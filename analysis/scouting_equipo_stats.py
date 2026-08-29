# -*- coding: utf-8 -*-
"""Normalización de nombres de equipo y métricas de partido (scouting rival)."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

_RE_CAT_PREFIX = re.compile(r"^(U13|U15|U17|U21|SUP)\s+", re.I)
_QUOTE_MAP = str.maketrans(
    {
        "\u201c": "'",
        "\u201d": "'",
        "\u2018": "'",
        "\u2019": "'",
        '"': "'",
        "`": "'",
    }
)


def clave_equipo(nombre: str) -> str:
    """Clave canónica: sin acentos, comillas unificadas, sin prefijo Uxx, espacios colapsados."""
    n = unicodedata.normalize("NFKD", nombre or "")
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = n.upper().translate(_QUOTE_MAP)
    n = _RE_CAT_PREFIX.sub("", n)
    n = re.sub(r"\s+", " ", n).strip()
    # Afiliada federativa ↔ nombre corto GES (Superior / Mayores).
    if n in {
        "INSTITUCION CULTURAL Y DEPORTIVA PEDRO ECHAGUE",
        "INSTITUCION CULTURAL Y DEPORTIVA PEDRO ECHAGUE A",
    }:
        return "PEDRO ECHAGUE"
    if n == "INSTITUCION CULTURAL Y DEPORTIVA PEDRO ECHAGUE B":
        return "PEDRO ECHAGUE B"
    return n


def _es_nombre_prefijado(nombre: str) -> bool:
    return bool(_RE_CAT_PREFIX.match((nombre or "").strip()))


def mapa_display_equipos(nombres: Iterable[str]) -> Dict[str, str]:
    """
    Para cada clave canónica, elige un nombre de display:
    el más frecuente entre variantes sin prefijo Uxx/SUP; si no hay, el más frecuente.
    """
    por_clave: Dict[str, Counter] = defaultdict(Counter)
    for raw in nombres:
        if not raw:
            continue
        por_clave[clave_equipo(raw)][raw] += 1
    out: Dict[str, str] = {}
    for clave, cnt in por_clave.items():
        sin_pref = Counter(
            {n: c for n, c in cnt.items() if not _es_nombre_prefijado(n)}
        )
        pool = sin_pref if sin_pref else cnt
        # Preferir más frecuente; desempate: menos comillas dobles, luego más corto.
        out[clave] = sorted(
            pool.items(),
            key=lambda kv: (-kv[1], '"' in kv[0], len(kv[0]), kv[0]),
        )[0][0]
    return out


def _to_int(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    return 0


def sumar_equipo_box(jugadores: List[Dict[str, object]]) -> Dict[str, float]:
    """Totales de equipo a partir de filas de jugadores del acta."""
    pts = rebof = rebdef = ast = rec = per = tap = val = fal = 0
    t2a = t2i = t3a = t3i = tla = tli = 0
    for j in jugadores or []:
        pts += _to_int(j.get("pts"))
        rebof += _to_int(j.get("rebofe"))
        rebdef += _to_int(j.get("rebdef"))
        ast += _to_int(j.get("ast"))
        rec += _to_int(j.get("rec"))
        per += _to_int(j.get("per"))
        tap += _to_int(j.get("tap_com"))
        val += _to_int(j.get("val"))
        fal += _to_int(j.get("fal_com"))
        t2 = j.get("t2") or {}
        t3 = j.get("t3") or {}
        tl = j.get("tl") or {}
        t2a += _to_int(t2.get("a"))
        t2i += _to_int(t2.get("i"))
        t3a += _to_int(t3.get("a"))
        t3i += _to_int(t3.get("i"))
        tla += _to_int(tl.get("a"))
        tli += _to_int(tl.get("i"))
    return {
        "pts": float(pts),
        "rebof": float(rebof),
        "rebdef": float(rebdef),
        "ast": float(ast),
        "rec": float(rec),
        "per": float(per),
        "tap": float(tap),
        "val": float(val),
        "fal": float(fal),
        "t2a": float(t2a),
        "t2i": float(t2i),
        "t3a": float(t3a),
        "t3i": float(t3i),
        "tla": float(tla),
        "tli": float(tli),
    }


def posesiones(line: Dict[str, float]) -> float:
    """Estimación de posesiones: FGA + 0.44*FTA - ORB + TO."""
    fga = line["t2i"] + line["t3i"]
    return fga + 0.44 * line["tli"] - line["rebof"] + line["per"]


def metricas_avanzadas(
    own: Dict[str, float], opp: Dict[str, float]
) -> Dict[str, Optional[float]]:
    """OER/DER/eFG/TS/ORB%/DRB% y posesiones del equipo."""
    poss = posesiones(own)
    opp_poss = posesiones(opp)
    fga = own["t2i"] + own["t3i"]
    fgm = own["t2a"] + own["t3a"]
    efg = (100.0 * (fgm + 0.5 * own["t3a"]) / fga) if fga > 0 else None
    ts_den = 2.0 * (fga + 0.44 * own["tli"])
    ts = (100.0 * own["pts"] / ts_den) if ts_den > 0 else None
    orb_den = own["rebof"] + opp["rebdef"]
    drb_den = own["rebdef"] + opp["rebof"]
    orb_pct = (100.0 * own["rebof"] / orb_den) if orb_den > 0 else None
    drb_pct = (100.0 * own["rebdef"] / drb_den) if drb_den > 0 else None
    oer = (100.0 * own["pts"] / poss) if poss > 0 else None
    der = (100.0 * opp["pts"] / opp_poss) if opp_poss > 0 else None
    return {
        "poss": round(poss, 1) if poss > 0 else None,
        "oer": round(oer, 1) if oer is not None else None,
        "der": round(der, 1) if der is not None else None,
        "efg": round(efg, 1) if efg is not None else None,
        "ts": round(ts, 1) if ts is not None else None,
        "orb_pct": round(orb_pct, 1) if orb_pct is not None else None,
        "drb_pct": round(drb_pct, 1) if drb_pct is not None else None,
    }


def _parse_fecha(fecha: str) -> datetime:
    fecha = (fecha or "").strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(fecha[:16], fmt)
        except ValueError:
            continue
    return datetime.min


def _fmt_tiros(a: float, i: float) -> str:
    return f"{int(a)}/{int(i)}"


def construir_partidos_equipo(
    partidos: List[Dict[str, str]],
    boxscores: Dict[str, Dict[str, object]],
    display: Dict[str, str],
) -> Dict[Tuple[str, str], List[Dict[str, object]]]:
    """
    Index (display_equipo, categoria) -> lista de partidos del equipo (con rivales y avanzadas).
    """
    out: Dict[Tuple[str, str], List[Dict[str, object]]] = defaultdict(list)

    for p in partidos:
        box = boxscores.get(p["id_partido"])
        if not box or not box.get("ok"):
            continue
        eqs = box.get("equipos") or []
        if len(eqs) < 2:
            continue
        cat = (p.get("categoria") or "").strip()
        # Preferir nombres del acta; fallback al fixture.
        raw_names = [
            (eqs[0].get("nombre") or p.get("local") or ""),
            (eqs[1].get("nombre") or p.get("visitante") or ""),
        ]
        claves = [clave_equipo(n) for n in raw_names]
        lines = [
            sumar_equipo_box(eqs[0].get("jugadores") or []),
            sumar_equipo_box(eqs[1].get("jugadores") or []),
        ]
        fecha = p.get("fecha") or ""
        for idx in (0, 1):
            clave = claves[idx]
            if not clave:
                continue
            eq_disp = display.get(clave) or raw_names[idx]
            riv_clave = claves[1 - idx]
            riv_disp = display.get(riv_clave) or raw_names[1 - idx]
            own, opp = lines[idx], lines[1 - idx]
            adv = metricas_avanzadas(own, opp)
            won = own["pts"] > opp["pts"]
            out[(eq_disp, cat)].append(
                {
                    "fecha": fecha,
                    "_dt": _parse_fecha(fecha),
                    "fase": (p.get("fase") or "").strip(),
                    "rival": riv_disp,
                    "loc": "L" if idx == 0 else "V",
                    "res": "G" if won else "P",
                    "pts": int(own["pts"]),
                    "pts_riv": int(opp["pts"]),
                    "t2": _fmt_tiros(own["t2a"], own["t2i"]),
                    "t3": _fmt_tiros(own["t3a"], own["t3i"]),
                    "tl": _fmt_tiros(own["tla"], own["tli"]),
                    "ro": int(own["rebof"]),
                    "rd": int(own["rebdef"]),
                    "ast": int(own["ast"]),
                    "rec": int(own["rec"]),
                    "per": int(own["per"]),
                    "val": int(own["val"]),
                    **adv,
                    # crudos para promediar temporada
                    "_own": own,
                    "_opp": opp,
                }
            )

    for key, games in out.items():
        games.sort(key=lambda g: g["_dt"], reverse=True)
    return out


def promediar_avanzadas(games: List[Dict[str, object]]) -> Dict[str, Optional[float]]:
    if not games:
        return {
            "poss": None,
            "oer": None,
            "der": None,
            "efg": None,
            "ts": None,
            "orb_pct": None,
            "drb_pct": None,
            "pts": None,
            "pts_riv": None,
            "ro": None,
            "rd": None,
            "ast": None,
            "rec": None,
            "per": None,
            "val": None,
            "pj": 0,
        }
    owns = [g["_own"] for g in games]  # type: ignore[index]
    opps = [g["_opp"] for g in games]  # type: ignore[index]
    n = len(games)

    def mean_own(field: str) -> float:
        return sum(o[field] for o in owns) / n

    avg_own = {k: mean_own(k) for k in owns[0]}
    avg_opp = {k: sum(o[k] for o in opps) / n for k in opps[0]}
    adv = metricas_avanzadas(avg_own, avg_opp)
    return {
        **adv,
        "pts": round(avg_own["pts"], 1),
        "pts_riv": round(avg_opp["pts"], 1),
        "ro": round(avg_own["rebof"], 1),
        "rd": round(avg_own["rebdef"], 1),
        "ast": round(avg_own["ast"], 1),
        "rec": round(avg_own["rec"], 1),
        "per": round(avg_own["per"], 1),
        "val": round(avg_own["val"], 1),
        "t2a": round(avg_own["t2a"], 1),
        "t3a": round(avg_own["t3a"], 1),
        "pj": n,
    }


def media_competencia(
    por_equipo: Dict[Tuple[str, str], List[Dict[str, object]]], cat: str
) -> Dict[str, Optional[float]]:
    """Media de la competencia = promedio de promedios de equipo en esa categoría."""
    season_avgs = [
        promediar_avanzadas(games)
        for (eq, c), games in por_equipo.items()
        if c == cat and games
    ]
    if not season_avgs:
        return {}
    keys = [
        "pts",
        "pts_riv",
        "ro",
        "rd",
        "ast",
        "rec",
        "per",
        "val",
        "t2a",
        "t3a",
        "poss",
        "oer",
        "der",
        "efg",
        "ts",
        "orb_pct",
        "drb_pct",
    ]
    out: Dict[str, Optional[float]] = {}
    for k in keys:
        vals = [float(a[k]) for a in season_avgs if a.get(k) is not None]
        out[k] = round(sum(vals) / len(vals), 1) if vals else None
    out["n_equipos"] = len(season_avgs)
    return out


def serializar_partido(g: Dict[str, object]) -> Dict[str, object]:
    """Quita campos internos antes de embeber en JSON."""
    dt = g.get("_dt")
    dt_iso = ""
    if isinstance(dt, datetime) and dt != datetime.min:
        dt_iso = dt.isoformat()
    return {
        "fecha": g.get("fecha") or "",
        "dt": dt_iso,
        "fase": g.get("fase") or "",
        "rival": g.get("rival") or "",
        "loc": g.get("loc"),
        "res": g.get("res"),
        "pts": g.get("pts"),
        "pts_riv": g.get("pts_riv"),
        "t2": g.get("t2"),
        "t3": g.get("t3"),
        "tl": g.get("tl"),
        "ro": g.get("ro"),
        "rd": g.get("rd"),
        "ast": g.get("ast"),
        "rec": g.get("rec"),
        "per": g.get("per"),
        "val": g.get("val"),
        "poss": g.get("poss"),
        "oer": g.get("oer"),
        "der": g.get("der"),
        "efg": g.get("efg"),
        "ts": g.get("ts"),
        "orb_pct": g.get("orb_pct"),
        "drb_pct": g.get("drb_pct"),
    }
