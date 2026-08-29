# -*- coding: utf-8 -*-
"""
Simula km de viaje visitante para escenarios de regionalización (élite 42).

Escenarios:
  A) 4 regiones (CENTRO/SUR/NORTE/OESTE) — fase 1 regional, fase 2: 16 mejores (4/region) sin región.
  B) Mixta CENTRO-SUR / NORTE-OESTE — fase 1 en 2 macro-regiones, misma fase 2.
  C) Sin regionalización — fase 1 sorteo puro en zonas de 8, misma fase 2.

Zonas de competencia: 8 equipos por sorteo (última zona puede tener 9-10 si sobran).

  python analysis/simular_viajes_escenarios.py
  python analysis/simular_viajes_escenarios.py --informe
"""

from __future__ import annotations

import argparse
import csv
import html
import importlib.util
import json
import random
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "outputs" / "viajes_elite42"
MAPEO_CSV = OUT_DIR / "mapeo_clubes.csv"
MATRIZ_JSON = OUT_DIR / "matriz_distancias_km.json"
ESCENARIOS_JSON = OUT_DIR / "escenarios_viajes.json"
INFORME_HTML = OUT_DIR / "informe_escenarios_viajes.html"

REGIONES = ("NORTE", "CENTRO", "SUR", "OESTE")
MIXTAS = (("CENTRO-SUR", ("CENTRO", "SUR")), ("NORTE-OESTE", ("NORTE", "OESTE")))
TAM_ZONA = 8
SEED_SORTEO = 42
AVANZAN_POR_REGION = 4  # fase 2: 16 equipos (4 x 4 regiones)


@dataclass
class Club:
    idx: int
    pos: int
    equipo: str
    clave: str
    zona_febamba: str
    region: str
    lat: float
    lon: float
    region_geo: str = ""
    mal_regionalizado: bool = False
    km_fase1: float = 0.0
    km_fase2: float = 0.0


@dataclass
class EscenarioResultado:
    id: str
    nombre: str
    descripcion: str
    km_por_club: Dict[str, float]
    km_fase1_por_club: Dict[str, float]
    km_fase2_por_club: Dict[str, float]
    zonas_fase1: List[List[str]]
    zonas_fase2: List[List[str]]
    stats: Dict[str, float] = field(default_factory=dict)


def _load_common():
    spec = importlib.util.spec_from_file_location(
        "viajes_elite42_common", ROOT / "analysis" / "viajes_elite42_common.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def region_desde_zona(zona: str) -> str:
    return (zona or "").split()[0].upper()


def cargar_clubes() -> Tuple[List[Club], List[List[float]]]:
    clubs: List[Club] = []
    with MAPEO_CSV.open(encoding="utf-8-sig", newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            lat, lon = row.get("lat"), row.get("lon")
            if not lat or not lon:
                raise ValueError(f"Sin coordenadas: {row['equipo']}")
            clubs.append(
                Club(
                    idx=i,
                    pos=int(row["pos"]),
                    equipo=row["equipo"],
                    clave=row["clave"],
                    zona_febamba=row["zona"],
                    region=region_desde_zona(row["zona"]),
                    lat=float(lat),
                    lon=float(lon),
                )
            )
    with MATRIZ_JSON.open(encoding="utf-8") as f:
        mat = json.load(f)["km"]
    return clubs, mat


def dist_km(mat: List[List[float]], a: int, b: int) -> float:
    v = mat[a][b]
    return float(v) if v is not None else 0.0


def centroides_region(clubs: Sequence[Club]) -> Dict[str, Tuple[float, float]]:
    acc: Dict[str, List[Tuple[float, float]]] = {r: [] for r in REGIONES}
    for c in clubs:
        acc[c.region].append((c.lat, c.lon))
    out: Dict[str, Tuple[float, float]] = {}
    for r, pts in acc.items():
        if pts:
            out[r] = (statistics.mean(p[0] for p in pts), statistics.mean(p[1] for p in pts))
    return out


def asignar_region_geografica(clubs: List[Club]) -> None:
    cents = centroides_region(clubs)
    for c in clubs:
        best_r, best_d = "", float("inf")
        for r, (lat, lon) in cents.items():
            d = (c.lat - lat) ** 2 + (c.lon - lon) ** 2
            if d < best_d:
                best_d, best_r = d, r
        c.region_geo = best_r
        c.mal_regionalizado = c.region_geo != c.region


def zonas_sorteo(indices: List[int], *, seed: int = SEED_SORTEO) -> List[List[int]]:
    """Parte en zonas de 8 por sorteo (bloques consecutivos tras mezclar)."""
    rng = random.Random(seed)
    ids = indices[:]
    rng.shuffle(ids)
    return [ids[i : i + TAM_ZONA] for i in range(0, len(ids), TAM_ZONA)]


def km_zona_round_robin(
    zona: List[int], mat: List[List[float]], *, ida_vuelta: bool = True
) -> Dict[int, float]:
    mult = 2.0 if ida_vuelta else 1.0
    km: Dict[int, float] = {i: 0.0 for i in zona}
    for i, a in enumerate(zona):
        for b in zona[i + 1 :]:
            d = dist_km(mat, a, b) * mult
            km[a] += d
            km[b] += d
    return km


def acumular_km(dest: Dict[int, float], zona_km: Dict[int, float]) -> None:
    for k, v in zona_km.items():
        dest[k] = dest.get(k, 0.0) + v


def top_por_region(clubs: Sequence[Club], n: int = AVANZAN_POR_REGION) -> List[int]:
    """Top N por región FeBAMBA (menor pos = mejor)."""
    por_r: Dict[str, List[Club]] = {r: [] for r in REGIONES}
    for c in clubs:
        por_r[c.region].append(c)
    sel: List[int] = []
    for r in REGIONES:
        orden = sorted(por_r[r], key=lambda x: x.pos)[:n]
        sel.extend(c.idx for c in orden)
    return sel


def top_global(clubs: Sequence[Club], n: int = 16) -> List[int]:
    return [c.idx for c in sorted(clubs, key=lambda x: x.pos)[:n]]


def simular_fase1_por_grupos(
    grupos: Dict[str, List[int]],
    mat: List[List[float]],
    *,
    seed: int,
) -> Tuple[Dict[int, float], List[List[str]], int]:
    km: Dict[int, float] = {}
    zonas_nombres: List[List[str]] = []
    seed_off = seed
    for _gname, ids in sorted(grupos.items()):
        for zona in zonas_sorteo(ids, seed=seed_off):
            zk = km_zona_round_robin(zona, mat)
            acumular_km(km, zk)
            zonas_nombres.append([str(i) for i in zona])
            seed_off += 1
    return km, zonas_nombres, seed_off


def idx_a_equipo(clubs: Sequence[Club]) -> Dict[int, str]:
    return {c.idx: c.equipo for c in clubs}


def resolver_nombres_zonas(
    zonas_idx: List[List[str]], names: Dict[int, str]
) -> List[List[str]]:
    return [[names[int(i)] for i in z] for z in zonas_idx]


def escenario_a(clubs: List[Club], mat: List[List[float]]) -> EscenarioResultado:
    grupos = {r: [c.idx for c in clubs if c.region == r] for r in REGIONES}
    km1, zonas1_idx, seed = simular_fase1_por_grupos(grupos, mat, seed=SEED_SORTEO)
    fase2_ids = top_por_region(clubs)
    km2: Dict[int, float] = {c.idx: 0.0 for c in clubs}
    zonas2_idx: List[List[str]] = []
    for zona in zonas_sorteo(fase2_ids, seed=seed):
        acumular_km(km2, km_zona_round_robin(zona, mat))
        zonas2_idx.append([str(i) for i in zona])
    names = idx_a_equipo(clubs)
    km_total = {c.idx: km1.get(c.idx, 0) + km2.get(c.idx, 0) for c in clubs}
    return EscenarioResultado(
        id="A",
        nombre="4 regiones (fase 1) + 16 sin región (fase 2)",
        descripcion=(
            "Fase 1: zonas de 8 por sorteo dentro de CENTRO, SUR, NORTE y OESTE. "
            "Fase 2: los 4 mejores de cada región (16) juegan 2 zonas metropolitanas de 8."
        ),
        km_por_club={names[i]: km_total[i] for i in km_total},
        km_fase1_por_club={names[i]: km1.get(i, 0) for i in range(len(clubs))},
        km_fase2_por_club={names[i]: km2.get(i, 0) for i in range(len(clubs))},
        zonas_fase1=resolver_nombres_zonas(zonas1_idx, names),
        zonas_fase2=resolver_nombres_zonas(zonas2_idx, names),
    )


def escenario_b(clubs: List[Club], mat: List[List[float]]) -> EscenarioResultado:
    grupos: Dict[str, List[int]] = {}
    for nombre, regs in MIXTAS:
        grupos[nombre] = [c.idx for c in clubs if c.region in regs]
    km1, zonas1_idx, seed = simular_fase1_por_grupos(grupos, mat, seed=SEED_SORTEO + 100)
    fase2_ids = top_por_region(clubs)
    km2: Dict[int, float] = {c.idx: 0.0 for c in clubs}
    zonas2_idx: List[List[str]] = []
    for zona in zonas_sorteo(fase2_ids, seed=seed):
        acumular_km(km2, km_zona_round_robin(zona, mat))
        zonas2_idx.append([str(i) for i in zona])
    names = idx_a_equipo(clubs)
    km_total = {c.idx: km1.get(c.idx, 0) + km2.get(c.idx, 0) for c in clubs}
    return EscenarioResultado(
        id="B",
        nombre="Mixta CENTRO-SUR / NORTE-OESTE + fase 2 metro",
        descripcion=(
            "Fase 1: dos macro-regiones (CENTRO+SUR y NORTE+OESTE), zonas de 8 por sorteo. "
            "Fase 2: mismos 16 clasificados (4/region) en formato metropolitano."
        ),
        km_por_club={names[i]: km_total[i] for i in km_total},
        km_fase1_por_club={names[i]: km1.get(i, 0) for i in range(len(clubs))},
        km_fase2_por_club={names[i]: km2.get(i, 0) for i in range(len(clubs))},
        zonas_fase1=resolver_nombres_zonas(zonas1_idx, names),
        zonas_fase2=resolver_nombres_zonas(zonas2_idx, names),
    )


def escenario_c(clubs: List[Club], mat: List[List[float]]) -> EscenarioResultado:
    todos = [c.idx for c in clubs]
    zonas1 = zonas_sorteo(todos, seed=SEED_SORTEO + 200)
    km1: Dict[int, float] = {}
    zonas1_idx: List[List[str]] = []
    for zona in zonas1:
        acumular_km(km1, km_zona_round_robin(zona, mat))
        zonas1_idx.append([str(i) for i in zona])
    fase2_ids = top_global(clubs, 16)
    km2: Dict[int, float] = {c.idx: 0.0 for c in clubs}
    zonas2_idx: List[List[str]] = []
    for zona in zonas_sorteo(fase2_ids, seed=SEED_SORTEO + 300):
        acumular_km(km2, km_zona_round_robin(zona, mat))
        zonas2_idx.append([str(i) for i in zona])
    names = idx_a_equipo(clubs)
    km_total = {c.idx: km1.get(c.idx, 0) + km2.get(c.idx, 0) for c in clubs}
    return EscenarioResultado(
        id="C",
        nombre="Sin regionalización (sorteo puro)",
        descripcion=(
            "Fase 1: los 42 en zonas de 8 por sorteo sin criterio geográfico. "
            "Fase 2: los 16 mejores globales en 2 zonas de 8."
        ),
        km_por_club={names[i]: km_total[i] for i in km_total},
        km_fase1_por_club={names[i]: km1.get(i, 0) for i in range(len(clubs))},
        km_fase2_por_club={names[i]: km2.get(i, 0) for i in range(len(clubs))},
        zonas_fase1=resolver_nombres_zonas(zonas1_idx, names),
        zonas_fase2=resolver_nombres_zonas(zonas2_idx, names),
    )


def stats_km(km_dict: Dict[str, float]) -> Dict[str, float]:
    vals = sorted(km_dict.values())
    if not vals:
        return {}
    return {
        "media": round(statistics.mean(vals), 1),
        "mediana": round(statistics.median(vals), 1),
        "p90": round(vals[int(len(vals) * 0.9) - 1], 1),
        "max": round(max(vals), 1),
        "min": round(min(vals), 1),
    }


def analizar_mal_regionalizados(clubs: Sequence[Club]) -> List[dict]:
    rows = []
    for c in clubs:
        if c.mal_regionalizado:
            rows.append(
                {
                    "equipo": c.equipo,
                    "region_febamba": c.region,
                    "region_geografica": c.region_geo,
                    "zona": c.zona_febamba,
                }
            )
    return rows


def compactar_intra_zona_media(
    clubs: List[Club], mat: List[List[float]], esc: EscenarioResultado
) -> float:
    """Distancia media entre pares dentro de zonas fase 1 (indicador de compactación)."""
    names = {c.equipo: c.idx for c in clubs}
    dists: List[float] = []
    for zona in esc.zonas_fase1:
        idxs = [names[n] for n in zona]
        for i, a in enumerate(idxs):
            for b in idxs[i + 1 :]:
                dists.append(dist_km(mat, a, b))
    return round(statistics.mean(dists), 1) if dists else 0.0


def ejecutar() -> dict:
    clubs, mat = cargar_clubes()
    asignar_region_geografica(clubs)
    escenarios = [escenario_a(clubs, mat), escenario_b(clubs, mat), escenario_c(clubs, mat)]
    for e in escenarios:
        e.stats = stats_km(e.km_por_club)
        e.stats["intra_zona_media_km"] = compactar_intra_zona_media(clubs, mat, e)

    mal = analizar_mal_regionalizados(clubs)
    conteo_region = {r: sum(1 for c in clubs if c.region == r) for r in REGIONES}

    payload = {
        "parametros": {
            "tam_zona": TAM_ZONA,
            "avanzan_por_region": AVANZAN_POR_REGION,
            "seed_sorteo": SEED_SORTEO,
            "ida_vuelta": True,
        },
        "conteo_por_region": conteo_region,
        "mal_regionalizados": mal,
        "escenarios": [
            {
                "id": e.id,
                "nombre": e.nombre,
                "descripcion": e.descripcion,
                "stats": e.stats,
                "zonas_fase1": e.zonas_fase1,
                "zonas_fase2": e.zonas_fase2,
                "km_por_club": e.km_por_club,
                "km_fase1_por_club": e.km_fase1_por_club,
                "km_fase2_por_club": e.km_fase2_por_club,
            }
            for e in escenarios
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with ESCENARIOS_JSON.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


def _tabla_escenarios(payload: dict) -> str:
    rows = []
    for e in payload["escenarios"]:
        s = e["stats"]
        rows.append(
            f"<tr><td><strong>{html.escape(e['id'])}</strong></td>"
            f"<td>{html.escape(e['nombre'])}</td>"
            f"<td>{s['media']}</td><td>{s['mediana']}</td><td>{s['p90']}</td>"
            f"<td>{s['max']}</td><td>{s.get('intra_zona_media_km', '—')}</td></tr>"
        )
    return "\n".join(rows)


def _tabla_mal(payload: dict) -> str:
    if not payload["mal_regionalizados"]:
        return "<p>Ningún club del élite 42 queda en región distinta a la geográfica sugerida.</p>"
    rows = []
    for m in payload["mal_regionalizados"]:
        rows.append(
            f"<tr><td>{html.escape(m['equipo'])}</td>"
            f"<td>{html.escape(m['region_febamba'])}</td>"
            f"<td>{html.escape(m['region_geografica'])}</td>"
            f"<td>{html.escape(m['zona'])}</td></tr>"
        )
    return (
        "<table><thead><tr><th>Equipo</th><th>Región FeBAMBA</th>"
        "<th>Región geo.</th><th>Zona</th></tr></thead><tbody>"
        + "\n".join(rows)
        + "</tbody></table>"
    )


def generar_informe(payload: dict, out: Path = INFORME_HTML) -> Path:
    esc = payload["escenarios"]
    mejor = min(esc, key=lambda e: e["stats"]["mediana"])
    out.write_text(
        f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"/>
<title>Escenarios de viaje · Élite 42</title>
<style>
  body {{ font-family: Segoe UI, sans-serif; margin:0; background:#f8fafc; color:#0f172a; }}
  header {{ background:#0f172a; color:#fff; padding:24px 28px; }}
  main {{ max-width:1100px; margin:0 auto; padding:24px 28px 40px; }}
  table {{ width:100%; border-collapse:collapse; background:#fff; margin:16px 0; font-size:.9rem; }}
  th, td {{ border-bottom:1px solid #e2e8f0; padding:8px 10px; text-align:left; }}
  th {{ background:#f1f5f9; }}
  .card {{ background:#fff; border-radius:10px; padding:16px 18px; margin:16px 0;
    box-shadow:0 1px 4px rgba(15,23,42,.08); }}
  .hl {{ color:#1d4ed8; font-weight:600; }}
</style></head><body>
<header><h1>Simulación de viajes · Élite 42</h1>
<p>Fase 1 en zonas de 8 · Fase 2: 16 equipos (4 por región) en 2 zonas metropolitanas.
Distancias ida y vuelta (Haversine). Sorteo determinístico (seed={SEED_SORTEO}).</p></header>
<main>
  <div class="card">
    <p>Mejor mediana de km/temporada: <span class="hl">Escenario {html.escape(mejor['id'])}</span>
    ({mejor['stats']['mediana']} km).</p>
    <p>Equipos por región FeBAMBA: {html.escape(str(payload['conteo_por_region']))}</p>
  </div>
  <h2>Comparativa de escenarios</h2>
  <table>
    <thead><tr><th>ID</th><th>Escenario</th><th>Media km</th><th>Mediana</th>
    <th>P90</th><th>Máx</th><th>Dist. intra-zona F1</th></tr></thead>
    <tbody>{_tabla_escenarios(payload)}</tbody>
  </table>
  <h2>Posibles mal regionalizados</h2>
  <p>Clubes cuya sede está más cerca del centroide de otra región que de la asignada en FeBAMBA.</p>
  {_tabla_mal(payload)}
  <h2>Detalle por escenario</h2>
  {"".join(f'<div class="card"><h3>{html.escape(e["id"])} — {html.escape(e["nombre"])}</h3><p>{html.escape(e["descripcion"])}</p></div>' for e in esc)}
</main></body></html>""",
        encoding="utf-8",
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--informe", action="store_true")
    args = ap.parse_args()
    payload = ejecutar()
    print(f"Escenarios: {ESCENARIOS_JSON}")
    for e in payload["escenarios"]:
        s = e["stats"]
        print(f"  {e['id']}: mediana={s['mediana']} km  media={s['media']}  max={s['max']}")
    if payload["mal_regionalizados"]:
        print(f"Mal regionalizados: {len(payload['mal_regionalizados'])}")
        for m in payload["mal_regionalizados"]:
            print(f"  {m['equipo']}: {m['region_febamba']} -> geo {m['region_geografica']}")
    if args.informe:
        p = generar_informe(payload)
        print(f"Informe: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
