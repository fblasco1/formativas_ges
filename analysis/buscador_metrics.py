# -*- coding: utf-8 -*-
"""Métricas avanzadas, percentiles y clustering para el buscador de jugadores."""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

# Perfiles de jugador (orden = cluster_id tras mapeo a prototipos).
PERFILES: Tuple[str, ...] = (
    "Especialista 3&D",
    "Protector de Aro",
    "Base Conductor",
    "Anotador de Volumen",
    "Generador Perimetral",
    "Interno de Rol",
)

PERFIL_INSUFICIENTE = "Muestra insuficiente"

# Textos para la guía de perfiles en el buscador.
PERFIL_DESCRIPCIONES: Dict[str, Dict[str, str]] = {
    "Especialista 3&D": {
        "resumen": "Jugador perimetral orientado al tiro de triple y la defensa exterior.",
        "caracteristicas": "Alto volumen de 3P intentados por partido y buen porcentaje. Suele aportar robos sin ser protagonista en asistencias ni rebote interior.",
        "scouting": "Útil para espaciar la pintura y acompañar a un base o interior. Buscar consistencia en 3P% con volumen (≥2 int/p) y aporte defensivo (robos).",
    },
    "Protector de Aro": {
        "resumen": "Especialista defensivo interior, protector del aro y reboteador.",
        "caracteristicas": "Dominancia en rebotes y tapones. Bajo uso del triple y perfil defensivo cerca del aro.",
        "scouting": "Priorizar rebotes por partido y presencia bajo el tablero. Ideal para complementar un frontcourt ofensivo.",
    },
    "Base Conductor": {
        "resumen": "Armador / facilitador con visión de juego y presión al balón.",
        "caracteristicas": "Altas asistencias y robos por partido. Perfil de organización y baloncesto en transición o half-court.",
        "scouting": "Mirar ratio Ast/Per (≥1.5) y volumen de asistencias. Buen candidato para manejar el ritmo del equipo.",
    },
    "Anotador de Volumen": {
        "resumen": "Scorer con alto uso ofensivo y producción en puntos.",
        "caracteristicas": "Muchos puntos por partido, uso elevado del tiro de campo y tiros libres. Perfil de go-to guy en categorías formativas.",
        "scouting": "Evaluar TS% y Val/Min además del volumen. Puede ser anotador puro o slasher según reparto 2P/TL.",
    },
    "Generador Perimetral": {
        "resumen": "Jugador versátil perimetral que aporta en varias facetas.",
        "caracteristicas": "Equilibrio entre triple, asistencias y rebotes. Perfil polivalente sin extremos marcados en una sola stat.",
        "scouting": "Buen jugador de rotación completo. Comparar percentiles en pts, ast y reb dentro de su categoría.",
    },
    "Interno de Rol": {
        "resumen": "Interior de rol con aporte defensivo y juego cerca del aro.",
        "caracteristicas": "Rebotes moderados-altos, algo de tapones, uso ofensivo contenido. Perfil de complemento en la pintura.",
        "scouting": "Buscar eficiencia defensiva y rebote sin exigir anotación alta. Val/Min puede ser alto en minutos moderados.",
    },
    PERFIL_INSUFICIENTE: {
        "resumen": "Jugador con menos de 5 partidos jugados en la muestra.",
        "caracteristicas": "No se asigna perfil de clustering para evitar conclusiones con datos insuficientes.",
        "scouting": "Ampliar muestra antes de fichar. Podés seguirlo en la lista de fichajes y revisar cuando acumule más PJ.",
    },
}

# Prototipos calibrados a formativas GES (features en escala real del dataset).
# Features: t3i_p, t3_pct, ast_p, rob_p, reb_p, pts_p
_PROTOTIPOS: List[List[float]] = [
    [2.5, 30.0, 0.8, 1.5, 2.5, 6.0],   # Especialista 3&D
    [0.2, 12.0, 0.4, 0.8, 7.0, 4.0],   # Protector de Aro
    [1.0, 18.0, 2.5, 2.0, 3.0, 8.0],   # Base Conductor
    [0.5, 14.0, 0.5, 0.7, 3.5, 12.0],  # Anotador de Volumen
    [1.5, 22.0, 1.5, 1.2, 4.5, 10.0],  # Generador Perimetral
    [0.4, 14.0, 0.5, 0.9, 5.5, 5.0],   # Interno de Rol
]

CLUSTER_FEATURES = ("t3i_p", "t3_pct", "ast_p", "rob_p", "reb_p", "pts_p")
PCT_METRICS = ("pts_p", "ts_pct", "val_min", "ast_p", "reb_p")
MIN_PJ_CLUSTER = 5
K_CLUSTERS = 6
KMEANS_MAX_ITER = 50


def ts_pct(pts: int, t2i: int, t3i: int, tli: int) -> Optional[float]:
    fga = t2i + t3i
    denom = 2 * (fga + 0.44 * tli)
    if denom <= 0:
        return None
    return round(100.0 * pts / denom, 1)


def efg_pct(t2a: int, t3a: int, t2i: int, t3i: int) -> Optional[float]:
    fga = t2i + t3i
    if fga <= 0:
        return None
    fgm = t2a + t3a
    return round(100.0 * (fgm + 0.5 * t3a) / fga, 1)


def val_min(val_p: float, min_p: float) -> Optional[float]:
    if min_p <= 0:
        return None
    return round(val_p / min_p, 3)


def ast_per(ast_p: float, per_p: float) -> Optional[float]:
    if per_p <= 0:
        return None
    return round(ast_p / per_p, 2)


def _mean_std(values: Sequence[float]) -> Tuple[float, float]:
    n = len(values)
    if n == 0:
        return 0.0, 1.0
    mu = sum(values) / n
    if n == 1:
        return mu, 1.0
    var = sum((v - mu) ** 2 for v in values) / n
    return mu, math.sqrt(var) if var > 0 else 1.0


def _zscore_row(row: List[float], stats: List[Tuple[float, float]]) -> List[float]:
    return [(row[i] - stats[i][0]) / stats[i][1] for i in range(len(row))]


def _dist2(a: Sequence[float], b: Sequence[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b))


def _kmeans(
    data: List[List[float]], k: int, *, seed: int = 42
) -> Tuple[List[int], List[List[float]]]:
    n = len(data)
    if n == 0:
        return [], []
    k = min(k, n)
    rng = __import__("random").Random(seed)
    centroids = [list(data[i]) for i in rng.sample(range(n), k)]
    assignments = [-1] * n
    for _ in range(KMEANS_MAX_ITER):
        changed = False
        for i, row in enumerate(data):
            best = min(range(k), key=lambda c: _dist2(row, centroids[c]))
            if assignments[i] != best:
                assignments[i] = best
                changed = True
        new_centroids: List[List[float]] = []
        for c in range(k):
            members = [data[i] for i in range(n) if assignments[i] == c]
            if members:
                dim = len(members[0])
                new_centroids.append(
                    [sum(m[d] for m in members) / len(members) for d in range(dim)]
                )
            else:
                new_centroids.append(list(centroids[c]))
        centroids = new_centroids
        if not changed:
            break
    return assignments, centroids


def _map_clusters_to_perfiles(
    centroids_z: List[List[float]], proto_z: List[List[float]]
) -> Dict[int, int]:
    """Asignación 1:1 entre clusters K-Means y perfiles por proximidad."""
    pairs: List[Tuple[float, int, int]] = []
    for ci, c in enumerate(centroids_z):
        for pi, p in enumerate(proto_z):
            pairs.append((_dist2(c, p), ci, pi))
    pairs.sort()
    cluster_map: Dict[int, int] = {}
    used_c: set = set()
    used_p: set = set()
    for _, ci, pi in pairs:
        if ci in used_c or pi in used_p:
            continue
        cluster_map[ci] = pi
        used_c.add(ci)
        used_p.add(pi)
    for ci in range(len(centroids_z)):
        if ci not in cluster_map:
            pi = min(
                range(len(proto_z)),
                key=lambda p: _dist2(centroids_z[ci], proto_z[p]),
            )
            cluster_map[ci] = pi
    return cluster_map


def _percentile_rank(value: float, population: List[float]) -> int:
    if not population:
        return 0
    below = sum(1 for v in population if v < value)
    equal = sum(1 for v in population if v == value)
    return int(round(100.0 * (below + 0.5 * equal) / len(population)))


def _assign_nearest_prototype(z_row: List[float], proto_z: List[List[float]]) -> int:
    return min(range(len(proto_z)), key=lambda i: _dist2(z_row, proto_z[i]))


def _cluster_players(
    eligible: List[Dict[str, object]],
) -> None:
    raw_rows = [[float(j.get(f) or 0) for f in CLUSTER_FEATURES] for j in eligible]
    stats = [_mean_std([r[i] for r in raw_rows]) for i in range(len(CLUSTER_FEATURES))]
    z_rows = [_zscore_row(r, stats) for r in raw_rows]
    proto_z = [_zscore_row(p, stats) for p in _PROTOTIPOS]
    if len(eligible) >= K_CLUSTERS:
        assignments, centroids_z = _kmeans(z_rows, K_CLUSTERS)
        cluster_map = _map_clusters_to_perfiles(centroids_z, proto_z)
        for j, z_row, assign in zip(eligible, z_rows, assignments):
            perfil_idx = cluster_map.get(assign, _assign_nearest_prototype(z_row, proto_z))
            j["cluster_id"] = assign
            j["perfil"] = PERFILES[perfil_idx]
    else:
        for j, z_row in zip(eligible, z_rows):
            perfil_idx = _assign_nearest_prototype(z_row, proto_z)
            j["cluster_id"] = perfil_idx
            j["perfil"] = PERFILES[perfil_idx]


def enriquecer_jugadores(jugadores: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """Añade métricas avanzadas, percentiles y perfiles a cada jugador."""
    for j in jugadores:
        pts = int(j.get("pts") or 0)
        t2a, t3a = int(j.get("t2a") or 0), int(j.get("t3a") or 0)
        t2i, t3i, tli = int(j.get("t2i") or 0), int(j.get("t3i") or 0), int(j.get("tli") or 0)
        min_p = float(j.get("min_p") or 0)
        val_p = float(j.get("val_p") or 0)
        ast_p = float(j.get("ast_p") or 0)
        per_total = int(j.get("per") or 0)
        pj = int(j.get("pj") or 0)
        per_p = round(per_total / pj, 1) if pj > 0 else 0.0

        ts = ts_pct(pts, t2i, t3i, tli)
        efg = efg_pct(t2a, t3a, t2i, t3i)
        vmin = val_min(val_p, min_p)
        aper = ast_per(ast_p, per_p)

        j["per_p"] = per_p
        j["ts_pct"] = ts if ts is not None else ""
        j["efg_pct"] = efg if efg is not None else ""
        j["val_min"] = vmin if vmin is not None else ""
        j["ast_per"] = aper if aper is not None else ""
        j["cluster_id"] = -1
        j["perfil"] = PERFIL_INSUFICIENTE

    # Percentiles por categoría.
    by_cat: Dict[str, List[Dict[str, object]]] = {}
    for j in jugadores:
        by_cat.setdefault(str(j.get("cat") or ""), []).append(j)

    for cat_players in by_cat.values():
        for metric in PCT_METRICS:
            vals = [
                float(j[metric])
                for j in cat_players
                if j.get(metric) not in (None, "")
            ]
            key = f"pct_{metric.replace('_p', '').replace('_pct', '').replace('val_min', 'val')}"
            if metric == "pts_p":
                key = "pct_pts"
            elif metric == "ts_pct":
                key = "pct_ts"
            elif metric == "val_min":
                key = "pct_val"
            elif metric == "ast_p":
                key = "pct_ast"
            elif metric == "reb_p":
                key = "pct_reb"
            for j in cat_players:
                v = j.get(metric)
                if v in (None, ""):
                    j[key] = ""
                else:
                    j[key] = _percentile_rank(float(v), vals)

    eligible = [j for j in jugadores if int(j.get("pj") or 0) >= MIN_PJ_CLUSTER]
    if eligible:
        _cluster_players(eligible)

    return jugadores
