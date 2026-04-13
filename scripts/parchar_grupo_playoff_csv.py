# -*- coding: utf-8 -*-
"""
Recalcula la columna ``grupo`` en Playoff / Final Four como ``local-visitante`` (llave),
igual que el scraper tras el fix de ``inferir_ronda`` — **sin** volver a scrapear.

Solo toca filas cuyo ``grupo`` es placeholder (Desconocido, LLAVE DE PLAYOFF EQUIPOS, …).

Uso:
  python scripts/parchar_grupo_playoff_csv.py Data/raw/formativas_1623_2025_FORMATIVAS_2025.csv \\
      -o Data/raw/formativas_1623_2025_FORMATIVAS_2025_patched.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd

from mapeos.loader import cargar_mapeo_equipos, normalizar_equipo
from utils.logger import get_logger
from utils.open_csv import leer_csv_autodetect

logger = get_logger(__name__)

_PLACEHOLDER_GRUPO = frozenset(
    {
        "",
        "desconocido",
        "desconocida",
        "llave de playoff equipos",
        "nan",
    }
)


def _es_playoff_o_final_four(fase: object) -> bool:
    u = str(fase or "").upper().strip()
    return u in ("PLAYOFF", "FINAL FOUR")


def _grupo_es_placeholder(val: object) -> bool:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return True
    return str(val).strip().lower() in _PLACEHOLDER_GRUPO


def parchar_grupo_llave(
    ruta_entrada: Path,
    ruta_salida: Path,
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Devuelve (filas_leídas, filas_actualizadas).
    """
    df = leer_csv_autodetect(str(ruta_entrada))
    if "grupo" not in df.columns or "local" not in df.columns or "visitante" not in df.columns:
        raise ValueError("El CSV debe incluir columnas grupo, local y visitante.")

    mapeo = cargar_mapeo_equipos()
    n = len(df)
    cambios = 0
    for i in df.index:
        if not _es_playoff_o_final_four(df.at[i, "fase"]):
            continue
        if not _grupo_es_placeholder(df.at[i, "grupo"]):
            continue
        loc = normalizar_equipo(str(df.at[i, "local"]), mapeo)
        vis = normalizar_equipo(str(df.at[i, "visitante"]), mapeo)
        df.at[i, "grupo"] = f"{loc}-{vis}"
        cambios += 1

    if dry_run:
        logger.info("[dry-run] Se habrían actualizado %s de %s filas", cambios, n)
        return n, cambios

    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta_salida, index=False, encoding="utf-8-sig")
    logger.info("Escrito %s — %s filas con grupo recalculado (total %s)", ruta_salida, cambios, n)
    return n, cambios


def main() -> None:
    p = argparse.ArgumentParser(description="Parchar grupo=local-visitante en Playoff/Final Four sin re-scrape.")
    p.add_argument("entrada", type=Path, help="CSV crudo existente")
    p.add_argument("-o", "--salida", type=Path, required=True, help="CSV de salida")
    p.add_argument("--dry-run", action="store_true", help="Solo contar filas a cambiar")
    args = p.parse_args()
    parchar_grupo_llave(args.entrada, args.salida, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
