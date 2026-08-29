# -*- coding: utf-8 -*-
"""
Promedios de fase regular METRO (Liga Federal Mayores, GES 2032)
cuando el equipo gana — base para objetivos de plantel.

Grupos: METRO A / METRO B / METRO C.
Solo partidos COMPLETO con boxscore válido; excluye walkovers 20-0.

  python analysis/promedios_victorias_metro_lff.py --progress
  python analysis/promedios_victorias_metro_lff.py --desde-cache
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.scouting_equipo_stats import posesiones, sumar_equipo_box  # noqa: E402
from ingest.argbasket.partido import parse_boxscore_html  # noqa: E402
from ingest.ges.extractor import GesDeportivaExtractor  # noqa: E402
from ingest.http_client import HttpClient, SessionProvider  # noqa: E402

ID_COMPETENCIA = 2032
ID_CATEGORIA = 5117
ID_FASE_REGULAR = 18129
GRUPOS_METRO: Dict[str, int] = {
    "METRO A": 34583,
    "METRO B": 34584,
    "METRO C": 34585,
}

OUT_DIR = ROOT / "outputs" / "lff_metro_objetivos"
OUT_JSON = OUT_DIR / "promedios_victorias.json"
OUT_CORR_JSON = OUT_DIR / "correlacion_victorias.json"
BOXSCORES_CACHE = OUT_DIR / "boxscores.json"
PARTIDOS_CACHE = OUT_DIR / "partidos.json"

# (clave, etiqueta, mayor_es_mejor_para_ganar)
METRICAS_CORR: Tuple[Tuple[str, str, bool], ...] = (
    ("pts", "PTS anotados", True),
    ("ro", "RO propio", True),
    ("ast_per", "AST/PER", True),
    ("rec", "Recuperos", True),
    ("pct_2p", "% 2P propio", True),
    ("pct_3p", "% 3P propio", True),
    ("pct_tl", "% TL propio", True),
    ("pts_recibidos", "PTS recibidos", False),
    ("ro_rival", "RO rival", False),
    ("per_rival", "Pérdidas rival", True),
    ("pct_2p_rival", "% 2P rival", False),
    ("pct_3p_rival", "% 3P rival", False),
    ("pct_tl_rival", "% TL rival", False),
    ("poss", "Posesiones", True),
    ("fga", "Tiros de cancha (intentos)", True),
    ("fgm", "Tiros de cancha (anotados)", True),
    ("t2i", "Intentos 2P", True),
    ("t2a", "Aciertos 2P", True),
    ("t3i", "Intentos 3P", True),
    ("t3a", "Aciertos 3P", True),
    ("tli", "Intentos TL", True),
    ("tla", "Aciertos TL", True),
)

# Casi tautológicas con el resultado (margen); se reportan aparte.
METRICAS_CIRCULARES = {"pts", "pts_recibidos"}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
)


def _load_widget_key() -> str:
    with (ROOT / "config" / "competencias.json").open(encoding="utf-8") as f:
        return json.load(f).get("widget_key", "")


def _to_int(value: object) -> Optional[int]:
    if value is None:
        return None
    s = str(value).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    return None


def _boxscore_url(token: str) -> str:
    return (
        "https://argentina.basketball/liga-federal/partido/estadisticas/"
        f"{token.strip()}==?key="
    )


def _es_walkover(pl: Optional[int], pv: Optional[int]) -> bool:
    if pl is None or pv is None:
        return False
    return (pl == 20 and pv == 0) or (pl == 0 and pv == 20)


def recolectar_partidos(
    ges: GesDeportivaExtractor,
    *,
    key: str,
    fecha_ini: str,
    fecha_fin: str,
    progress: bool = False,
) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for nombre_grupo, id_grupo in GRUPOS_METRO.items():
        partidos = ges.get_info_partidos(
            ID_CATEGORIA,
            fecha_ini,
            fecha_fin,
            key=key,
            id_fase=ID_FASE_REGULAR,
            id_grupo=id_grupo,
        )
        n = 0
        for p in partidos:
            if p.get("Estado") != "COMPLETO":
                continue
            pl = _to_int(p.get("PTS_LOCAL"))
            pv = _to_int(p.get("PTS_VISITANTE"))
            out.append(
                {
                    "grupo": nombre_grupo,
                    "local": p.get("Local") or "",
                    "visitante": p.get("Visitante") or "",
                    "pts_local": pl,
                    "pts_visit": pv,
                    "id_partido": p.get("ID_PARTIDO") or "",
                    "fecha": p.get("Fecha") or "",
                    "walkover": _es_walkover(pl, pv),
                }
            )
            n += 1
        if progress:
            print(f"  {nombre_grupo}: {n} partidos COMPLETO", file=sys.stderr, flush=True)
    return out


def _descargar_boxscore(token: str) -> Dict[str, object]:
    try:
        resp = requests.get(
            _boxscore_url(token),
            headers={"User-Agent": UA, "Accept": "text/html,*/*"},
            timeout=45,
        )
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    if len(html) < 8000:
        return {"ok": False, "error": "html_corto"}
    equipos = parse_boxscore_html(html).get("equipos") or []
    if len(equipos) < 2:
        return {"ok": False, "error": "sin_equipos"}
    return {
        "ok": True,
        "equipos": [
            {
                "nombre": eq.get("nombre") or "",
                "jugadores": eq.get("jugadores") or [],
            }
            for eq in equipos[:2]
        ],
    }


def descargar_boxscores(
    tokens: List[str],
    *,
    workers: int = 10,
    progress: bool = False,
    force: bool = False,
) -> Dict[str, Dict[str, object]]:
    cache: Dict[str, Dict[str, object]] = {}
    if BOXSCORES_CACHE.exists() and not force:
        try:
            cache = json.loads(BOXSCORES_CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    unicos = [t for t in dict.fromkeys(tokens) if t]
    pendientes = [
        t
        for t in unicos
        if force or t not in cache or not cache[t].get("ok")
    ]
    if progress:
        print(
            f"Boxscores: {len(unicos)} únicos, {len(unicos) - len(pendientes)} ok en caché, "
            f"{len(pendientes)} a descargar…",
            file=sys.stderr,
            flush=True,
        )
    if pendientes:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            fut = {pool.submit(_descargar_boxscore, t): t for t in pendientes}
            done = 0
            for f in as_completed(fut):
                cache[fut[f]] = f.result()
                done += 1
                if progress and (done % 25 == 0 or done == len(pendientes)):
                    print(f"  {done}/{len(pendientes)}", file=sys.stderr, flush=True)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        BOXSCORES_CACHE.write_text(
            json.dumps(cache, ensure_ascii=False), encoding="utf-8"
        )
    return cache


def _pct(a: float, i: float) -> Optional[float]:
    if i <= 0:
        return None
    return round(100.0 * a / i, 1)


def _round1(x: float) -> float:
    return round(x, 1)


def promedios_victorias(
    partidos: List[Dict[str, object]],
    boxscores: Dict[str, Dict[str, object]],
) -> Dict[str, object]:
    wins: List[Dict[str, object]] = []
    omitidos = {"sin_box": 0, "walkover": 0, "empate": 0, "sin_pts": 0}

    for p in partidos:
        if p.get("walkover"):
            omitidos["walkover"] += 1
            continue
        token = str(p.get("id_partido") or "")
        box = boxscores.get(token) or {}
        if not box.get("ok"):
            omitidos["sin_box"] += 1
            continue
        eqs = box.get("equipos") or []
        if len(eqs) < 2:
            omitidos["sin_box"] += 1
            continue
        lines = [
            sumar_equipo_box(eqs[0].get("jugadores") or []),
            sumar_equipo_box(eqs[1].get("jugadores") or []),
        ]
        # Preferir puntos del box; fallback al fixture.
        pl = int(lines[0]["pts"])
        pv = int(lines[1]["pts"])
        if pl == 0 and pv == 0:
            pl_f = p.get("pts_local")
            pv_f = p.get("pts_visit")
            if isinstance(pl_f, int) and isinstance(pv_f, int):
                pl, pv = pl_f, pv_f
        if pl == pv:
            omitidos["empate"] += 1
            continue
        if pl <= 0 and pv <= 0:
            omitidos["sin_pts"] += 1
            continue
        wi = 0 if pl > pv else 1
        own, opp = lines[wi], lines[1 - wi]
        wins.append(
            {
                "grupo": p.get("grupo"),
                "fecha": p.get("fecha"),
                "ganador": eqs[wi].get("nombre") or "",
                "rival": eqs[1 - wi].get("nombre") or "",
                "own": own,
                "opp": opp,
            }
        )

    n = len(wins)
    if n == 0:
        return {"n_victorias": 0, "omitidos": omitidos}

    def mean_field(side: str, field: str) -> float:
        return sum(w[side][field] for w in wins) / n  # type: ignore[index]

    sum_own = {k: sum(w["own"][k] for w in wins) for k in wins[0]["own"]}  # type: ignore[index]
    sum_opp = {k: sum(w["opp"][k] for w in wins) for k in wins[0]["opp"]}  # type: ignore[index]

    pts = mean_field("own", "pts")
    pts_riv = mean_field("opp", "pts")
    ro = mean_field("own", "rebof")
    ro_riv = mean_field("opp", "rebof")
    ast = mean_field("own", "ast")
    per = mean_field("own", "per")
    rec = mean_field("own", "rec")
    per_riv = mean_field("opp", "per")
    ast_per = (ast / per) if per > 0 else None

    propio = {
        "pts": _round1(pts),
        "ro": _round1(ro),
        "ast": _round1(ast),
        "per": _round1(per),
        "ast_per": round(ast_per, 2) if ast_per is not None else None,
        "rec": _round1(rec),
        "pct_2p": _pct(sum_own["t2a"], sum_own["t2i"]),
        "pct_3p": _pct(sum_own["t3a"], sum_own["t3i"]),
        "pct_tl": _pct(sum_own["tla"], sum_own["tli"]),
        "t2": f"{int(round(mean_field('own', 't2a')))}/{int(round(mean_field('own', 't2i')))}",
        "t3": f"{int(round(mean_field('own', 't3a')))}/{int(round(mean_field('own', 't3i')))}",
        "tl": f"{int(round(mean_field('own', 'tla')))}/{int(round(mean_field('own', 'tli')))}",
        "t2a": _round1(mean_field("own", "t2a")),
        "t2i": _round1(mean_field("own", "t2i")),
        "t3a": _round1(mean_field("own", "t3a")),
        "t3i": _round1(mean_field("own", "t3i")),
        "tla": _round1(mean_field("own", "tla")),
        "tli": _round1(mean_field("own", "tli")),
        "fga": _round1(mean_field("own", "t2i") + mean_field("own", "t3i")),
        "poss": _round1(sum(posesiones(w["own"]) for w in wins) / n),  # type: ignore[arg-type]
    }
    rival = {
        "pts_recibidos": _round1(pts_riv),
        "ro": _round1(ro_riv),
        "per": _round1(per_riv),
        "pct_2p": _pct(sum_opp["t2a"], sum_opp["t2i"]),
        "pct_3p": _pct(sum_opp["t3a"], sum_opp["t3i"]),
        "pct_tl": _pct(sum_opp["tla"], sum_opp["tli"]),
        "t2": f"{int(round(mean_field('opp', 't2a')))}/{int(round(mean_field('opp', 't2i')))}",
        "t3": f"{int(round(mean_field('opp', 't3a')))}/{int(round(mean_field('opp', 't3i')))}",
        "tl": f"{int(round(mean_field('opp', 'tla')))}/{int(round(mean_field('opp', 'tli')))}",
        "t2a": _round1(mean_field("opp", "t2a")),
        "t2i": _round1(mean_field("opp", "t2i")),
        "t3a": _round1(mean_field("opp", "t3a")),
        "t3i": _round1(mean_field("opp", "t3i")),
        "tla": _round1(mean_field("opp", "tla")),
        "tli": _round1(mean_field("opp", "tli")),
        "fga": _round1(mean_field("opp", "t2i") + mean_field("opp", "t3i")),
        "poss": _round1(sum(posesiones(w["opp"]) for w in wins) / n),  # type: ignore[arg-type]
    }

    por_grupo: Dict[str, int] = {}
    for w in wins:
        g = str(w.get("grupo") or "")
        por_grupo[g] = por_grupo.get(g, 0) + 1

    return {
        "competencia": ID_COMPETENCIA,
        "fase": "FASE REGULAR",
        "grupos": list(GRUPOS_METRO.keys()),
        "n_partidos_fixture": len(partidos),
        "n_victorias": n,
        "por_grupo": por_grupo,
        "omitidos": omitidos,
        "propio": propio,
        "rival": rival,
        # Objetivos redondeados a enteros / décimas útiles para el plantel.
        "objetivos_sugeridos": {
            "propio": {
                "pts": round(pts),
                "ro": round(ro),
                "ast_per": round(ast_per, 1) if ast_per is not None else None,
                "rec": round(rec),
                "pct_2p": round(propio["pct_2p"] or 0),
                "pct_3p": round(propio["pct_3p"] or 0),
                "pct_tl": round(propio["pct_tl"] or 0),
            },
            "rival": {
                "pts_recibidos_max": round(pts_riv),
                "ro_max": round(ro_riv),
                "per_forzadas_min": round(per_riv),
                "pct_2p_max": round(rival["pct_2p"] or 0),
                "pct_3p_max": round(rival["pct_3p"] or 0),
                "pct_tl_max": round(rival["pct_tl"] or 0),
            },
        },
    }


def _pct_linea(line: Dict[str, float], pref: str) -> Optional[float]:
    a = line[f"{pref}a"]
    i = line[f"{pref}i"]
    if i <= 0:
        return None
    return 100.0 * a / i


def _metricas_actuacion(
    own: Dict[str, float], opp: Dict[str, float]
) -> Dict[str, Optional[float]]:
    per = own["per"]
    ast_per = (own["ast"] / per) if per > 0 else (own["ast"] if own["ast"] > 0 else None)
    fga = own["t2i"] + own["t3i"]
    return {
        "pts": own["pts"],
        "ro": own["rebof"],
        "ast_per": ast_per,
        "rec": own["rec"],
        "pct_2p": _pct_linea(own, "t2"),
        "pct_3p": _pct_linea(own, "t3"),
        "pct_tl": _pct_linea(own, "tl"),
        "pts_recibidos": opp["pts"],
        "ro_rival": opp["rebof"],
        "per_rival": opp["per"],
        "pct_2p_rival": _pct_linea(opp, "t2"),
        "pct_3p_rival": _pct_linea(opp, "t3"),
        "pct_tl_rival": _pct_linea(opp, "tl"),
        "poss": posesiones(own),
        "t2i": own["t2i"],
        "t2a": own["t2a"],
        "t3i": own["t3i"],
        "t3a": own["t3a"],
        "tli": own["tli"],
        "tla": own["tla"],
        "fga": fga,
        "fgm": own["t2a"] + own["t3a"],
    }



def construir_actuaciones(
    partidos: List[Dict[str, object]],
    boxscores: Dict[str, Dict[str, object]],
) -> List[Dict[str, object]]:
    """Una fila por equipo-partido (ganador y perdedor)."""
    rows: List[Dict[str, object]] = []
    for p in partidos:
        if p.get("walkover"):
            continue
        token = str(p.get("id_partido") or "")
        box = boxscores.get(token) or {}
        if not box.get("ok"):
            continue
        eqs = box.get("equipos") or []
        if len(eqs) < 2:
            continue
        lines = [
            sumar_equipo_box(eqs[0].get("jugadores") or []),
            sumar_equipo_box(eqs[1].get("jugadores") or []),
        ]
        pl, pv = int(lines[0]["pts"]), int(lines[1]["pts"])
        if pl == pv:
            continue
        for idx in (0, 1):
            own, opp = lines[idx], lines[1 - idx]
            won = own["pts"] > opp["pts"]
            m = _metricas_actuacion(own, opp)
            rows.append(
                {
                    "grupo": p.get("grupo"),
                    "id_partido": token,
                    "equipo": eqs[idx].get("nombre") or "",
                    "win": 1 if won else 0,
                    **m,
                }
            )
    return rows


def _pearson(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    if len(x) < 3 or len(x) != len(y):
        return None
    ax = np.asarray(x, dtype=float)
    ay = np.asarray(y, dtype=float)
    if np.std(ax) == 0 or np.std(ay) == 0:
        return None
    r = float(np.corrcoef(ax, ay)[0, 1])
    return None if math.isnan(r) else r


def _cohens_d(g: Sequence[float], p: Sequence[float]) -> Optional[float]:
    if len(g) < 2 or len(p) < 2:
        return None
    ag = np.asarray(g, dtype=float)
    ap = np.asarray(p, dtype=float)
    ng, np_ = len(ag), len(ap)
    vg, vp = float(np.var(ag, ddof=1)), float(np.var(ap, ddof=1))
    pooled = math.sqrt(((ng - 1) * vg + (np_ - 1) * vp) / (ng + np_ - 2))
    if pooled == 0:
        return None
    return float((ag.mean() - ap.mean()) / pooled)


def _nivel_r(abs_r: float) -> str:
    if abs_r >= 0.5:
        return "fuerte"
    if abs_r >= 0.3:
        return "moderada"
    if abs_r >= 0.1:
        return "débil"
    return "muy débil"


def correlaciones_victoria(
    actuaciones: List[Dict[str, object]],
) -> Dict[str, object]:
    """Correlación punto-biserial (Pearson vs win 0/1) + Cohen's d G vs P."""
    metricas: List[Dict[str, object]] = []
    for clave, etiqueta, mayor_mejor in METRICAS_CORR:
        pares = [
            (float(a[clave]), int(a["win"]))  # type: ignore[arg-type]
            for a in actuaciones
            if a.get(clave) is not None
        ]
        if len(pares) < 10:
            continue
        xs = [v for v, _ in pares]
        ys = [w for _, w in pares]
        g = [v for v, w in pares if w == 1]
        p = [v for v, w in pares if w == 0]
        r = _pearson(xs, ys)
        d = _cohens_d(g, p)
        abs_r = abs(r) if r is not None else 0.0
        # Importancia de proceso: |r|; PTS se marcan como circulares.
        metricas.append(
            {
                "clave": clave,
                "etiqueta": etiqueta,
                "mayor_mejor": mayor_mejor,
                "circular": clave in METRICAS_CIRCULARES,
                "n": len(pares),
                "r": round(r, 3) if r is not None else None,
                "abs_r": round(abs_r, 3),
                "nivel": _nivel_r(abs_r),
                "media_g": round(float(np.mean(g)), 2),
                "media_p": round(float(np.mean(p)), 2),
                "diff_g_p": round(float(np.mean(g) - np.mean(p)), 2),
                "cohens_d": round(d, 2) if d is not None else None,
                "sentido_ok": (
                    (r is not None and r > 0 and mayor_mejor)
                    or (r is not None and r < 0 and not mayor_mejor)
                    or r == 0
                ),
            }
        )

    proceso = [m for m in metricas if not m["circular"]]
    # Colapsar pares espejo (ej. % 3P propio ↔ % 3P rival): mismo |r| por diseño.
    espejo_de = {
        "pct_2p_rival": "pct_2p",
        "pct_3p_rival": "pct_3p",
        "pct_tl_rival": "pct_tl",
        "ro_rival": "ro",
    }
    por_clave = {m["clave"]: m for m in proceso}
    unicas: List[Dict[str, object]] = []
    vistos = set()
    for m in sorted(proceso, key=lambda x: x["abs_r"], reverse=True):
        clave = str(m["clave"])
        canon = espejo_de.get(clave, clave)
        if canon in vistos:
            continue
        vistos.add(canon)
        base = por_clave.get(canon, m)
        if clave in espejo_de:
            etiqueta = {
                "pct_2p": "% 2P (propio↑ / rival↓)",
                "pct_3p": "% 3P (propio↑ / rival↓)",
                "pct_tl": "% TL (propio↑ / rival↓)",
                "ro": "RO (propio↑ / rival↓)",
            }.get(canon, str(base["etiqueta"]))
        else:
            etiqueta = str(base["etiqueta"])
        unicas.append({**base, "etiqueta": etiqueta})

    prioridad = []
    for i, m in enumerate(unicas, start=1):
        mayor = bool(m["mayor_mejor"])
        if str(m["clave"]) in {"pct_2p", "pct_3p", "pct_tl", "ro"}:
            mensaje = f"Mejorar {m['etiqueta']}"
        elif mayor:
            mensaje = f"Priorizar subir {m['etiqueta']}"
        else:
            mensaje = f"Priorizar bajar {m['etiqueta']}"
        prioridad.append(
            {
                "orden": i,
                "etiqueta": m["etiqueta"],
                "clave": m["clave"],
                "r": m["r"],
                "nivel": m["nivel"],
                "diff_g_p": m["diff_g_p"],
                "cohens_d": m["cohens_d"],
                "media_g": m["media_g"],
                "media_p": m["media_p"],
                "mensaje": mensaje,
            }
        )

    todas_ranked = sorted(metricas, key=lambda m: m["abs_r"], reverse=True)

    return {
        "n_actuaciones": len(actuaciones),
        "n_victorias": sum(int(a["win"]) for a in actuaciones),
        "n_derrotas": sum(1 - int(a["win"]) for a in actuaciones),
        "nota": (
            "r = correlación punto-biserial con victoria (1/0). "
            "|r| alto = más asociada a ganar. "
            "PTS anotados/recibidos son casi circulares con el resultado. "
            "% tiro propio/rival y RO propio/rival son espejos del mismo partido "
            "(mismo |r|); la prioridad colapsa esos pares."
        ),
        "metricas": metricas,
        "ranking_todas": [
            {"etiqueta": m["etiqueta"], "r": m["r"], "nivel": m["nivel"]}
            for m in todas_ranked
        ],
        "prioridad_proceso": prioridad,
    }


def imprimir_correlaciones(corr: Dict[str, object]) -> None:
    print()
    print("=" * 72)
    print("CORRELACIÓN CON VICTORIA — métricas de proceso (sin PTS)")
    print("=" * 72)
    print(
        f"Actuaciones: {corr.get('n_actuaciones')} "
        f"({corr.get('n_victorias')} G / {corr.get('n_derrotas')} P)"
    )
    print(f"{'#':>2}  {'Metrica':<18} {'r':>6}  {'|r|':>5}  {'nivel':<10}  "
          f"{'G':>7}  {'P':>7}  {'dif':>7}  {'d':>5}")
    print("-" * 72)
    for row in corr.get("prioridad_proceso") or []:
        print(
            f"{row['orden']:>2}  {str(row['etiqueta']):<28} "
            f"{row['r']:>6.3f}  {abs(float(row['r'] or 0)):>5.3f}  "
            f"{str(row['nivel']):<10}  "
            f"{row.get('media_g', ''):>7}  {row.get('media_p', ''):>7}  "
            f"{row['diff_g_p']:>7}  {row['cohens_d'] if row['cohens_d'] is not None else '':>5}"
        )
    print()
    print("Referencia circular (margen ≈ resultado):")
    for m in corr.get("metricas") or []:
        if m.get("circular"):
            print(
                f"  {m['etiqueta']:<18} r={m['r']}  "
                f"G={m['media_g']}  P={m['media_p']}  d={m['cohens_d']}"
            )
    print()
    print("Cómo leer: |r|≥0.5 fuerte · ≥0.3 moderada · ≥0.1 débil")
    print("Cohen's d: diferencia tipificada G vs P (≈0.2 chica, 0.5 media, 0.8 grande)")
    print()


def imprimir_informe(res: Dict[str, object]) -> None:
    propio = res.get("propio") or {}
    rival = res.get("rival") or {}
    obj = res.get("objetivos_sugeridos") or {}
    print()
    print("=" * 64)
    print("LIGA FEDERAL MAYORES — FASE REGULAR METRO (A/B/C)")
    print("Promedios cuando el equipo GANA")
    print("=" * 64)
    print(f"Victorias con boxscore: {res.get('n_victorias')}  |  omitidos: {res.get('omitidos')}")
    print(f"Por grupo: {res.get('por_grupo')}")
    print()
    print("--- PROPIO (ofensiva / control) ---")
    print(f"  Posesiones       {propio.get('poss')}")
    print(f"  PTS anotados     {propio.get('pts')}")
    print(f"  2P (vol/%)       {propio.get('t2')}  ({propio.get('pct_2p')}%)")
    print(f"  3P (vol/%)       {propio.get('t3')}  ({propio.get('pct_3p')}%)")
    print(f"  TL (vol/%)       {propio.get('tl')}  ({propio.get('pct_tl')}%)")
    print(f"  FGA              {propio.get('fga')}")
    print(f"  RO               {propio.get('ro')}")
    print(f"  AST/PER          {propio.get('ast_per')}  (AST {propio.get('ast')} / PER {propio.get('per')})")
    print(f"  Recuperos        {propio.get('rec')}")
    print()
    print("--- RIVAL (lo que permiten los ganadores) ---")
    print(f"  Posesiones       {rival.get('poss')}")
    print(f"  PTS recibidos   {rival.get('pts_recibidos')}")
    print(f"  2P (vol/%)       {rival.get('t2')}  ({rival.get('pct_2p')}%)")
    print(f"  3P (vol/%)       {rival.get('t3')}  ({rival.get('pct_3p')}%)")
    print(f"  TL (vol/%)       {rival.get('tl')}  ({rival.get('pct_tl')}%)")
    print(f"  FGA              {rival.get('fga')}")
    print(f"  RO               {rival.get('ro')}")
    print(f"  Pérdidas         {rival.get('per')}")
    print()
    print("--- Objetivos sugeridos (redondeados) ---")
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--progress", action="store_true")
    ap.add_argument("--desde-cache", action="store_true")
    ap.add_argument("--force-boxscores", action="store_true")
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.desde_cache and PARTIDOS_CACHE.exists():
        partidos = json.loads(PARTIDOS_CACHE.read_text(encoding="utf-8"))
        if args.progress:
            print(f"Partidos desde caché: {len(partidos)}", file=sys.stderr)
    else:
        key = _load_widget_key()
        with (ROOT / "config" / "competencias.json").open(encoding="utf-8") as f:
            cfg = json.load(f)
        fecha_ini = cfg.get("fecha_inicio", "2022-1-1")
        fecha_fin = cfg.get("fecha_fin", "2026-12-30")
        ges = GesDeportivaExtractor(HttpClient(SessionProvider.get_session()))
        if args.progress:
            print("Recolectando partidos METRO fase regular…", file=sys.stderr)
        partidos = recolectar_partidos(
            ges,
            key=key,
            fecha_ini=fecha_ini,
            fecha_fin=fecha_fin,
            progress=args.progress,
        )
        PARTIDOS_CACHE.write_text(
            json.dumps(partidos, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    tokens = [str(p["id_partido"]) for p in partidos if p.get("id_partido")]
    boxscores = descargar_boxscores(
        tokens,
        workers=args.workers,
        progress=args.progress,
        force=args.force_boxscores,
    )
    res = promedios_victorias(partidos, boxscores)
    OUT_JSON.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    imprimir_informe(res)

    actuaciones = construir_actuaciones(partidos, boxscores)
    corr = correlaciones_victoria(actuaciones)
    OUT_CORR_JSON.write_text(
        json.dumps(corr, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    imprimir_correlaciones(corr)

    print(f"JSON promedios: {OUT_JSON}")
    print(f"JSON correlación: {OUT_CORR_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
