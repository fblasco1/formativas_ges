# -*- coding: utf-8 -*-
"""
Importa datos de referencia del trabajo ENEBA 2024 (DOC-20260524-WA0098.docx)
sobre FeBAMBA vs Liga Federal Formativa U15 (doble competencia).

Genera CSVs reutilizables cuando no hay acceso histórico automatizado a LFF 2024.

  python analysis/importar_referencia_eneba_2024.py
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
REF_JSON = ROOT / "data" / "referencia" / "eneba_febamba_lff_2024.json"


def _load() -> Dict[str, Any]:
    with REF_JSON.open(encoding="utf-8") as f:
        return json.load(f)


def _write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def exportar(out_dir: Path) -> None:
    data = _load()
    out_dir.mkdir(parents=True, exist_ok=True)

    agg = data["promedios_agregados"]
    rows_agg = [
        {
            "liga": "FeBAMBA U15",
            "temporada": "2024",
            "t3_pp_intentados": agg["febamba"]["t3_pp_intentados"],
            "t3_pp_anotados": agg["febamba"]["t3_pp_anotados"],
            "fuente": data["fuente"],
        },
        {
            "liga": "LFF interior U15",
            "temporada": "2024",
            "t3_pp_intentados": agg["liga_federal_interior"]["t3_pp_intentados"],
            "t3_pp_anotados": agg["liga_federal_interior"]["t3_pp_anotados"],
            "fuente": data["fuente"],
        },
    ]
    p_agg = out_dir / "referencia_promedios_u15_2024.csv"
    _write_csv(
        p_agg,
        rows_agg,
        ["liga", "temporada", "t3_pp_intentados", "t3_pp_anotados", "fuente"],
    )

    rows_lff = []
    for eq in data["equipos_liga_federal_u15_2024"]:
        rows_lff.append(
            {
                "equipo": eq,
                "competicion": "Liga Federal Formativa U15",
                "temporada": "2024",
                "fuente": data["fuente"],
            }
        )
    p_lff = out_dir / "referencia_equipos_lff_interior_2024.csv"
    _write_csv(p_lff, rows_lff, ["equipo", "competicion", "temporada", "fuente"])

    rows_feb = []
    for eq in data["equipos_febamba_2024"]:
        rows_feb.append(
            {
                "equipo": eq,
                "competicion": "FeBAMBA U15",
                "temporada": "2024",
                "fuente": data["fuente"],
            }
        )
    p_feb = out_dir / "referencia_equipos_febamba_2024.csv"
    _write_csv(p_feb, rows_feb, ["equipo", "competicion", "temporada", "fuente"])

    rows_doble: List[Dict[str, Any]] = []
    com = data.get("comunicaciones_detalle", {})
    if com:
        lf = com.get("liga_federal", {})
        rows_doble.append(
            {
                "equipo": "COMUNICACIONES",
                "doble_competencia": "si",
                "partidos_lff": lf.get("partidos", ""),
                "t3_total_lff": lf.get("t3_total", ""),
                "t3_aciertos_lff": lf.get("t3_aciertos", ""),
                "t3_pct_lff": lf.get("t3_pct", ""),
                "t3_pp_lff": lf.get("t3_pp", ""),
                "t3_aciertos_pp_lff": lf.get("t3_aciertos_pp", ""),
                "t3_total_feb": com.get("febamba", {}).get("t3_total", ""),
                "t3_aciertos_feb": com.get("febamba", {}).get("t3_aciertos", ""),
                "t3_pct_feb": com.get("febamba", {}).get("t3_pct", ""),
                "notas": com.get("febamba", {}).get("nota", ""),
                "fuente": data["fuente"],
            }
        )

    for eq, vals in data.get("doble_competencia_aprox_pp", {}).items():
        if eq == "COMUNICACIONES":
            continue
        rows_doble.append(
            {
                "equipo": eq,
                "doble_competencia": "si",
                "t3_pp_lff": vals.get("lff_t3_pp", ""),
                "t3_aciertos_pp_lff": vals.get("lff_t3_aciertos_pp", ""),
                "t3_pp_feb": vals.get("feb_t3_pp", ""),
                "notas": "Valores aproximados — lectura visual del gráfico ENEBA",
                "fuente": data["fuente"],
            }
        )

    p_doble = out_dir / "referencia_doble_competencia_u15_2024.csv"
    _write_csv(
        p_doble,
        rows_doble,
        [
            "equipo",
            "doble_competencia",
            "partidos_lff",
            "t3_pp_lff",
            "t3_aciertos_pp_lff",
            "t3_total_lff",
            "t3_aciertos_lff",
            "t3_pct_lff",
            "t3_pp_feb",
            "t3_total_feb",
            "t3_aciertos_feb",
            "t3_pct_feb",
            "notas",
            "fuente",
        ],
    )

    print(f"Promedios: {p_agg}")
    print(f"Equipos LFF interior: {p_lff} ({len(rows_lff)} filas)")
    print(f"Equipos FeBAMBA: {p_feb} ({len(rows_feb)} filas)")
    print(f"Doble competencia: {p_doble} ({len(rows_doble)} filas)")


def main() -> int:
    p = argparse.ArgumentParser(description="Importar referencia ENEBA FeBAMBA vs LFF 2024")
    p.add_argument(
        "--output-dir",
        default=str(ROOT / "outputs" / "lff" / "referencia_2024"),
    )
    args = p.parse_args()
    if not REF_JSON.exists():
        print(f"No existe {REF_JSON}", file=sys.stderr)
        return 1
    exportar(Path(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
