# -*- coding: utf-8 -*-
"""
Cumplimiento de plantilla por categoría y nivel (Formativas FeBAMBA 2026).

Reglas (temporada 2026, según pedido federación):
  Completar plantilla = jugadores en acta (min>0):
    U9/U11/U13: ≥12 cat+anterior con ≥6 de la categoría (6+6 … 12+0).
                 Máximo 15 en plantilla; todos deben jugar al menos un cuarto.
    U15: ≥10 jugadores de la categoría en acta.
    U17: ≥8 entre cat + anterior.
    U21: ≥5 jugadores.
  Reglas de juego (aparte, también se miden):
    U9/U11/U13: todos 10-20 min; sin cuartos consecutivos.
    U15: todos ≥10 min; sin repetir Q1 y Q2.

U7 (2019+) no está en el dataset actual (Mosquitos); se informa como N/D.

También analiza composición U21 vs banda U19 (2007-2008) y minutos por año.

Ejemplos:
  python analysis/cumplimiento_plantillas_formativas.py --progress
  python analysis/cumplimiento_plantillas_formativas.py --sin-pbp --progress
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.argbasket.pbp_reglas import fetch_y_analizar
from ingest.febamba.mini_masc_regla_plantilla import parse_minutos_a_segundos
from ingest.febamba.standings_2026 import clave_equipo, _elegir_nombre

PARTIDOS = ROOT / "outputs" / "nacimientos_formativas" / "partidos.json"
BOX_BUSC = ROOT / "outputs" / "buscador" / "boxscores_full.json"
BOX_NUEVOS = ROOT / "outputs" / "nacimientos_formativas" / "boxscores_nuevos.json"
FICHAS = ROOT / "outputs" / "buscador" / "jugadores_ficha.json"
PBP_U11 = ROOT / "outputs" / "formativas_2026" / "pbp_u11.json"
PBP_CACHE = ROOT / "outputs" / "cumplimiento" / "pbp_cache.json"
OUT_DIR = ROOT / "outputs" / "cumplimiento"
OUT_HTML = OUT_DIR / "cumplimiento_plantillas.html"
OUT_JSON = OUT_DIR / "cumplimiento_plantillas.json"
DOCS_HTML = ROOT / "docs" / "cumplimiento_plantillas_formativas.html"

# Años de la categoría (banda inclusiva).
BANDAS: Dict[str, Tuple[int, int]] = {
    "U7": (2019, 2022),   # 2019 para adelante (mosquitos)
    "U9": (2017, 2018),
    "U11": (2015, 2016),
    "U13": (2013, 2014),
    "U15": (2011, 2012),
    "U17": (2009, 2010),
    "U21": (2005, 2008),
}
# Categoría anterior (más chicos) que puede completar plantilla.
ANTERIOR: Dict[str, str] = {
    "U9": "U7",
    "U11": "U9",
    "U13": "U11",
    "U15": "U13",
    "U17": "U15",
}

# Cats en el dataset de partidos.
CATS_DATA = ("U9", "U11", "U13", "U15", "U17", "U21")
CATS_NEED_PBP = {"U9", "U11", "U13", "U15"}

FASE_NIVEL = {
    "INTERCONFERENCIA A": "Interconferencia A",
    "INTERCONFERENCIA B": "Interconferencia B",
    "NIVEL 1": "Nivel 1",
    "NIVEL 2": "Nivel 2",
    "NIVEL 3": "Nivel 3",
    "TORNEO DE CLASIFICACION": "Clasificatorio",
    "TORNEO RECLASIFICATORIO": "Reclasificación",
    "TORNEO RECLASIFICACION": "Reclasificación",
}

NIVELES_ORDEN = [
    "Interconferencia A",
    "Interconferencia B",
    "Nivel 1",
    "Nivel 2",
    "Nivel 3",
]

# Fuera del informe: 1ª fase y copas/LFF (no son los niveles de Segunda).
NIVELES_EXCLUIDOS = {"Clasificatorio", "Reclasificación", "Otro"}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def year_of(fnac: object) -> Optional[int]:
    s = ("" if fnac is None else str(fnac)).strip()
    for part in s.replace("-", "/").split("/"):
        if len(part) == 4 and part.isdigit():
            y = int(part)
            if 1990 <= y <= 2030:
                return y
    return None


def banda_de(anio: int) -> Optional[str]:
    for cat, (lo, hi) in BANDAS.items():
        if lo <= anio <= hi:
            return cat
    return None


def nivel_de_fase(fase: str) -> str:
    f = (fase or "").strip().upper()
    if f in FASE_NIVEL:
        return FASE_NIVEL[f]
    if "INTERCONFERENCIA A" in f:
        return "Interconferencia A"
    if "INTERCONFERENCIA B" in f:
        return "Interconferencia B"
    if f.startswith("NIVEL 1"):
        return "Nivel 1"
    if f.startswith("NIVEL 2"):
        return "Nivel 2"
    if f.startswith("NIVEL 3"):
        return "Nivel 3"
    if "CLASIFICACION" in f and "LFF" not in f and "RECLA" not in f:
        return "Clasificatorio"
    if "RECLASIFIC" in f:
        return "Reclasificación"
    # LFF / triangular / playoffs sueltos → fuera de los niveles de Segunda.
    if "LFF" in f or "TRIANGULAR" in f or "PLAYOFF" in f or "COPA" in f:
        return "Otro"
    return "Otro"


def cargar_boxes() -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for path in (BOX_BUSC, BOX_NUEVOS):
        if path.exists():
            out.update(json.loads(path.read_text(encoding="utf-8")))
    return out


def cargar_pbp(sin_pbp: bool, tokens: List[str], workers: int, progress: bool) -> Dict[str, dict]:
    cache: Dict[str, dict] = {}
    if PBP_U11.exists():
        cache.update(json.loads(PBP_U11.read_text(encoding="utf-8")))
    if PBP_CACHE.exists():
        cache.update(json.loads(PBP_CACHE.read_text(encoding="utf-8")))
    if sin_pbp:
        return cache
    pendientes = [t for t in dict.fromkeys(tokens) if t and t not in cache]
    if progress:
        log(f"PBP: {len(tokens)} pedidos, {len(cache)} en caché, {len(pendientes)} a bajar")
    if not pendientes:
        return cache
    PBP_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futs = {pool.submit(fetch_y_analizar, t): t for t in pendientes}
        done = 0
        for fut in as_completed(futs):
            tok = futs[fut]
            try:
                cache[tok] = fut.result()
            except Exception as exc:  # noqa: BLE001
                cache[tok] = {"tiene_pbp": False, "error": str(exc)}
            done += 1
            if progress and (done % 100 == 0 or done == len(pendientes)):
                log(f"  pbp {done}/{len(pendientes)}")
            if done % 250 == 0:
                PBP_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    PBP_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache


def jugadores_activos(eq: dict) -> List[dict]:
    out = []
    for j in eq.get("jugadores") or []:
        seg = parse_minutos_a_segundos(j.get("min")) or 0
        if seg <= 0:
            continue
        out.append(j)
    return out


def ids_consecutivos(pbp: Optional[dict], lado_nombre: str) -> Set[str]:
    """Identidades normalizadas de jugadores con cuartos consecutivos en ese equipo."""
    if not pbp or not pbp.get("tiene_pbp"):
        return set()
    from ingest.argbasket.pbp_reglas import _normaliza_nombre

    # Match por nombre de equipo aproximado: el PBP usa local/visitante labels.
    hits = set()
    for c in pbp.get("jugadores_consecutivos") or []:
        nom = c.get("nombre")
        if nom:
            hits.add(_normaliza_nombre(str(nom)))
    return hits


def ids_q1_q2(pbp: Optional[dict]) -> Set[str]:
    """Jugadores que aparecen en Q1 y Q2 (según eventos PBP)."""
    if not pbp or not pbp.get("tiene_pbp"):
        return set()
    from ingest.argbasket.pbp_reglas import _normaliza_nombre

    # Reusar estructura de consecutivos: pares que incluyen (1,2)
    hits = set()
    for c in pbp.get("jugadores_consecutivos") or []:
        pares = c.get("pares") or []
        if any(tuple(p) == (1, 2) or list(p) == [1, 2] for p in pares):
            nom = c.get("nombre")
            if nom:
                hits.add(_normaliza_nombre(str(nom)))
    return hits


def eval_equipo(
    *,
    cat: str,
    jugadores: List[dict],
    fichas: Dict[str, dict],
    pbp: Optional[dict],
) -> Dict[str, object]:
    """
    Evalúa completar plantilla y reglas de juego por separado.

    Completar (cupo en acta, min>0):
      U9/U11/U13: ≥12 cat+anterior con ≥6 de la categoría (6+6…12+0).
      U15: ≥10 de la categoría en acta.
      U17: ≥8 cat+anterior; U21: ≥5.

    Reglas de juego (no reducen el cupo; se reportan aparte):
      U9/U11/U13: todos 10-20 min; sin cuartos consecutivos (si hay PBP).
      U15: todos ≥10 min; sin Q1+Q2 (si hay PBP).
    """
    from ingest.argbasket.pbp_reglas import _normaliza_nombre

    min_seg = 10 * 60
    max_seg = 20 * 60

    consec_noms: Set[str] = set()
    q1q2_noms: Set[str] = set()
    tiene_pbp = bool(pbp and pbp.get("tiene_pbp"))
    if cat in ("U9", "U11", "U13") and tiene_pbp:
        for c in pbp.get("jugadores_consecutivos") or []:
            if c.get("nombre"):
                consec_noms.add(_normaliza_nombre(str(c["nombre"])))
    if cat == "U15" and tiene_pbp:
        q1q2_noms = ids_q1_q2(pbp)

    lo, hi = BANDAS[cat]
    prev = ANTERIOR.get(cat)
    prev_lo = prev_hi = None
    if prev:
        prev_lo, prev_hi = BANDAS[prev]

    n_en_acta = 0
    n_cat = 0
    n_prev = 0
    n_otros = 0
    sin_fnac = 0
    n_viola_min = 0
    n_viola_cuartos = 0
    anios: Counter = Counter()

    for j in jugadores:
        seg = parse_minutos_a_segundos(j.get("min")) or 0
        if seg <= 0:
            continue
        n_en_acta += 1
        pid = str(j.get("pid") or "").strip()
        anio = year_of((fichas.get(pid) or {}).get("fnac")) if pid else None
        nombre = (j.get("nombre_completo") or j.get("nombre") or "").strip()
        nn = _normaliza_nombre(nombre) if nombre else ""

        # Reglas de juego sobre todos los que figuran en acta con minutos.
        if cat in ("U9", "U11", "U13"):
            if seg < min_seg or seg > max_seg:
                n_viola_min += 1
            if nn and nn in consec_noms:
                n_viola_cuartos += 1
        elif cat == "U15":
            if seg < min_seg:
                n_viola_min += 1
            if nn and nn in q1q2_noms:
                n_viola_cuartos += 1

        if anio is None:
            sin_fnac += 1
            continue
        anios[anio] += 1

        if lo <= anio <= hi:
            n_cat += 1
        elif prev_lo is not None and prev_lo <= anio <= prev_hi:
            n_prev += 1
        else:
            n_otros += 1

    n_plantilla = n_cat + n_prev  # cupo para completar (acta cat+anterior)
    motivos: List[str] = []
    completa = True
    falla_menos_12 = False
    falla_composicion = False

    if cat in ("U9", "U11", "U13"):
        min_cat = 6
        if n_plantilla < 12:
            completa = False
            falla_menos_12 = True
            motivos.append(f"menos de 12 en acta cat+ant ({n_plantilla}: {n_cat} cat + {n_prev} ant)")
        elif n_cat < min_cat:
            completa = False
            falla_composicion = True
            motivos.append(f"composición {n_cat} cat + {n_prev} ant (mínimo {min_cat} de la categoría)")
    elif cat == "U15":
        min_cat = 10
        if n_cat < min_cat:
            completa = False
            # Misma bandera de “cupo insuficiente” que usa el informe.
            falla_menos_12 = True
            motivos.append(
                f"menos de {min_cat} de la categoría en acta ({n_cat} cat"
                f"{f' + {n_prev} ant' if n_prev else ''})"
            )
    elif cat == "U17":
        if n_plantilla < 8:
            completa = False
            falla_menos_12 = True
            motivos.append(f"menos de 8 cat+anterior ({n_plantilla})")
    elif cat == "U21":
        n_jug = sum(anios.values())
        if n_jug < 5:
            completa = False
            falla_menos_12 = True
            motivos.append(f"menos de 5 jugadores ({n_jug})")

    falla_minutos = n_viola_min > 0 and cat in ("U9", "U11", "U13", "U15")
    falla_cuartos = n_viola_cuartos > 0 and cat in ("U9", "U11", "U13", "U15")
    if falla_minutos:
        motivos.append(f"minutos fuera de regla ({n_viola_min} jugadores)")
    if falla_cuartos:
        motivos.append(f"cuartos (consec/Q1+Q2) ({n_viola_cuartos} jugadores)")

    cumple_reglas_juego = not falla_minutos and not falla_cuartos
    # "completa" = cupo/composición; "cumple" = plantilla + reglas de juego
    cumple = completa and cumple_reglas_juego

    return {
        "completa": completa,
        "cumple": cumple,
        "cumple_reglas_juego": cumple_reglas_juego,
        "motivos": motivos,
        "falla_menos_12": falla_menos_12,
        "falla_composicion": falla_composicion,
        "falla_minutos": falla_minutos,
        "falla_cuartos": falla_cuartos,
        "n_activos": n_en_acta,
        "n_elegibles": n_plantilla,
        "n_cat": n_cat,
        "n_prev": n_prev,
        "n_otros": n_otros,
        "n_viola_min": n_viola_min,
        "n_viola_cuartos": n_viola_cuartos,
        "sin_fnac": sin_fnac,
        "pbp": tiene_pbp,
        "anios": dict(anios),
    }


def analizar(
    *,
    sin_pbp: bool = False,
    workers: int = 12,
    progress: bool = False,
    solo_segunda: bool = False,
) -> dict:
    partidos = json.loads(PARTIDOS.read_text(encoding="utf-8"))
    fichas = json.loads(FICHAS.read_text(encoding="utf-8"))
    boxes = cargar_boxes()

    if solo_segunda:
        partidos = [
            p
            for p in partidos
            if nivel_de_fase(p.get("fase") or "")
            in {
                "Interconferencia A",
                "Interconferencia B",
                "Nivel 1",
                "Nivel 2",
                "Nivel 3",
            }
        ]

    tokens_pbp = [
        p["id_partido"]
        for p in partidos
        if p.get("categoria") in CATS_NEED_PBP
    ]
    pbp_map = cargar_pbp(sin_pbp, tokens_pbp, workers, progress)

    # acumuladores
    # cat -> nivel -> {equipo_games, no_completa, ...}
    stats = defaultdict(lambda: defaultdict(lambda: {
        "equipo_partidos": 0,
        "no_completa": 0,
        "no_cumple": 0,
        "menos_12": 0,
        "mala_composicion": 0,
        "falla_minutos": 0,
        "falla_cuartos": 0,
        "suma_acta": 0,  # jugadores con min>0
        "suma_plantilla": 0,  # cat + anterior con min>0
        "acta_lt12": 0,
        "acta_12_15": 0,  # inclusive
        "acta_gt15": 0,  # sobre máximo U9/U11/U13
        "sin_acta": 0,
        "sin_fnac_afecta": 0,
        "con_pbp": 0,
        "motivos": Counter(),
    }))
    # U21 extras
    u21_roster_sizes: List[int] = []
    u21_u19_counts: List[int] = []
    u21_u21only_counts: List[int] = []  # 2005-2006
    u21_seg_por_anio: Dict[int, List[int]] = defaultdict(list)
    u21_seg_por_anio_nivel: Dict[str, Dict[int, List[int]]] = defaultdict(
        lambda: defaultdict(list)
    )
    # (clave, nivel) -> slot de minutos / plantel en ese nivel
    u21_equipos: Dict[Tuple[str, str], dict] = {}
    # clave -> set(pid) únicos en la temporada
    u21_pids: Dict[str, Set[str]] = defaultdict(set)
    u21_pids_u19: Dict[str, Set[str]] = defaultdict(set)
    u21_pids_old: Dict[str, Set[str]] = defaultdict(set)

    nombres_por_clave: Dict[str, set] = defaultdict(set)
    n_eval = 0

    for p in partidos:
        cat = p.get("categoria") or ""
        if cat not in CATS_DATA:
            continue
        nivel = nivel_de_fase(p.get("fase") or "")
        if nivel in NIVELES_EXCLUIDOS:
            continue
        box = boxes.get(p["id_partido"])
        if not box or not box.get("ok"):
            for _ in (0, 1):
                stats[cat][nivel]["sin_acta"] += 1
            continue
        equipos = box.get("equipos") or []
        lados = [
            (p.get("local") or "", equipos[0] if len(equipos) > 0 else None),
            (p.get("visitante") or "", equipos[1] if len(equipos) > 1 else None),
        ]
        pbp = pbp_map.get(p["id_partido"])
        for nombre_fix, eq in lados:
            if not eq:
                stats[cat][nivel]["sin_acta"] += 1
                continue
            raw = (eq.get("nombre") or nombre_fix or "").strip()
            clave = clave_equipo(raw) if raw else "?"
            if raw:
                nombres_por_clave[clave].add(raw)
            activos = jugadores_activos(eq)
            # minutos por año (U21)
            if cat == "U21":
                anios_eq: Counter = Counter()
                for j in activos:
                    pid = str(j.get("pid") or "").strip()
                    anio = year_of((fichas.get(pid) or {}).get("fnac")) if pid else None
                    seg = parse_minutos_a_segundos(j.get("min")) or 0
                    if anio is None:
                        continue
                    anios_eq[anio] += 1
                    u21_seg_por_anio[anio].append(seg)
                    if 2005 <= anio <= 2008:
                        u21_seg_por_anio_nivel[nivel][anio].append(seg)
                n_u19 = sum(anios_eq[y] for y in (2007, 2008))
                n_old = sum(anios_eq[y] for y in (2005, 2006))
                n_tot = sum(anios_eq.values())
                u21_roster_sizes.append(n_tot)
                u21_u19_counts.append(n_u19)
                u21_u21only_counts.append(n_old)
                slot = u21_equipos.setdefault(
                    (clave, nivel),
                    {
                        "clave": clave,
                        "nivel": nivel,
                        "anios": Counter(),
                        "seg": defaultdict(list),
                        "pids_por_anio": defaultdict(set),
                        "partidos": 0,
                        "nombres": set(),
                    },
                )
                slot["partidos"] += 1
                slot["nombres"].add(raw)
                for y, c in anios_eq.items():
                    slot["anios"][y] += c
                for j in activos:
                    pid = str(j.get("pid") or "").strip()
                    anio = year_of((fichas.get(pid) or {}).get("fnac")) if pid else None
                    seg = parse_minutos_a_segundos(j.get("min")) or 0
                    if anio is not None:
                        slot["seg"][anio].append(seg)
                        if pid and 2005 <= anio <= 2008:
                            slot["pids_por_anio"][anio].add(pid)
                    if pid and anio is not None and 2005 <= anio <= 2008:
                        u21_pids[clave].add(pid)
                        if anio in (2007, 2008):
                            u21_pids_u19[clave].add(pid)
                        else:
                            u21_pids_old[clave].add(pid)

            ev = eval_equipo(cat=cat, jugadores=activos, fichas=fichas, pbp=pbp)
            st = stats[cat][nivel]
            st["equipo_partidos"] += 1
            n_act = int(ev.get("n_activos") or 0)
            st["suma_acta"] += n_act
            st["suma_plantilla"] += int(ev.get("n_elegibles") or 0)
            if n_act < 12:
                st["acta_lt12"] += 1
            elif n_act <= 15:
                st["acta_12_15"] += 1
            else:
                st["acta_gt15"] += 1
            n_eval += 1
            if ev["pbp"]:
                st["con_pbp"] += 1
            if ev["sin_fnac"] and not ev["completa"]:
                st["sin_fnac_afecta"] += 1
            if not ev["completa"]:
                st["no_completa"] += 1
                if ev.get("falla_menos_12"):
                    st["menos_12"] += 1
                if ev.get("falla_composicion"):
                    st["mala_composicion"] += 1
            if not ev.get("cumple", ev["completa"]):
                st["no_cumple"] += 1
            if ev.get("falla_minutos"):
                st["falla_minutos"] += 1
            if ev.get("falla_cuartos"):
                st["falla_cuartos"] += 1
            if not ev["completa"] or ev.get("falla_minutos") or ev.get("falla_cuartos"):
                for m in ev["motivos"]:
                    if m.startswith("menos de 12") or m.startswith("menos de 8") or m.startswith("menos de 5"):
                        key = "menos del mínimo de plantilla"
                    elif m.startswith("composición"):
                        key = "composición insuficiente"
                    elif m.startswith("minutos"):
                        key = "minutos fuera de regla"
                    elif m.startswith("cuartos"):
                        key = "cuartos (consec/Q1+Q2)"
                    else:
                        key = m.split(" (")[0]
                    st["motivos"][key] += 1

    # armar tablas pct
    tablas = {}
    for cat in CATS_DATA:
        filas = []
        tot_ep = tot_nc = tot_m12 = tot_comp = tot_min = tot_cua = tot_cum = 0
        tot_suma_acta = tot_suma_pl = 0
        tot_lt12 = tot_12_15 = tot_gt15 = 0
        for nivel in NIVELES_ORDEN:
            st = stats[cat].get(nivel)
            if not st or st["equipo_partidos"] <= 0:
                continue
            ep = st["equipo_partidos"]
            nc = st["no_completa"]
            m12 = st["menos_12"]
            comp = st["mala_composicion"]
            fmin = st["falla_minutos"]
            fcua = st["falla_cuartos"]
            ncum = st["no_cumple"]
            suma_acta = st["suma_acta"]
            suma_pl = st["suma_plantilla"]
            a_lt12 = st["acta_lt12"]
            a_12_15 = st["acta_12_15"]
            a_gt15 = st["acta_gt15"]
            tot_ep += ep
            tot_nc += nc
            tot_m12 += m12
            tot_comp += comp
            tot_min += fmin
            tot_cua += fcua
            tot_cum += ncum
            tot_suma_acta += suma_acta
            tot_suma_pl += suma_pl
            tot_lt12 += a_lt12
            tot_12_15 += a_12_15
            tot_gt15 += a_gt15
            filas.append({
                "nivel": nivel,
                "equipo_partidos": ep,
                "no_completa": nc,
                "pct_no_completa": round(100.0 * nc / ep, 1),
                "menos_12": m12,
                "pct_menos_12": round(100.0 * m12 / ep, 1),
                "mala_composicion": comp,
                "pct_mala_composicion": round(100.0 * comp / ep, 1),
                "falla_minutos": fmin,
                "pct_falla_minutos": round(100.0 * fmin / ep, 1),
                "falla_cuartos": fcua,
                "pct_falla_cuartos": round(100.0 * fcua / ep, 1),
                "no_cumple": ncum,
                "pct_no_cumple": round(100.0 * ncum / ep, 1),
                "prom_acta": round(suma_acta / ep, 2),
                "prom_plantilla": round(suma_pl / ep, 2),
                "pct_acta_lt12": round(100.0 * a_lt12 / ep, 1),
                "pct_acta_12_15": round(100.0 * a_12_15 / ep, 1),
                "pct_acta_gt15": round(100.0 * a_gt15 / ep, 1),
                "con_pbp": st["con_pbp"],
                "sin_acta": st["sin_acta"],
                "motivos": st["motivos"].most_common(8),
            })
        if tot_ep:
            filas.append({
                "nivel": "TOTAL",
                "equipo_partidos": tot_ep,
                "no_completa": tot_nc,
                "pct_no_completa": round(100.0 * tot_nc / tot_ep, 1),
                "menos_12": tot_m12,
                "pct_menos_12": round(100.0 * tot_m12 / tot_ep, 1),
                "mala_composicion": tot_comp,
                "pct_mala_composicion": round(100.0 * tot_comp / tot_ep, 1),
                "falla_minutos": tot_min,
                "pct_falla_minutos": round(100.0 * tot_min / tot_ep, 1),
                "falla_cuartos": tot_cua,
                "pct_falla_cuartos": round(100.0 * tot_cua / tot_ep, 1),
                "no_cumple": tot_cum,
                "pct_no_cumple": round(100.0 * tot_cum / tot_ep, 1),
                "prom_acta": round(tot_suma_acta / tot_ep, 2),
                "prom_plantilla": round(tot_suma_pl / tot_ep, 2),
                "pct_acta_lt12": round(100.0 * tot_lt12 / tot_ep, 1),
                "pct_acta_12_15": round(100.0 * tot_12_15 / tot_ep, 1),
                "pct_acta_gt15": round(100.0 * tot_gt15 / tot_ep, 1),
                "con_pbp": sum(stats[cat][n]["con_pbp"] for n in NIVELES_ORDEN if n in stats[cat]),
                "sin_acta": sum(stats[cat][n]["sin_acta"] for n in NIVELES_ORDEN if n in stats[cat]),
                "motivos": [],
            })
        tablas[cat] = filas

    def avg(xs: List[int]) -> Optional[float]:
        return round(sum(xs) / len(xs), 1) if xs else None

    def _min_stats(segs: List[int], n_jugadores: Optional[int] = None) -> dict:
        """prom = minutos promedio por aparición; n = jugadores únicos."""
        return {
            "n": int(n_jugadores) if n_jugadores is not None else len(segs),
            "n_apariciones": len(segs),
            "prom": round((sum(segs) / len(segs)) / 60.0, 2) if segs else None,
        }

    u21_min_por_anio = {
        str(y): {
            "n_apariciones": len(segs),
            "min_promedio": round((sum(segs) / len(segs)) / 60.0, 2) if segs else None,
        }
        for y, segs in sorted(u21_seg_por_anio.items())
        if 2005 <= y <= 2008
    }
    u21_min_por_nivel: Dict[str, dict] = {}
    for niv, by_y in u21_seg_por_anio_nivel.items():
        u21_min_por_nivel[niv] = {
            str(y): _min_stats(by_y[y])
            for y in (2005, 2006, 2007, 2008)
            if by_y.get(y)
        }

    # equipos U21 por nivel (fila = equipo en un nivel)
    nivel_rank = {n: i for i, n in enumerate(NIVELES_ORDEN)}
    equipos_u21 = []
    nombres_por_clave_u21: Dict[str, set] = defaultdict(set)
    for (clave, nivel), slot in u21_equipos.items():
        anios = slot["anios"]
        n_u19 = anios[2007] + anios[2008]
        n_old = anios[2005] + anios[2006]
        pj = max(1, slot["partidos"])
        prom_roster = round(sum(anios.values()) / pj, 1)
        prom_u19 = round(n_u19 / pj, 1)
        prom_old = round(n_old / pj, 1)
        min_por_anio = {
            str(y): _min_stats(
                slot["seg"][y],
                n_jugadores=len(slot["pids_por_anio"].get(y) or ()),
            )
            for y in (2005, 2006, 2007, 2008)
            if slot["seg"].get(y)
        }
        nombres_por_clave_u21[clave] |= set(slot["nombres"])
        equipos_u21.append({
            "clave": clave,
            "equipo": _elegir_nombre(slot["nombres"], clave),
            "nivel": nivel,
            "partidos": slot["partidos"],
            "prom_jugadores_por_partido": prom_roster,
            "prom_u19_2007_2008": prom_u19,
            "prom_2005_2006": prom_old,
            "pct_u19": round(100.0 * n_u19 / max(1, n_u19 + n_old), 1),
            "min_por_anio": min_por_anio,
        })
    equipos_u21.sort(
        key=lambda e: (
            nivel_rank.get(e["nivel"], 99),
            e["equipo"],
        )
    )

    planteles_u21 = []
    for clave, pids in u21_pids.items():
        n = len(pids)
        n19 = len(u21_pids_u19.get(clave) or ())
        nold = len(u21_pids_old.get(clave) or ())
        planteles_u21.append({
            "equipo": _elegir_nombre(nombres_por_clave_u21.get(clave) or {clave}, clave),
            "plantel_unico": n,
            "u19_unicos": n19,
            "y2005_2006_unicos": nold,
            "pct_u19": round(100.0 * n19 / max(1, n19 + nold), 1),
        })
    planteles_u21.sort(key=lambda e: (-e["plantel_unico"], e["equipo"]))
    n_plant_15 = sum(1 for e in planteles_u21 if e["plantel_unico"] >= 15)

    payload = {
        "fecha": date.today().strftime("%d/%m/%Y"),
        "n_partidos": len(partidos),
        "n_evaluaciones": n_eval,
        "solo_segunda": solo_segunda,
        "sin_pbp": sin_pbp,
        "bandas": {k: list(v) for k, v in BANDAS.items()},
        "reglas": {
            "U9/U11/U13": "Completar: ≥12 en acta cat+anterior con ≥6 de la categoría (6+6…12+0). Máximo 15 en plantilla; todos deben jugar un cuarto. Juego: 10-20 min; sin cuartos consecutivos",
            "U15": "Completar: ≥10 jugadores de la categoría en acta. Juego: todos ≥10 min; sin Q1+Q2",
            "U17": "Completar: ≥8 entre categoría y anterior (minutos > 0)",
            "U21": "Completar: ≥5 jugadores con minutos > 0",
            "U7": "Sin partidos en dataset (Mosquitos no relevado)",
        },
        "tablas": tablas,
        "u21": {
            "n_equipo_partidos": len(u21_roster_sizes),
            "prom_jugadores": avg(u21_roster_sizes),
            "prom_u19": avg(u21_u19_counts),
            "prom_2005_2006": avg(u21_u21only_counts),
            "pct_partidos_15plus": round(
                100.0 * sum(1 for n in u21_roster_sizes if n >= 15) / max(1, len(u21_roster_sizes)),
                1,
            ),
            "pct_partidos_u19_mayoria": round(
                100.0
                * sum(
                    1
                    for a, b in zip(u21_u19_counts, u21_u21only_counts)
                    if a > b
                )
                / max(1, len(u21_u19_counts)),
                1,
            ),
            "n_equipos": len(planteles_u21),
            "pct_equipos_plantel_15plus": round(
                100.0 * n_plant_15 / max(1, len(planteles_u21)), 1
            ),
            "planteles_15plus": [e for e in planteles_u21 if e["plantel_unico"] >= 15],
            "minutos_por_anio": u21_min_por_anio,
            "minutos_por_anio_por_nivel": u21_min_por_nivel,
            "anios": [2005, 2006, 2007, 2008],
            "niveles": [
                n
                for n in NIVELES_ORDEN
                if any(e["nivel"] == n for e in equipos_u21)
            ],
            "equipos": equipos_u21,
            "planteles": planteles_u21,
        },
        "notas": [
            "Unidad de análisis: equipo-partido (local y visitante cuentan aparte).",
            "Solo Segunda fase (Interconferencia A/B y Niveles 1–3); se excluyen Clasificatorio, Reclasificación y LFF/playoffs.",
            "U9/U11/U13: completar = ≥12 en acta cat+anterior con ≥6 de la categoría (6+6…12+0).",
            "U15: completar = ≥10 jugadores de la categoría en acta (min>0).",
            "Prom. en acta = promedio de jugadores con minutos > 0 por equipo-partido (comparar entre niveles).",
            "U9/U11/U13: plantilla máxima 15; todos deben jugar al menos un cuarto.",
            "Minutos y cuartos son reglas de juego aparte: no restan del cupo; se informan en columnas propias.",
            "Categoría anterior = banda etaria más chica (ej. U13←U11, U11←U9, U9←U7/2019+).",
            "U17/U21: sin mínimos individuales de minutos; se cuentan jugadores con minutos > 0.",
            "Cuartos consecutivos / Q1-Q2 solo se evalúan si hay play-by-play del partido.",
            "U7 (Mosquitos) no está en el corpus de partidos descargado.",
        ],
    }
    return payload


def _pct_cell(v: float) -> str:
    if v >= 40:
        cls = "bad"
    elif v >= 20:
        cls = "mid"
    else:
        cls = "ok"
    return f'<td class="num {cls}">{v:.1f}%</td>'


def render_html(payload: dict) -> str:
    fecha = payload["fecha"]
    bloques = []
    for cat in CATS_DATA:
        filas = payload["tablas"].get(cat) or []
        if not filas:
            continue
        rows = []
        for f in filas:
            strong = " total" if f["nivel"] == "TOTAL" else ""
            rows.append(
                f"<tr class='{strong}'><td>{f['nivel']}</td>"
                f"<td class='num'>{f['equipo_partidos']}</td>"
                f"<td class='num'>{f.get('prom_acta') or '—'}</td>"
                f"<td class='num'>{f['no_completa']}</td>"
                f"{_pct_cell(f['pct_no_completa'])}"
                f"{_pct_cell(f.get('pct_menos_12') or 0)}"
                f"{_pct_cell(f.get('pct_mala_composicion') or 0)}"
                f"{_pct_cell(f.get('pct_falla_minutos') or 0)}"
                f"{_pct_cell(f.get('pct_falla_cuartos') or 0)}"
                f"<td class='num'>{f['con_pbp']}</td></tr>"
            )
        if cat in ("U9", "U11", "U13"):
            regla = payload["reglas"]["U9/U11/U13"]
        else:
            regla = payload["reglas"].get(cat, "")
        bloques.append(
            f"<section class='card'><h3>{cat} "
            f"<small>({BANDAS[cat][0]}-{BANDAS[cat][1]})</small></h3>"
            f"<p class='rule'>{regla}</p>"
            "<table><thead><tr><th>Nivel</th><th>Equipo-partidos</th>"
            "<th>Prom. en acta</th>"
            "<th>No completa</th><th>% no completa</th>"
            "<th>% &lt;12 en acta</th><th>% mala composición</th>"
            "<th>% viola minutos</th><th>% viola cuartos</th>"
            "<th>Con PBP</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></section>"
        )

    u21 = payload["u21"]
    min_rows = "".join(
        f"<tr><td>{y}</td><td class='num'>{d['n_apariciones']}</td>"
        f"<td class='num'>{d['min_promedio']}</td></tr>"
        for y, d in (u21.get("minutos_por_anio") or {}).items()
    )
    eq_rows = "".join(
        f"<tr><td>{e['equipo']}</td><td class='num'>{e['partidos']}</td>"
        f"<td class='num'>{e['prom_jugadores_por_partido']}</td>"
        f"<td class='num'>{e['prom_u19_2007_2008']}</td>"
        f"<td class='num'>{e['prom_2005_2006']}</td>"
        f"<td class='num'>{e['pct_u19']}%</td></tr>"
        for e in (u21.get("equipos") or [])[:40]
    )
    notas = "".join(f"<li>{n}</li>" for n in payload.get("notas") or [])

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Cumplimiento de plantillas · Formativas 2026</title>
<style>
:root {{ --bg:#f4f7fb; --ink:#0f172a; --muted:#64748b; --line:#dbe3ee; --ok:#166534; --mid:#a16207; --bad:#991b1b; }}
body {{ margin:0; font-family: "Segoe UI", system-ui, sans-serif; background:var(--bg); color:var(--ink); }}
.wrap {{ max-width:1100px; margin:0 auto; padding:28px 18px 60px; }}
h1 {{ font-size:1.6rem; margin:0 0 6px; }}
h2 {{ margin:28px 0 10px; font-size:1.25rem; }}
h3 {{ margin:0 0 8px; }}
.lede {{ color:var(--muted); margin:0 0 18px; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; margin:16px 0 22px; }}
.kpi {{ background:#fff; border:1px solid var(--line); border-radius:12px; padding:12px 14px; }}
.kpi b {{ display:block; font-size:1.25rem; }}
.kpi span {{ font-size:.78rem; color:var(--muted); }}
.card {{ background:#fff; border:1px solid var(--line); border-radius:14px; padding:14px 16px; margin:0 0 14px; }}
.rule {{ color:var(--muted); font-size:.85rem; margin:0 0 10px; }}
table {{ width:100%; border-collapse:collapse; font-size:.9rem; }}
th, td {{ padding:7px 8px; border-bottom:1px solid var(--line); text-align:left; }}
th {{ font-size:.75rem; color:var(--muted); text-transform:uppercase; letter-spacing:.03em; }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
tr.total td {{ font-weight:700; background:#f8fafc; }}
td.ok {{ color:var(--ok); font-weight:600; }}
td.mid {{ color:var(--mid); font-weight:600; }}
td.bad {{ color:var(--bad); font-weight:600; }}
ul.notes {{ color:var(--muted); font-size:.88rem; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Cumplimiento de plantillas por nivel</h1>
  <p class="lede">Formativas FeBAMBA 2026 · actualizado {fecha} ·
  {payload['n_partidos']} partidos · {payload['n_evaluaciones']} equipo-partidos evaluados
  {"· solo segunda fase" if payload.get("solo_segunda") else ""}.</p>

  <div class="kpis">
    <div class="kpi"><b>{u21.get('prom_jugadores') or '—'}</b><span>U21 · jugadores promedio por partido</span></div>
    <div class="kpi"><b>{u21.get('prom_u19') or '—'}</b><span>U21 · promedio nacidos 2007-2008 (U19)</span></div>
    <div class="kpi"><b>{u21.get('pct_equipos_plantel_15plus')}%</b><span>U21 · equipos con plantel único ≥15</span></div>
    <div class="kpi"><b>{u21.get('pct_partidos_u19_mayoria')}%</b><span>U21 · partidos con mayoría U19</span></div>
  </div>

  <h2>Porcentaje de equipo-partidos que no completan</h2>
  {''.join(bloques)}

  <h2>U21 · ¿tiene sentido una U19?</h2>
  <section class="card">
    <p class="rule">Banda U21 = 2005-2008. Se toma U19 = 2007-2008. Minutos promedio por aparición en acta.</p>
    <table>
      <thead><tr><th>Año nacimiento</th><th>Apariciones</th><th>Minutos promedio</th></tr></thead>
      <tbody>{min_rows}</tbody>
    </table>
  </section>
  <section class="card">
    <h3>Plantel único de temporada U21 (jugadores distintos con minutos)</h3>
    <table>
      <thead><tr><th>Equipo</th><th>Plantel</th><th>U19 (07-08)</th><th>2005-06</th><th>% U19</th></tr></thead>
      <tbody>{''.join(
        f"<tr><td>{e['equipo']}</td><td class='num'>{e['plantel_unico']}</td>"
        f"<td class='num'>{e['u19_unicos']}</td><td class='num'>{e['y2005_2006_unicos']}</td>"
        f"<td class='num'>{e['pct_u19']}%</td></tr>"
        for e in (u21.get('planteles') or [])[:40]
      )}</tbody>
    </table>
  </section>
  <section class="card">
    <h3>Equipos U21 (promedio por partido)</h3>
    <table>
      <thead><tr><th>Equipo</th><th>PJ</th><th>Jug/partido</th><th>U19</th><th>2005-06</th><th>% U19</th></tr></thead>
      <tbody>{eq_rows}</tbody>
    </table>
  </section>

  <h2>Notas</h2>
  <ul class="notes">{notas}</ul>
</div>
</body>
</html>"""


def main() -> int:
    p = argparse.ArgumentParser(description="Cumplimiento plantillas formativas")
    p.add_argument("--progress", action="store_true")
    p.add_argument("--sin-pbp", action="store_true", help="No descarga PBP nuevo")
    p.add_argument("--solo-segunda", action="store_true", help="Solo Inter A/B y Niveles 1-3")
    p.add_argument("--workers", type=int, default=12)
    p.add_argument("--publicar-docs", action="store_true")
    args = p.parse_args()

    payload = analizar(
        sin_pbp=args.sin_pbp,
        workers=args.workers,
        progress=args.progress,
        solo_segunda=args.solo_segunda,
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html = render_html(payload)
    OUT_HTML.write_text(html, encoding="utf-8")
    docs = None
    if args.publicar_docs:
        DOCS_HTML.write_text(html, encoding="utf-8")
        docs = str(DOCS_HTML)

    resumen = {
        cat: next((f for f in filas if f["nivel"] == "TOTAL"), None)
        for cat, filas in payload["tablas"].items()
    }
    print(
        json.dumps(
            {
                "html": str(OUT_HTML),
                "json": str(OUT_JSON),
                "docs": docs,
                "totales": {
                    cat: {
                        "pct_no_completa": (t or {}).get("pct_no_completa"),
                        "pct_menos_12": (t or {}).get("pct_menos_12"),
                        "pct_mala_composicion": (t or {}).get("pct_mala_composicion"),
                        "pct_falla_minutos": (t or {}).get("pct_falla_minutos"),
                        "pct_falla_cuartos": (t or {}).get("pct_falla_cuartos"),
                        "prom_acta": (t or {}).get("prom_acta"),
                        "equipo_partidos": (t or {}).get("equipo_partidos"),
                    }
                    for cat, t in resumen.items()
                },
                "u21": {
                    "prom_jugadores": payload["u21"]["prom_jugadores"],
                    "prom_u19": payload["u21"]["prom_u19"],
                    "pct_15plus": payload["u21"]["pct_partidos_15plus"],
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
