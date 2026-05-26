# -*- coding: utf-8 -*-
"""
Purifica equipos_map.json: claves normalizadas, sin entradas identidad redundantes.

  python pipelines/purificar_equipos_map.py
  python pipelines/purificar_equipos_map.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mapeos.loader import clave_mapeo, guardar_mapeo_equipos  # noqa: E402

EQUIPOS_MAP_PATH = ROOT / "mapeos" / "equipos_map.json"


def purificar(mapeo: dict[str, str]) -> tuple[dict[str, str], dict]:
    stats = {
        "entrada": len(mapeo),
        "identidad_omitida": 0,
        "clave_vacia": 0,
        "destino_vacio": 0,
    }
    limpio: dict[str, str] = {}
    for origen, destino in mapeo.items():
        k = clave_mapeo(origen)
        v = str(destino).strip() if destino is not None else ""
        if not k:
            stats["clave_vacia"] += 1
            continue
        if not v:
            stats["destino_vacio"] += 1
            continue
        if k == clave_mapeo(v):
            stats["identidad_omitida"] += 1
            continue
        limpio[k] = v
    stats["salida"] = len(limpio)
    return dict(sorted(limpio.items())), stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Purificar equipos_map.json")
    p.add_argument("--dry-run", action="store_true", help="Solo mostrar estadísticas.")
    p.add_argument("--output", type=Path, default=EQUIPOS_MAP_PATH)
    args = p.parse_args(argv)

    with open(EQUIPOS_MAP_PATH, encoding="utf-8") as f:
        raw = json.load(f)

    limpio, stats = purificar(raw)
    print(f"Entradas originales: {stats['entrada']}")
    print(f"  Omitidas (identidad): {stats['identidad_omitida']}")
    print(f"  Clave/destino vacío: {stats['clave_vacia'] + stats['destino_vacio']}")
    print(f"Entradas finales: {stats['salida']}")

    if not args.dry_run:
        if args.output == EQUIPOS_MAP_PATH:
            guardar_mapeo_equipos(limpio)
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(limpio, f, ensure_ascii=False, indent=2)
                f.write("\n")
        print(f"Guardado: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
