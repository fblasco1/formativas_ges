# -*- coding: utf-8 -*-
"""
Extrae el top 42 de la tabla general de tiras y lo empareja con el padrón federativo.

  python analysis/emparejar_clubes_federacion.py
  python analysis/emparejar_clubes_federacion.py --geocodificar
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
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

cargar_elite42 = _mod.cargar_elite42
cargar_federacion = _mod.cargar_federacion
emparejar_elite_con_federacion = _mod.emparejar_elite_con_federacion
exportar_elite_csv = _mod.exportar_elite_csv
exportar_mapeo_csv = _mod.exportar_mapeo_csv
geocodificar_mapeos = _mod.geocodificar_mapeos
matriz_distancias = _mod.matriz_distancias
ELITE42_CSV = _mod.ELITE42_CSV
GEOJSON = _mod.GEOJSON
MAPEO_CSV = _mod.MAPEO_CSV
OUT_DIR = _mod.OUT_DIR


def main() -> int:
    ap = argparse.ArgumentParser(description="Empareja élite 42 con afiliadas FeBAMBA")
    ap.add_argument(
        "--top",
        type=int,
        default=None,
        help="Top N de la tabla general (default: todos)",
    )
    ap.add_argument(
        "--fase",
        default="PRIMERA",
        help="PRIMERA (Clasificación+Reclasificación), CLASIFICACION o RECLASIFICACION",
    )
    ap.add_argument("--geocodificar", action="store_true")
    ap.add_argument("--regeocodificar", action="store_true", help="Ignora caché de geocodificación")
    ap.add_argument("--xlsx", type=Path, default=None)
    args = ap.parse_args()

    elite = cargar_elite42(fase=args.fase, top_n=args.top)
    fed = cargar_federacion(args.xlsx)
    mapeos = emparejar_elite_con_federacion(elite, fed)
    mapeos = _mod.aplicar_sedes_confirmadas(mapeos)

    exportar_elite_csv(elite, ELITE42_CSV)
    exportar_mapeo_csv(mapeos, MAPEO_CSV)

    n_eq = len(elite)
    label = f"Top {args.top}" if args.top else f"Tabla completa ({n_eq})"
    print(f"{label}: {ELITE42_CSV}")
    print(f"Mapeo: {MAPEO_CSV}")
    print(f"Afiliadas cargadas: {len(fed)}")
    print()

    conf = {}
    for m in mapeos:
        conf[m.confianza] = conf.get(m.confianza, 0) + 1
    print("Confianza:", conf)
    print()

    revision = [m for m in mapeos if m.confianza in {"revision", "bajo"}]
    sin_padron = [m for m in mapeos if m.confianza == "sin_padron"]
    if sin_padron:
        print("Sin padrón federativo (completar sede en mapeo_clubes.csv):")
        for m in sin_padron:
            print(f"  #{m.pos:2d} {m.equipo}")
        print()

    if revision:
        print("Revisar manualmente:")
        for m in revision:
            print(f"  #{m.pos:2d} {m.equipo} -> {m.afiliada} (score={m.score})")
        print()

    if args.geocodificar:
        print("Geocodificando (Nominatim, puede tardar ~1 min)...")
        mapeos = geocodificar_mapeos(mapeos, forzar=args.regeocodificar)
        exportar_mapeo_csv(mapeos, MAPEO_CSV)
        ok = sum(1 for m in mapeos if m.lat is not None)
        print(f"Geocodificados: {ok}/{len(mapeos)} -> {GEOJSON}")

        nombres, mat = matriz_distancias(mapeos)
        dist_path = OUT_DIR / "matriz_distancias_km.json"
        with dist_path.open("w", encoding="utf-8") as f:
            json.dump({"equipos": nombres, "km": mat}, f, ensure_ascii=False, indent=2)
        print(f"Matriz distancias: {dist_path}")

        vals = [v for row in mat for v in row if v and v > 0]
        if vals:
            vals_sorted = sorted(vals)
            print(
                f"Distancia km (haversine): min={vals_sorted[0]:.1f} "
                f"mediana={vals_sorted[len(vals_sorted)//2]:.1f} "
                f"max={vals_sorted[-1]:.1f}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
