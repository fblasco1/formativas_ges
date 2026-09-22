# -*- coding: utf-8 -*-
"""
Recalcula la matriz de distancias entre clubes con OSRM (ruta vial).

Usa el Table API público (o un servidor propio) en bloques, con fallback
haversine si un par no resuelve.

  python analysis/calcular_matriz_osrm.py
  python analysis/calcular_matriz_osrm.py --chunk 35 --base-url https://router.project-osrm.org
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "viajes_elite42_common",
    ROOT / "analysis" / "viajes_elite42_common.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

MAPEO_CSV = _mod.MAPEO_CSV
OUT_DIR = _mod.OUT_DIR
MapeoClub = _mod.MapeoClub
matriz_distancias_osrm = _mod.matriz_distancias_osrm

DIST_PATH = OUT_DIR / "matriz_distancias_km.json"
META_PATH = OUT_DIR / "matriz_distancias_meta.json"


def _cargar_mapeos_desde_csv() -> list:
    if not MAPEO_CSV.exists():
        raise SystemExit(f"Falta {MAPEO_CSV}. Corré emparejar_clubes_federacion.py --geocodificar")
    rows = list(csv.DictReader(MAPEO_CSV.open(encoding="utf-8-sig", newline="")))
    mapeos = []
    for r in rows:
        mapeos.append(
            MapeoClub(
                pos=int(r["pos"]),
                equipo=r["equipo"],
                clave=r.get("clave") or "",
                zona=r.get("zona") or "",
                puntos=int(float(r["puntos"])),
                afiliada=r.get("afiliada") or "",
                direccion=r.get("direccion") or "",
                cod_postal=r.get("cod_postal") or "",
                confianza=r.get("confianza") or "",
                score=float(r["score"]) if r.get("score") else 0.0,
                lat=float(r["lat"]) if r.get("lat") else None,
                lon=float(r["lon"]) if r.get("lon") else None,
                geocode_precision=r.get("geocode_precision") or "",
                fase=r.get("fase") or "CLASIFICACION",
            )
        )
    return mapeos


def main() -> int:
    ap = argparse.ArgumentParser(description="Matriz de distancias OSRM (ruta vial)")
    ap.add_argument("--base-url", default="https://router.project-osrm.org")
    ap.add_argument("--chunk", type=int, default=40, help="Coords por bloque (<=100)")
    ap.add_argument("--pause", type=float, default=0.35, help="Segundos entre requests")
    args = ap.parse_args()

    mapeos = _cargar_mapeos_desde_csv()
    ok = sum(1 for m in mapeos if m.lat is not None)
    print(f"Mapeo: {len(mapeos)} clubes · {ok} geocodificados")
    print(f"OSRM: {args.base_url} · chunk={args.chunk}")

    nombres, mat, meta = matriz_distancias_osrm(
        mapeos,
        base_url=args.base_url,
        chunk_size=args.chunk,
        pause_s=args.pause,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with DIST_PATH.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "equipos": nombres,
                "km": mat,
                "modo": "osrm",
                "meta": meta,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    with META_PATH.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    vals = [v for row in mat for v in row if v and v > 0]
    print(f"Matriz: {DIST_PATH}")
    print(
        f"OSRM ok={meta['n_osrm']} · fallback haversine={meta['n_fallback_haversine']} · "
        f"nulls OSRM={meta['n_fallidos']}"
    )
    if vals:
        vs = sorted(vals)
        print(
            f"km ruta: min={vs[0]:.1f} mediana={vs[len(vs)//2]:.1f} max={vs[-1]:.1f}"
        )
    if meta["errores"]:
        print(f"Errores ({len(meta['errores'])}): {meta['errores'][:3]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
