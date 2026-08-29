# -*- coding: utf-8 -*-
"""
Resume en un CSV (una fila por equipo) las estadísticas de todas las fases
del campeonato FEB, sumando totales y recalculando medias.

Excluye la fila agregada PLAY-OFF (fase_id=-44960) porque duplica los
partidos de las rondas de playoff desglosadas.

Ejemplo:
  python analysis/sumarizar_feb_temporada.py
  python analysis/sumarizar_feb_temporada.py --input outputs/feb/lanzamiento_cespclubescadmasc_2025_todas.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent

# Fase agregada de playoff: repite datos ya presentes en 1/8, 1/4, etc.
FASES_EXCLUIR = {"-44960"}


@dataclass
class AcumEquipo:
    equipo: str
    competicion: str = ""
    edad: str = ""
    temporada: str = ""
    partidos: int = 0
    pts_total: int = 0
    tl_total: int = 0
    tl_aciertos: int = 0
    t2_total: int = 0
    t2_aciertos: int = 0
    t3_total: int = 0
    t3_aciertos: int = 0
    fases: List[str] = field(default_factory=list)


def _norm_equipo(nombre: str) -> str:
    t = unicodedata.normalize("NFKD", nombre or "")
    t = t.encode("ascii", "ignore").decode("ascii")
    return " ".join(t.upper().replace('"', "").split())


def _pct(a: int, i: int) -> str:
    if i <= 0:
        return ""
    return f"{100.0 * a / i:.1f}"


def _pp(total: float, n: int) -> str:
    if n <= 0:
        return ""
    return f"{total / n:.2f}"


def _efg(fgm: int, tpm: int, fga: int) -> str:
    if fga <= 0:
        return ""
    return f"{100.0 * (fgm + 0.5 * tpm) / fga:.1f}"


def _ts(pts: int, fga: int, fta: int) -> str:
    denom = 2 * (fga + 0.44 * fta)
    if denom <= 0:
        return ""
    return f"{100.0 * pts / denom:.1f}"


def _int(val: object) -> int:
    try:
        return int(float(str(val).strip() or "0"))
    except ValueError:
        return 0


def cargar_y_resumir(path: Path) -> List[AcumEquipo]:
    por_equipo: Dict[str, AcumEquipo] = {}
    # Evita duplicar si la FEB repite el mismo equipo en la misma fase (ej. con/sin tilde).
    visto_fase: set[tuple[str, str]] = set()

    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            fase_id = str(row.get("fase_id", "")).strip()
            if fase_id in FASES_EXCLUIR:
                continue

            nombre = row.get("equipo", "").strip()
            if not nombre:
                continue

            key = _norm_equipo(nombre)
            dedupe_key = (key, fase_id)
            if dedupe_key in visto_fase:
                continue
            visto_fase.add(dedupe_key)

            if key not in por_equipo:
                por_equipo[key] = AcumEquipo(
                    equipo=nombre,
                    competicion=row.get("competicion", ""),
                    edad=row.get("edad", ""),
                    temporada=row.get("temporada", ""),
                )

            ac = por_equipo[key]
            fase = row.get("fase", "").strip()
            if fase and fase not in ac.fases:
                ac.fases.append(fase)

            ac.partidos += _int(row.get("partidos"))
            ac.pts_total += _int(row.get("pts_total"))
            ac.tl_total += _int(row.get("tl_total"))
            ac.tl_aciertos += _int(row.get("tl_aciertos"))
            ac.t2_total += _int(row.get("t2_total"))
            ac.t2_aciertos += _int(row.get("t2_aciertos"))
            ac.t3_total += _int(row.get("t3_total"))
            ac.t3_aciertos += _int(row.get("t3_aciertos"))

    return sorted(por_equipo.values(), key=lambda x: x.equipo)


def escribir_csv(path: Path, rows: List[AcumEquipo]) -> None:
    fieldnames = [
        "competicion",
        "edad",
        "temporada",
        "equipo",
        "partidos",
        "fases_jugadas",
        "pts_total",
        "pts_pp",
        "tl_total",
        "tl_pp",
        "tl_aciertos",
        "tl_aciertos_pp",
        "tl_pct",
        "t2_total",
        "t2_pp",
        "t2_aciertos",
        "t2_aciertos_pp",
        "t2_pct",
        "t3_total",
        "t3_pp",
        "t3_aciertos",
        "t3_aciertos_pp",
        "t3_pct",
        "fg_pct",
        "efg_pct",
        "ts_pct",
    ]

    out_rows = []
    for r in rows:
        p = r.partidos
        fgm = r.t2_aciertos + r.t3_aciertos
        fga = r.t2_total + r.t3_total
        out_rows.append(
            {
                "competicion": r.competicion,
                "edad": r.edad,
                "temporada": r.temporada,
                "equipo": r.equipo,
                "partidos": p,
                "fases_jugadas": len(r.fases),
                "pts_total": r.pts_total,
                "pts_pp": _pp(r.pts_total, p),
                "tl_total": r.tl_total,
                "tl_pp": _pp(r.tl_total, p),
                "tl_aciertos": r.tl_aciertos,
                "tl_aciertos_pp": _pp(r.tl_aciertos, p),
                "tl_pct": _pct(r.tl_aciertos, r.tl_total),
                "t2_total": r.t2_total,
                "t2_pp": _pp(r.t2_total, p),
                "t2_aciertos": r.t2_aciertos,
                "t2_aciertos_pp": _pp(r.t2_aciertos, p),
                "t2_pct": _pct(r.t2_aciertos, r.t2_total),
                "t3_total": r.t3_total,
                "t3_pp": _pp(r.t3_total, p),
                "t3_aciertos": r.t3_aciertos,
                "t3_aciertos_pp": _pp(r.t3_aciertos, p),
                "t3_pct": _pct(r.t3_aciertos, r.t3_total),
                "fg_pct": _pct(fgm, fga),
                "efg_pct": _efg(fgm, r.t3_aciertos, fga),
                "ts_pct": _ts(r.pts_total, fga, r.tl_total),
            }
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)


def main() -> int:
    p = argparse.ArgumentParser(description="Resume fases FEB en un CSV por equipo")
    p.add_argument(
        "--input",
        default=str(ROOT / "outputs" / "feb" / "lanzamiento_cespclubescadmasc_2025_todas.csv"),
    )
    p.add_argument("--output", default="", help="CSV de salida")
    args = p.parse_args()

    inp = Path(args.input)
    if not inp.exists():
        print(f"No existe el archivo: {inp}", file=sys.stderr)
        return 1

    rows = cargar_y_resumir(inp)
    if not rows:
        print("Sin filas para resumir", file=sys.stderr)
        return 1

    stem = inp.stem.replace("_todas", "")
    out = Path(args.output) if args.output else inp.parent / f"{stem}_resumen.csv"
    escribir_csv(out, rows)

    print(f"Equipos: {len(rows)}")
    print(f"Guardado: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
