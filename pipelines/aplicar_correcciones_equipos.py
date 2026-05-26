# -*- coding: utf-8 -*-
"""Fusiona mapeos/equipos_correcciones_usuario.json en equipos_map.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mapeos.loader import agregar_entradas_mapeo, clave_mapeo

CORRECCIONES = ROOT / "mapeos" / "equipos_correcciones_usuario.json"


def main() -> int:
    with open(CORRECCIONES, encoding="utf-8") as f:
        data = json.load(f)
    entradas = {
        clave_mapeo(k): str(v).strip()
        for k, v in data.items()
        if not str(k).startswith("_")
    }
    agregar_entradas_mapeo(entradas)
    print(f"Actualizado equipos_map.json ({len(entradas)} entradas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
