# -*- coding: utf-8 -*-
"""
Proyecta los 6 niveles FeBAMBA 2027 a partir del rendimiento de Fase 2 2026.

Entrada:
  docs/formativas_2026_tabla_posiciones.html  (tablas por zona)
  outputs/viajes_elite42/mapeo_clubes.csv     (sedes / región)

Salida:
  data/niveles_2027.json
  outputs/viajes_elite42/niveles_2027_movilidad.json  (detalle + status)

Reglas de cupo / movilidad 2027:
  Equivalencia: N1↔Inter A, N2↔Inter B, N3↔GES N1, N4↔GES N2, N5↔GES N3, N6 nuevo.
  Nadie desciende más de 1 nivel respecto de esa equivalencia.
  - Inter A: bajan últimos 2/grupo (8) → N2
  - Inter B: suben 2/grupo a N1 (8); bajan 2/grupo a N3 (8)
  - GES Nivel 1: suben 2/región a N2 (8); al menos 2/región permanecen en N3;
    el resto entra al pool regional N3–N6
  - N3–N6: ranking regional (objetivo 8/región) con tope de 1 descenso

  python analysis/calcular_niveles_2027.py
  python analysis/calcular_niveles_2027.py --inyectar-badges
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.febamba.standings_2026 import clave_equipo

STANDINGS_HTML = ROOT / "docs" / "formativas_2026_tabla_posiciones.html"
STANDINGS_OUT = ROOT / "outputs" / "formativas_2026" / "tabla_posiciones.html"
MAPEO_CSV = ROOT / "outputs" / "viajes_elite42" / "mapeo_clubes.csv"
OUT_JSON = ROOT / "data" / "niveles_2027.json"
OUT_DETALLE = ROOT / "outputs" / "viajes_elite42" / "niveles_2027_movilidad.json"

REGIONES = ("NORTE", "CENTRO", "SUR", "OESTE")

# Equivalencia 2026 → cupo 2027 (un nivel = un escalón en esta escala).
# N6 es nuevo: solo puede recibir a quien equivalía a N5 (GES Nivel 3) o inferior.
ORIGEN_EQUIV = {
    "INTERCONFERENCIA_A": 1,
    "INTERCONFERENCIA_B": 2,
    "NIVEL_1": 3,
    "NIVEL_2": 4,
    "NIVEL_3": 5,
    "RECLASIFICACION": 5,
    "CLASIFICACION": 6,
}
MAX_DESCENSO = 1  # nadie baja más de un nivel respecto de su equivalencia

# Base: con N equipos en GES Nivel 1, D descensos = N - 24 para dejar N3 en 32
# (N - 8 ascienden a N2 - D + 8 de Inter B + 8 de N4 = 32 ⇒ D = N - 24).
DESCENSOS_N3_BASE = {"NORTE": 4, "SUR": 4, "CENTRO": 3, "OESTE": 2}  # suma 13 (N=37)
ASCENSOS_N3_A_N2 = 2
# Mínimo de equipos del GES Nivel 1 2026 que permanecen en N3 2027, por región.
MIN_STAY_N3_FROM_GES_N1 = 2
ASCENSOS_N4_A_N3 = 2
TARGET_N3 = 32
CUPO_REGIONAL = 8  # N3–N5: objetivo 8 por región (32/nivel)

# Ajustes de región para el armado 2027 (clave_equipo → región).
# No cambian el nivel competitivo; solo la zona geográfica 2027.
REGION_OVERRIDES_2027: Dict[str, str] = {
    clave_equipo("FERROCARRIL OESTE NARANJA"): "CENTRO",
    clave_equipo("EL TALAR"): "CENTRO",
    clave_equipo("SAN ANDRES"): "NORTE",
    clave_equipo("17 DE AGOSTO"): "CENTRO",
    clave_equipo("PINOCHO VERDE"): "CENTRO",
    clave_equipo("COLEGIALES NEGRO"): "CENTRO",
    clave_equipo("ITALIANO DE JOSE C PAZ"): "NORTE",
    clave_equipo("SAN MIGUEL BLANCO"): "NORTE",
    clave_equipo("PORTENO ATLETICO CLUB BLANCO B"): "NORTE",
    clave_equipo("UNIVERSIDAD DE BUENOS AIRES"): "CENTRO",
    clave_equipo("VELEZ SARSFIELD AZUL - B"): "CENTRO",
}

# Forzar nivel 2027 (clave → nivel). Se aplica antes del reequilibrio 8/región.
NIVEL_OVERRIDES_2027: Dict[str, int] = {
    clave_equipo("VELEZ SARSFIELD AZUL - B"): 3,
    clave_equipo("CLUB ATLETICO HURACAN DE PARQUE PATRICIOS"): 4,
}

# Bandas de permanencia / descenso en tabla regional N4 (pos 1-indexed).
N4_STAY = {
    "NORTE": (3, 6),
    "SUR": (3, 6),
    "CENTRO": (3, 6),
    "OESTE": (3, 8),
}
N4_DESC = {
    "NORTE": (7, 15),
    "SUR": (7, 16),
    "CENTRO": (7, 8),
    "OESTE": (9, 16),
}


def _plan_descensos_n3(n_nivel1: int) -> Tuple[Dict[str, int], int]:
    """
    Devuelve (descensos_por_región, ascensos_centro_desde_abajo).

    Objetivo: N3_2027 = 32. Centro baja 3 si hace falta D=13; si D=12, Centro baja 2
    y se compensan 2 plazas de N4 Centro desde el remanente.
    """
    d_objetivo = max(0, n_nivel1 - 24)  # N - 8 + 16 - 32
    desc = dict(DESCENSOS_N3_BASE)
    total_base = sum(desc.values())  # 13
    if d_objetivo <= total_base - 1:
        # Preferir Centro 2 cuando alcanza (caso N=36 → D=12)
        desc["CENTRO"] = 2
        centro_from_below = 2  # 2 (N3) + 4 (stay) + 2 = 8
    else:
        desc["CENTRO"] = 3
        centro_from_below = 1  # 3 + 4 + 1 = 8
    # Ajuste fino si aún no cierra
    while sum(desc.values()) > d_objetivo and desc["CENTRO"] > 0:
        desc["CENTRO"] -= 1
        centro_from_below = 8 - desc["CENTRO"] - 4  # stay centro = 4
        centro_from_below = max(0, centro_from_below)
    while sum(desc.values()) < d_objetivo:
        # Agregar al Sur (más chico relativo / más equipos en GES)
        desc["SUR"] += 1
    return desc, centro_from_below


def _load_standings(path: Path = STANDINGS_HTML) -> dict:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"const DATA = (\{.*?\});\s*\n", text, re.S)
    if not m:
        raise RuntimeError(f"No se encontró DATA en {path}")
    return json.loads(m.group(1))


def _region_desde_zona(zona: str) -> str:
    return (zona or "").split()[0].upper()


def _mapa_regiones(data: dict) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for fase in (
        "CLASIFICACION",
        "RECLASIFICACION",
        "NIVEL_1",
        "NIVEL_2",
        "NIVEL_3",
    ):
        for zona, rows in data["tablas"].get(fase, {}).items():
            reg = _region_desde_zona(zona)
            if reg not in REGIONES:
                continue
            for row in rows:
                out[clave_equipo(row["equipo"])] = reg
    if MAPEO_CSV.exists():
        with MAPEO_CSV.open(encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                reg = _region_desde_zona(r.get("zona") or "")
                if not reg:
                    continue
                out[clave_equipo(r["equipo"])] = reg
                if r.get("clave"):
                    out[clave_equipo(r["clave"])] = reg
    return out


def _aplicar_overrides_y_reequilibrar_nivel(
    equipos: List[dict],
    *,
    cupo: Optional[int] = CUPO_REGIONAL,
    strict: bool = True,
) -> List[dict]:
    """
    Aplica REGION_OVERRIDES_2027 y, si `cupo` no es None, reequilibra a ese
    cupo por región cuando se puede.

    Los equipos con override fijo no se mueven a otra región. Si una región queda
    sobrecargada, se reasignan equipos sin override hacia regiones con cupo libre.
    """
    fixed = set(REGION_OVERRIDES_2027.keys())
    for e in equipos:
        ck = e.get("clave") or clave_equipo(e.get("equipo") or "")
        e["clave"] = ck
        if ck in REGION_OVERRIDES_2027:
            nueva = REGION_OVERRIDES_2027[ck]
            if e.get("region") != nueva:
                prev = e.get("region")
                e["region"] = nueva
                extra = f" · región 2027 {prev}→{nueva} (ajuste)"
                det = e.get("detalle") or ""
                if extra.strip() not in det:
                    e["detalle"] = det + extra

    if cupo is None:
        return equipos

    def _counts() -> Counter:
        return Counter(e.get("region") for e in equipos if e.get("region") in REGIONES)

    # Hasta 3* N ciclos (suficiente para vaciar sobrantes).
    for _ in range(len(equipos) * 3 + 1):
        c = _counts()
        overs = [r for r in REGIONES if c[r] > cupo]
        unders = [r for r in REGIONES if c[r] < cupo]
        if not overs:
            break
        if not unders:
            break
        moved = False
        for src in sorted(overs, key=lambda r: -c[r]):
            cands = [
                e
                for e in equipos
                if e.get("region") == src and (e.get("clave") or "") not in fixed
            ]
            if not cands:
                continue
            # Mover el de peor posición / nombre (menor impacto competitivo percibido).
            victim = max(
                cands,
                key=lambda e: (
                    int(e.get("pos_2026") or 99),
                    str(e.get("equipo") or ""),
                ),
            )
            dst = min(unders, key=lambda r: c[r])
            victim["region"] = dst
            extra = f" · reequilibrio región → {dst}"
            det = victim.get("detalle") or ""
            if extra.strip() not in det:
                victim["detalle"] = det + extra
            moved = True
            break
        if not moved:
            break

    if strict:
        _counts()  # deja contadores listos si se inspecciona en debug
    return equipos


def _status_vs_equiv(nivel_2026: str, nivel_2027: int) -> str:
    equiv = ORIGEN_EQUIV.get(nivel_2026 or "", nivel_2027)
    if nivel_2027 < equiv:
        return "ASCIENDE"
    if nivel_2027 > equiv:
        return "DESCIENDE"
    return "MANTIENE"


def _aplicar_nivel_overrides(niveles: Dict[int, List[dict]]) -> Dict[int, List[dict]]:
    """Mueve equipos a su nivel forzado (NIVEL_OVERRIDES_2027)."""
    if not NIVEL_OVERRIDES_2027:
        return niveles
    by_clave: Dict[str, Tuple[int, dict]] = {}
    for n, eqs in niveles.items():
        for e in eqs:
            ck = e.get("clave") or clave_equipo(e.get("equipo") or "")
            e["clave"] = ck
            by_clave[ck] = (n, e)
    for ck, dest in NIVEL_OVERRIDES_2027.items():
        if ck not in by_clave:
            continue
        cur, e = by_clave[ck]
        if cur == dest:
            # Igual fuerza región override ya aplicado después; solo anota.
            continue
        niveles[cur] = [x for x in niveles[cur] if x.get("clave") != ck]
        prev = cur
        e["nivel_2027"] = dest
        # Status según el movimiento 2027 (no solo equivalencia 2026).
        if dest < prev:
            e["status"] = "ASCIENDE"
        elif dest > prev:
            e["status"] = "DESCIENDE"
        else:
            e["status"] = _status_vs_equiv(e.get("nivel_2026") or "", dest)
        extra = f" · nivel 2027 forzado {prev}→{dest} (ajuste)"
        det = e.get("detalle") or ""
        if extra.strip() not in det:
            e["detalle"] = det + extra
        niveles.setdefault(dest, []).append(e)
        by_clave[ck] = (dest, e)
    return niveles


def _reequilibrar_cupos_n3_a_n6(niveles: Dict[int, List[dict]]) -> Dict[int, List[dict]]:
    """
    Restaura 8/región en N3–N5 moviendo equipos entre niveles de la misma región.
    N6 absorbe el remanente (sin cupo estricto).
    No mueve equipos con NIVEL_OVERRIDES_2027.
    """
    fixed = set(NIVEL_OVERRIDES_2027.keys())

    def _reg_count(n: int, reg: str) -> int:
        return sum(1 for e in niveles.get(n, []) if e.get("region") == reg)

    def _cands(n: int, reg: str, *, worst_first: bool) -> List[dict]:
        xs = [
            e
            for e in niveles.get(n, [])
            if e.get("region") == reg and (e.get("clave") or "") not in fixed
        ]
        xs.sort(
            key=lambda e: (
                int(e.get("pos_2026") or 99),
                str(e.get("equipo") or ""),
            ),
            reverse=worst_first,
        )
        return xs

    def _move(e: dict, src: int, dst: int, motivo: str) -> None:
        niveles[src] = [x for x in niveles[src] if x.get("clave") != e.get("clave")]
        e["nivel_2027"] = dst
        e["status"] = _status_vs_equiv(e.get("nivel_2026") or "", dst)
        extra = f" · {motivo}"
        det = e.get("detalle") or ""
        if extra.strip() not in det:
            e["detalle"] = det + extra
        niveles.setdefault(dst, []).append(e)

    # Cascada N3←N4←N5←N6 y demotes N3→N4→N5→N6 hasta cerrar cupos.
    for _ in range(200):
        changed = False
        for reg in REGIONES:
            # Demotes: exceso en N3–N5 hacia el nivel inferior.
            for n_src, n_dst in ((3, 4), (4, 5), (5, 6)):
                while _reg_count(n_src, reg) > CUPO_REGIONAL:
                    cands = _cands(n_src, reg, worst_first=True)
                    if not cands:
                        break
                    _move(
                        cands[0],
                        n_src,
                        n_dst,
                        f"reequilibrio cupo {reg} {n_src}→{n_dst}",
                    )
                    changed = True
            # Promotes: faltante en N3–N5 desde el nivel inferior.
            for n_dst, n_src in ((3, 4), (4, 5), (5, 6)):
                while _reg_count(n_dst, reg) < CUPO_REGIONAL:
                    cands = _cands(n_src, reg, worst_first=False)
                    if not cands:
                        break
                    _move(
                        cands[0],
                        n_src,
                        n_dst,
                        f"reequilibrio cupo {reg} {n_src}→{n_dst}",
                    )
                    changed = True
        if not changed:
            break
    return niveles


def _unir_filas_por_region(
    tablas_fase: Dict[str, List[dict]], *, fase: str
) -> Dict[str, List[dict]]:
    """Une subzonas (NORTE A/B, …) en una tabla regional. Prefiere zona unificada si existe."""
    pool: Dict[str, List[dict]] = defaultdict(list)
    seen: set = set()
    has_unified = {
        r: r in (tablas_fase or {}) for r in REGIONES
    }
    for zona, rows in (tablas_fase or {}).items():
        reg = _region_desde_zona(zona)
        if reg not in REGIONES:
            continue
        # Si ya hay NORTE unificada, no volver a sumar NORTE A/B.
        if has_unified.get(reg) and zona != reg:
            continue
        for r in rows:
            c = clave_equipo(r["equipo"])
            if c in seen:
                continue
            seen.add(c)
            pool[reg].append(
                {"row": r, "zona": zona, "fase": fase, "clave": c, "region": reg}
            )
    for reg, items in pool.items():
        items.sort(key=lambda x: _sort_key_fila(x["row"]))
        for i, x in enumerate(items, 1):
            x["pos_regional"] = i
    return pool


def _origen_equiv(fase: str) -> int:
    return ORIGEN_EQUIV.get(fase, 5)


def _max_nivel_2027(fase: str) -> int:
    """Nivel 2027 máximo permitido (equivalencia + 1 descenso)."""
    return min(6, _origen_equiv(fase) + MAX_DESCENSO)


def _status_por_origen(fase_origen: str, nivel_2027: int) -> Tuple[str, str]:
    """Status + detalle según de dónde venía el equipo en 2026."""
    origen = _origen_equiv(fase_origen)
    if nivel_2027 < origen:
        return "ASCIENDE", f"Asciende a Nivel {nivel_2027} (venía de {fase_origen})"
    if nivel_2027 > origen:
        return "DESCIENDE", f"Desciende a Nivel {nivel_2027} (venía de {fase_origen})"
    return "MANTIENE", f"Permanece en Nivel {nivel_2027}"


def _ideal_banda(pos_regional: int) -> int:
    if pos_regional <= 8:
        return 3
    if pos_regional <= 16:
        return 4
    if pos_regional <= 24:
        return 5
    return 6


def _asignar_n3_a_n6_con_tope_descenso(
    pool_reg: Dict[str, List[dict]],
    *,
    cupo_n3_por_region: Optional[Dict[str, int]] = None,
) -> Tuple[Dict[int, List[dict]], dict]:
    """
    Ranking regional 8×4 con tope de un descenso respecto de la equivalencia 2026.

    1) Destino ideal por posición (1-8→N3 … 25+→N6), clamp a origen+1.
       Si cupo_n3_por_region[reg] < 8 (porque ya hay plazas N3 reservadas),
       la banda N3 del pool se achica.
    2) Si un nivel 3–5 queda sobre cupo, se degrada al más débil que aún pueda bajar
       un escalón (sin violar el tope). Quienes no pueden bajar más quedan de más.
    """
    por_nivel: Dict[int, List[dict]] = {3: [], 4: [], 5: [], 6: []}
    clampados = 0
    demotes = 0
    demotes_forzados = 0
    cupo_n3 = cupo_n3_por_region or {}

    for reg in REGIONES:
        items = pool_reg.get(reg, [])
        cupo3 = int(cupo_n3.get(reg, CUPO_REGIONAL))
        cupo3 = max(0, min(CUPO_REGIONAL, cupo3))
        buckets: Dict[int, List[dict]] = {3: [], 4: [], 5: [], 6: []}
        for x in items:
            fase = x["fase"]
            # Recalcular banda ideal si N3 del pool tiene menos de 8 plazas.
            pos = int(x["pos_regional"])
            if cupo3 <= 0:
                ideal = _ideal_banda(pos + CUPO_REGIONAL)  # corre bandas hacia N4+
                if ideal < 4:
                    ideal = 4
            elif pos <= cupo3:
                ideal = 3
            elif pos <= cupo3 + 8:
                ideal = 4
            elif pos <= cupo3 + 16:
                ideal = 5
            else:
                ideal = 6
            max_l = _max_nivel_2027(fase)
            dest = min(ideal, max_l)
            if dest < 3:
                dest = max_l if max_l >= 3 else 3
            if dest != ideal:
                clampados += 1
            x = dict(x)
            x["dest"] = dest
            x["ideal"] = ideal
            x["max_l"] = max_l
            buckets[dest].append(x)

        # Rebalance: cupo estricto por región en N3–N5.
        cupos = {3: cupo3, 4: CUPO_REGIONAL, 5: CUPO_REGIONAL}
        for L in (3, 4, 5):
            while len(buckets[L]) > cupos[L]:
                movibles = [x for x in buckets[L] if x["max_l"] >= L + 1]
                forzado = False
                if not movibles:
                    movibles = list(buckets[L])
                    forzado = True
                victim = max(movibles, key=lambda x: _sort_key_fila(x["row"]))
                buckets[L].remove(victim)
                victim["dest"] = L + 1
                if forzado:
                    victim["demote_forzado_cupo"] = True
                    demotes_forzados += 1
                buckets[L + 1].append(victim)
                demotes += 1

        for L in (3, 4, 5, 6):
            for x in buckets[L]:
                dest = x["dest"]
                st, det = _status_por_origen(x["fase"], dest)
                extra = f" · pos regional {x['pos_regional']}"
                if x["ideal"] != dest:
                    extra += f" · tope descenso (ideal N{x['ideal']})"
                if x.get("demote_forzado_cupo"):
                    extra += " · cupo 8/región (demote forzado)"
                por_nivel[dest].append(
                    _entry(
                        x["row"],
                        nivel_2026=x["fase"],
                        zona_2026=x["zona"],
                        region=reg,
                        status=st,
                        nivel_2027=dest,
                        detalle=f"{det}{extra}",
                    )
                )

    stats = {
        "clampados_tope_descenso": clampados,
        "demotes_reequilibrio": demotes,
        "demotes_forzados_cupo": demotes_forzados,
    }
    return por_nivel, stats


def _sort_key_fila(row: dict) -> Tuple:
    pts = int(row.get("puntos") or 0)
    pj = max(int(row.get("pj_general") or 0), 1)
    pts_g = int(row.get("pts_general") or 0)
    ganados = int(row.get("ganados") or 0)
    # 1) pts tira 2) coef pts/pj (aprox pts_general/pj) 3) ganados 4) nombre
    return (-pts, -(pts_g / pj), -ganados, -pts_g, row.get("equipo") or "")


def _entry(
    row: dict,
    *,
    nivel_2026: str,
    zona_2026: str,
    region: str,
    status: str,
    nivel_2027: int,
    detalle: str = "",
) -> dict:
    return {
        "equipo": row["equipo"],
        "clave": clave_equipo(row["equipo"]),
        "pos_2026": row.get("pos"),
        "puntos": row.get("puntos"),
        "pts_general": row.get("pts_general"),
        "pts_presentacion": row.get("pts_presentacion"),
        "pj_general": row.get("pj_general"),
        "ganados": row.get("ganados"),
        "nivel_2026": nivel_2026,
        "zona_2026": zona_2026,
        "region": region,
        "status": status,
        "nivel_2027": nivel_2027,
        "detalle": detalle,
    }


def calcular(data: dict) -> dict:
    regiones = _mapa_regiones(data)
    tablas = data["tablas"]

    def region_of(equipo: str) -> str:
        return regiones.get(clave_equipo(equipo), "?")

    # --- Inter A / B ---
    a_keep: List[dict] = []
    a_down: List[dict] = []
    for zona, rows in tablas["INTERCONFERENCIA_A"].items():
        ordered = sorted(rows, key=_sort_key_fila)
        # respetar orden publicado si ya viene ordenado por pos
        ordered = list(rows)
        for r in ordered[:-2]:
            a_keep.append(
                _entry(
                    r,
                    nivel_2026="INTERCONFERENCIA_A",
                    zona_2026=zona,
                    region=region_of(r["equipo"]),
                    status="MANTIENE",
                    nivel_2027=1,
                    detalle="Permanece en Interconferencia A / Nivel 1",
                )
            )
        for r in ordered[-2:]:
            a_down.append(
                _entry(
                    r,
                    nivel_2026="INTERCONFERENCIA_A",
                    zona_2026=zona,
                    region=region_of(r["equipo"]),
                    status="DESCIENDE",
                    nivel_2027=2,
                    detalle="Desciende a Interconferencia B / Nivel 2",
                )
            )

    b_up: List[dict] = []
    b_keep: List[dict] = []
    b_down: List[dict] = []
    for zona, rows in tablas["INTERCONFERENCIA_B"].items():
        ordered = list(rows)
        for r in ordered[:2]:
            b_up.append(
                _entry(
                    r,
                    nivel_2026="INTERCONFERENCIA_B",
                    zona_2026=zona,
                    region=region_of(r["equipo"]),
                    status="ASCIENDE",
                    nivel_2027=1,
                    detalle="Asciende a Interconferencia A / Nivel 1",
                )
            )
        for r in ordered[2:-2]:
            b_keep.append(
                _entry(
                    r,
                    nivel_2026="INTERCONFERENCIA_B",
                    zona_2026=zona,
                    region=region_of(r["equipo"]),
                    status="MANTIENE",
                    nivel_2027=2,
                    detalle="Permanece en Interconferencia B / Nivel 2",
                )
            )
        for r in ordered[-2:]:
            b_down.append(
                _entry(
                    r,
                    nivel_2026="INTERCONFERENCIA_B",
                    zona_2026=zona,
                    region=region_of(r["equipo"]),
                    status="DESCIENDE",
                    nivel_2027=3,
                    detalle="Desciende a Nivel 3",
                )
            )

    # --- Nivel 3 (GES NIVEL_1) ---
    n3_by_reg: Dict[str, List[Tuple[dict, str]]] = defaultdict(list)
    for zona, rows in tablas["NIVEL_1"].items():
        reg = _region_desde_zona(zona)
        for r in rows:
            n3_by_reg[reg].append((r, zona))

    n_nivel1 = sum(len(v) for v in n3_by_reg.values())
    # Plan histórico de descensos (referencia); la permanencia mínima en N3
    # se fija con MIN_STAY_N3_FROM_GES_N1 y el resto va al pool regional.
    _plan_descensos_n3(n_nivel1)

    n3_up: List[dict] = []
    n3_keep: List[dict] = []
    keep_por_region: Dict[str, int] = {r: 0 for r in REGIONES}
    for reg in REGIONES:
        items = n3_by_reg.get(reg, [])
        n_up = ASCENSOS_N3_A_N2
        for r, zona in items[:n_up]:
            n3_up.append(
                _entry(
                    r,
                    nivel_2026="NIVEL_1",
                    zona_2026=zona,
                    region=reg,
                    status="ASCIENDE",
                    nivel_2027=2,
                    detalle="Asciende a Interconferencia B / Nivel 2",
                )
            )
        # Garantía: al menos MIN_STAY_N3_FROM_GES_N1 del GES N1 quedan en N3.
        restantes = items[n_up:]
        n_keep = min(MIN_STAY_N3_FROM_GES_N1, len(restantes))
        for r, zona in restantes[:n_keep]:
            n3_keep.append(
                _entry(
                    r,
                    nivel_2026="NIVEL_1",
                    zona_2026=zona,
                    region=reg,
                    status="MANTIENE",
                    nivel_2027=3,
                    detalle=(
                        f"Permanece en Nivel 3 (cupo mínimo GES N1 → N3, {reg})"
                    ),
                )
            )
            keep_por_region[reg] += 1
        # El resto del GES N1 entra al pool regional (no se fija descenso acá).

    nivel1 = a_keep + b_up
    nivel2 = b_keep + a_down + n3_up
    # N3 reservados + N1/N2 ya no compiten en el pool.
    assigned_top = {e["clave"] for e in nivel1 + nivel2 + n3_keep}
    cupo_n3_pool = {
        r: max(0, CUPO_REGIONAL - keep_por_region.get(r, 0)) for r in REGIONES
    }

    # --- N3–N6: 8 por región (32/nivel), ranking regional del remanente ---
    # Universo priorizando fase actual (N3→N2→N1→…); excluye ya ubicados en N1/N2.
    prioridad = {
        "NIVEL_3": 0,
        "NIVEL_2": 1,
        "NIVEL_1": 2,
        "INTERCONFERENCIA_B": 3,
        "INTERCONFERENCIA_A": 4,
        "RECLASIFICACION": 5,
        "CLASIFICACION": 6,
    }
    fases_universo = (
        "INTERCONFERENCIA_A",
        "INTERCONFERENCIA_B",
        "NIVEL_1",
        "NIVEL_2",
        "NIVEL_3",
        "CLASIFICACION",
        "RECLASIFICACION",
    )
    candidatos: Dict[str, List[Tuple[int, str, str, dict]]] = defaultdict(list)
    for fase in fases_universo:
        for zona, rows in tablas.get(fase, {}).items():
            # Evitar doble conteo de subzonas si ya está la unificada.
            reg_z = _region_desde_zona(zona)
            if (
                fase in ("NIVEL_2", "NIVEL_3")
                and reg_z in REGIONES
                and zona != reg_z
                and reg_z in tablas.get(fase, {})
            ):
                continue
            for r in rows:
                c = clave_equipo(r["equipo"])
                candidatos[c].append((prioridad.get(fase, 9), fase, zona, r))

    uniq: Dict[str, dict] = {}
    meta_row: Dict[str, Tuple[str, str]] = {}
    for c, opts in candidatos.items():
        opts.sort(key=lambda t: t[0])
        _prio, fase, zona, r = opts[0]
        uniq[c] = r
        meta_row[c] = (fase, zona)

    pool_reg: Dict[str, List[dict]] = defaultdict(list)
    for c, r in uniq.items():
        if c in assigned_top:
            continue
        reg = region_of(r["equipo"])
        if reg not in REGIONES:
            continue
        fase, zona = meta_row[c]
        pool_reg[reg].append(
            {"row": r, "clave": c, "fase": fase, "zona": zona, "region": reg}
        )

    for reg in REGIONES:
        pool_reg[reg].sort(key=lambda x: _sort_key_fila(x["row"]))
        for i, x in enumerate(pool_reg[reg], 1):
            x["pos_regional"] = i

    por_nivel, stats_tope = _asignar_n3_a_n6_con_tope_descenso(
        pool_reg, cupo_n3_por_region=cupo_n3_pool
    )

    nivel3 = n3_keep + por_nivel[3]
    nivel4 = por_nivel[4]
    nivel5 = por_nivel[5]
    nivel6 = por_nivel[6]
    fuente_n4 = "RANKING_REGIONAL_8x4_TOPE_1_DESCENSO"
    pool_counts = {r: len(pool_reg.get(r, [])) for r in REGIONES}

    niveles = {
        1: nivel1,
        2: nivel2,
        3: nivel3,
        4: nivel4,
        5: nivel5,
        6: nivel6,
    }

    # 1) Forzar niveles puntuales (p.ej. Vélez N3 / Huracán N4).
    niveles = _aplicar_nivel_overrides(niveles)

    # 2) Ajustes geográficos 2027.
    # N1/N2 son interregionales: solo override, sin forzar 8/región.
    for n in (1, 2):
        niveles[n] = _aplicar_overrides_y_reequilibrar_nivel(
            niveles[n], cupo=None, strict=False
        )
    # N3–N5: cupo estricto 8/región (solo región dentro del nivel).
    for n in (3, 4, 5):
        niveles[n] = _aplicar_overrides_y_reequilibrar_nivel(
            niveles[n], cupo=CUPO_REGIONAL, strict=True
        )
    # N6: remanente; se intenta acercar a 8/región sin forzar.
    niveles[6] = _aplicar_overrides_y_reequilibrar_nivel(
        niveles[6], cupo=CUPO_REGIONAL, strict=False
    )

    # 3) Cerrar cupos 8/región moviendo entre N3–N6 de la misma región.
    niveles = _reequilibrar_cupos_n3_a_n6(niveles)
    # Reaplicar región fija (por si un promote/demote tocó overrides).
    for n in (3, 4, 5):
        niveles[n] = _aplicar_overrides_y_reequilibrar_nivel(
            niveles[n], cupo=CUPO_REGIONAL, strict=True
        )
    niveles[6] = _aplicar_overrides_y_reequilibrar_nivel(
        niveles[6], cupo=CUPO_REGIONAL, strict=False
    )

    status_por_clave: Dict[str, dict] = {}
    for n, eqs in niveles.items():
        for e in eqs:
            status_por_clave[e["clave"]] = {
                "status": e["status"],
                "nivel_2027": n,
                "nivel_2026": e["nivel_2026"],
                "region": e["region"],
                "detalle": e["detalle"],
            }

    cupos = {str(n): len(eqs) for n, eqs in niveles.items()}
    por_region = {
        str(n): dict(Counter(e["region"] for e in eqs)) for n, eqs in niveles.items()
    }
    overrides_aplicados = []
    for ck, reg in REGION_OVERRIDES_2027.items():
        st = status_por_clave.get(ck)
        if not st:
            continue
        overrides_aplicados.append(
            {
                "clave": ck,
                "region_2027": reg,
                "nivel_2027": st["nivel_2027"],
                "status": st["status"],
            }
        )

    meta = {
        "fecha_calculo": date.today().isoformat(),
        "fecha_standings": data.get("fecha"),
        "total_equipos": sum(cupos.values()),
        "fuente_standings": str(STANDINGS_HTML.relative_to(ROOT)).replace("\\", "/"),
        "nota_u21": (
            "U21 = LIGA PROXIMO MASCULINO (GES 5075): suma a la tabla general "
            "junto con U13/U15/U17. Presentación a la general: solo U11 (U9 informativa)."
        ),
        "equipo_unificado_alias": "NAUTICO BUCHARDO NORTE (A) -> NAUTICO BUCHARDO A",
        "fuente_pool_n4": fuente_n4,
        "equilibrio_regional": {
            "regla": (
                "N3-N5: cupo estricto 8/región (32/nivel); N6 recibe el remanente. "
                "Prioriza tope de 1 descenso; si el cupo no cierra, demote forzado. "
                "(InterA=N1, InterB=N2, GES N1=N3, GES N2=N4, GES N3=N5; N6 nuevo)"
            ),
            "pool_remanente_por_region": pool_counts,
            "n1_n2_interregional": True,
            "ges_n1_keep_n3_por_region": dict(keep_por_region),
            "cupo_n3_pool_por_region": dict(cupo_n3_pool),
            "region_overrides_2027": overrides_aplicados,
            **stats_tope,
        },
        "reglas": {
            "inter_a_descensos_por_grupo": 2,
            "inter_b_ascensos_por_grupo": 2,
            "inter_b_descensos_por_grupo": 2,
            "n3_ascensos_por_region_a_n2": ASCENSOS_N3_A_N2,
            "n3_min_stay_ges_n1_por_region": MIN_STAY_N3_FROM_GES_N1,
            "n3_a_n6_cupo_por_region": CUPO_REGIONAL,
            "max_descenso_niveles": MAX_DESCENSO,
            "equivalencia_2026": dict(ORIGEN_EQUIV),
            "region_overrides_2027": {
                ck: reg for ck, reg in REGION_OVERRIDES_2027.items()
            },
            "nivel_overrides_2027": {
                ck: n for ck, n in NIVEL_OVERRIDES_2027.items()
            },
        },
    }

    payload = {
        "meta": meta,
        "cupos": cupos,
        "por_region": por_region,
        "niveles": {
            str(n): {
                "id": n,
                "nombre": {
                    1: "Nivel 1 · Interconferencia A",
                    2: "Nivel 2 · Interconferencia B",
                    3: "Nivel 3",
                    4: "Nivel 4",
                    5: "Nivel 5",
                    6: "Nivel 6",
                }[n],
                "n_equipos": len(eqs),
                "equipos": eqs,
            }
            for n, eqs in niveles.items()
        },
        "status_por_clave": status_por_clave,
    }
    return payload


def inyectar_badges_en_standings(payload: dict, html_paths: List[Path]) -> None:
    """Inyecta mapa equipo→status y badges en las filas de la tabla (idempotente)."""
    by_equipo: Dict[str, dict] = {}
    for _n_str, bloque in payload["niveles"].items():
        for e in bloque["equipos"]:
            by_equipo[e["equipo"]] = {
                "status": e["status"],
                "nivel_2027": e["nivel_2027"],
                "detalle": e["detalle"],
                "clave": e["clave"],
            }

    status_json = json.dumps(by_equipo, ensure_ascii=False)
    css = (
        "\n    .badge-mov { display:inline-block; margin-left:6px; padding:1px 7px;"
        " border-radius:999px; font-size:10px; font-weight:700; letter-spacing:.02em;"
        " vertical-align:middle; cursor:help; }\n"
        "    .badge-mov.ASC { background:#dcfce7; color:#166534; }\n"
        "    .badge-mov.DESC { background:#fee2e2; color:#991b1b; }\n"
        "    .badge-mov.KEEP { background:#e2e8f0; color:#334155; }\n"
        "    .mov-legend { display:flex; flex-wrap:wrap; gap:10px; margin:8px 0 0;"
        " font-size:12px; color:var(--muted); align-items:center; }\n"
    )
    legend = (
        '\n    <div class="mov-legend" id="mov-legend">\n'
        '      <span><span class="badge-mov ASC">ASC</span> asciende → 2027</span>\n'
        '      <span><span class="badge-mov DESC">DESC</span> desciende → 2027</span>\n'
        '      <span><span class="badge-mov KEEP">N#</span> mantiene / proyectado</span>\n'
        "      <span>Movilidad Fase 2 2026 → 6 niveles 2027</span>\n"
        "    </div>\n"
    )
    helper_js = (
        f"\n    const MOVILIDAD_2027_EQ = {status_json};\n"
        "    function badgeMovEquipo(equipo) {\n"
        "      const info = MOVILIDAD_2027_EQ[equipo];\n"
        '      if (!info) return "";\n'
        '      const st = info.status || "";\n'
        "      const n = info.nivel_2027;\n"
        '      let cls = "KEEP", lab = "N" + n;\n'
        '      if (st === "ASCIENDE") { cls = "ASC"; lab = "ASC N" + n; }\n'
        '      else if (st === "DESCIENDE") { cls = "DESC"; lab = "DESC N" + n; }\n'
        '      const title = (info.detalle || st) + " (Nivel 2027: " + n + ")";\n'
        "      return ` <span class=\"badge-mov ${cls}\" title=\"${title.replace(/\"/g, '&quot;')}\">${lab}</span>`;\n"
        "    }\n"
    )

    # Quita inyecciones previas rotas / duplicadas.
    strip_mov = re.compile(
        r"\s*const MOVILIDAD_2027_EQ = \{.*?\};\s*"
        r"function badgeMovEquipo\(equipo\) \{.*?\n    \}\s*",
        re.S,
    )
    strip_orphan = re.compile(
        r"\n\s*else if \(st === \"DESCIENDE\"\) \{.*?\n    \}\s*",
        re.S,
    )

    old_eq = '<td class="pos">${f.pos}</td><td class="eq">${f.equipo}</td>'
    new_eq = (
        '<td class="pos">${f.pos}</td>'
        '<td class="eq">${f.equipo}${badgeMovEquipo(f.equipo)}</td>'
    )

    for path in html_paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")

        # Limpiar restos de inyecciones anteriores.
        text = strip_mov.sub("\n", text)
        text = strip_orphan.sub("\n", text)
        text = text.replace(new_eq, old_eq)
        text = re.sub(
            r"\n\s*\.badge-mov \{.*?\n\s*\.mov-legend \{.*?\n",
            "\n",
            text,
            count=1,
            flags=re.S,
        )
        text = re.sub(
            r'\n\s*<div class="mov-legend" id="mov-legend">.*?</div>\s*',
            "\n",
            text,
            count=1,
            flags=re.S,
        )

        if ".badge-mov" not in text:
            text = text.replace("</style>", css + "  </style>", 1)
        if 'id="mov-legend"' not in text:
            if '<div class="stats" id="stats"></div>' in text:
                text = text.replace(
                    '<div class="stats" id="stats"></div>',
                    '<div class="stats" id="stats"></div>\n' + legend,
                    1,
                )
            elif "</header>" in text:
                text = text.replace("</header>", legend + "  </header>", 1)

        if "const DATA = " in text and "MOVILIDAD_2027_EQ" not in text:
            text = text.replace("const DATA = ", helper_js + "\n    const DATA = ", 1)

        if "${f.equipo}${badgeMovEquipo" not in text:
            text = text.replace(old_eq, new_eq)

        path.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--standings", type=Path, default=STANDINGS_HTML)
    ap.add_argument("--out", type=Path, default=OUT_JSON)
    ap.add_argument("--inyectar-badges", action="store_true")
    args = ap.parse_args()

    data = _load_standings(args.standings)
    payload = calcular(data)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    OUT_DETALLE.parent.mkdir(parents=True, exist_ok=True)
    OUT_DETALLE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"cupos": payload["cupos"], "por_region": payload["por_region"], "meta": payload["meta"]}, ensure_ascii=False, indent=2))

    if args.inyectar_badges:
        paths = [STANDINGS_HTML, STANDINGS_OUT]
        inyectar_badges_en_standings(payload, paths)
        print("Badges inyectados en:", [str(p) for p in paths if p.exists()])

    # Validación: tope de 1 descenso; N1–N4 suelen ser 32 (N5/N6 se desvían por el tope).
    cupos = {int(k): v for k, v in payload["cupos"].items()}
    if cupos.get(1) != 32 or cupos.get(2) != 32:
        print(f"ADVERTENCIA: cupos N1/N2 {cupos}", file=sys.stderr)
        return 2
    viol = 0
    eq = payload.get("meta", {}).get("reglas", {}).get("equivalencia_2026", ORIGEN_EQUIV)
    for _nk, bloque in payload["niveles"].items():
        for e in bloque["equipos"]:
            origen = eq.get(e["nivel_2026"], 5)
            if e["nivel_2027"] - origen > MAX_DESCENSO:
                viol += 1
    if viol:
        print(f"ADVERTENCIA: {viol} equipos bajan mas de {MAX_DESCENSO} nivel(es)", file=sys.stderr)
        return 2
    total = payload["meta"]["total_equipos"]
    if total != sum(cupos.values()):
        print("ADVERTENCIA: suma cupos != total", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
