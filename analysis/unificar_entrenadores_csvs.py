# -*- coding: utf-8 -*-
"""
Fusiona varios CSV con columnas Categoria, Equipo, Entrenador, unifica
(una fila por tripleta, sin entrenador vacío) y ordena como
``extraer_entrenadores_partidos_2026.py``.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from extraer_entrenadores_partidos_2026 import (  # noqa: E402
    _fieldnames,
    _postprocesar_filas_entrenadores,
)


def _cargar_csv(path: str) -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--entrada",
        action="append",
        dest="entradas",
        default=[],
        help="CSV a fusionar (repetible). Por defecto: formativas 2026 + Superior 5074.",
    )
    p.add_argument(
        "--out",
        default="entrenadores_unificado_formativas_y_superior.csv",
        help="CSV de salida unificado.",
    )
    args = p.parse_args()

    paths = args.entradas or [
        "entrenadores_partidos_2026.csv",
        "entrenadores_superior_masculino_5074.csv",
    ]

    todas: List[Dict[str, str]] = []
    for path in paths:
        try:
            todas.extend(_cargar_csv(path))
        except OSError as e:
            print(f"Error leyendo {path}: {e}", file=sys.stderr)
            return 1

    out_rows = _postprocesar_filas_entrenadores(
        todas,
        mantener_duplicados=False,
        mantener_sin_entrenador=False,
    )

    fn = _fieldnames()
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fn)
        w.writeheader()
        for row in out_rows:
            w.writerow({k: row.get(k, "") for k in fn})

    print(f"Fuentes: {len(paths)} archivo(s)")
    print(f"Filas tras unificar: {len(out_rows)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
