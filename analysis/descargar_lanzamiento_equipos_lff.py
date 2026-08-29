# -*- coding: utf-8 -*-
"""
Descarga estadísticas de lanzamiento por equipo (promedio por partido) de la
Liga Federal Formativa — categoría U15 (Cadetes) desde argentina.basketball.

Fuente: Comparativa de Equipos (no disponible en GES para esta categoría).
  https://argentina.basketball/liga-federal/comparativa-equipos/{compCatId}

Ejemplo Cadetes masculino 2025 (compCatId 4643):
  python analysis/descargar_lanzamiento_equipos_lff.py --temporada 2025 --genero masc
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.argbasket.lff_constants import (
    BASE_URL,
    LFF_U15_DETALLE_URL,
    LFF_U15_TORNEO_COMP_CAT_ID,
)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/138.0.0.0 Safari/537.36"}

# Índices de celdas en #tabla-comparativa-equipos (columnas de lanzamiento).
COL_PARTIDOS = 1
COL_TL = slice(4, 8)   # total, PP, aciertos, %
COL_T2 = slice(8, 12)
COL_T3 = slice(12, 16)


def _nombre_equipo(tr) -> str:
    p = tr.select_one("#nombre-equipo")
    if p:
        return p.get_text(strip=True)
    cells = tr.find_all("td")
    return cells[0].get_text(strip=True) if cells else ""


def _celdas_fila(tr) -> List[str]:
    return [td.get_text(strip=True) for td in tr.find_all("td")]


def _aciertos_pp(aciertos: str, partidos: str) -> str:
    try:
        a = float(aciertos.replace(",", "."))
        p = int(partidos)
    except (ValueError, TypeError):
        return ""
    if p <= 0:
        return ""
    return f"{round(a / p, 1)}".replace(".", ",")


def fetch_comparativa_html(comp_cat_id: int, *, session: Optional[requests.Session] = None) -> str:
    s = session or requests.Session()
    url = f"{BASE_URL}/liga-federal/comparativa-equipos/{comp_cat_id}"
    r = s.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text


def parse_comparativa_lanzamiento(html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("#tabla-comparativa-equipos table")
    if not table:
        raise RuntimeError("No se encontró #tabla-comparativa-equipos en la página")

    rows: List[Dict[str, str]] = []
    for tr in table.select("tbody tr"):
        cells = _celdas_fila(tr)
        if len(cells) < 16:
            continue
        equipo = _nombre_equipo(tr)
        if not equipo:
            continue

        partidos = cells[COL_PARTIDOS]
        tl = cells[COL_TL]
        t2 = cells[COL_T2]
        t3 = cells[COL_T3]

        rows.append(
            {
                "equipo": equipo,
                "partidos": partidos,
                "tl_total": tl[0],
                "tl_pp": tl[1],
                "tl_aciertos": tl[2],
                "tl_aciertos_pp": _aciertos_pp(tl[2], partidos),
                "tl_pct": tl[3],
                "t2_total": t2[0],
                "t2_pp": t2[1],
                "t2_aciertos": t2[2],
                "t2_aciertos_pp": _aciertos_pp(t2[2], partidos),
                "t2_pct": t2[3],
                "t3_total": t3[0],
                "t3_pp": t3[1],
                "t3_aciertos": t3[2],
                "t3_aciertos_pp": _aciertos_pp(t3[2], partidos),
                "t3_pct": t3[3],
            }
        )
    if not rows:
        raise RuntimeError("La comparativa no tiene filas de equipos")
    return rows


def escribir_csv(
    path: Path,
    rows: List[Dict[str, str]],
    *,
    comp_cat_id: int,
    categoria: str,
    temporada: str,
    fuente_url: str,
) -> None:
    fieldnames = [
        "comp_cat_id",
        "categoria",
        "temporada",
        "fuente_url",
        "equipo",
        "partidos",
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
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in sorted(rows, key=lambda r: r["equipo"]):
            w.writerow(
                {
                    "comp_cat_id": comp_cat_id,
                    "categoria": categoria,
                    "temporada": temporada,
                    "fuente_url": fuente_url,
                    **row,
                }
            )


def main() -> int:
    p = argparse.ArgumentParser(
        description="Lanzamiento por equipo (promedio) — LFF Cadetes U15 desde argentina.basketball"
    )
    p.add_argument("--temporada", default="2025", help="Temporada (metadata en CSV)")
    p.add_argument("--genero", choices=("masc", "fem"), default="masc")
    p.add_argument(
        "--comp-cat-id",
        type=int,
        default=0,
        help="compCatId argentina.basketball (default: 4643 masc / 4644 fem)",
    )
    p.add_argument("--output", default="", help="CSV salida")
    p.add_argument("--timeout", type=int, default=60)
    args = p.parse_args()

    genero_lbl = "masculino" if args.genero == "masc" else "femenino"
    comp_cat_id = args.comp_cat_id or LFF_U15_TORNEO_COMP_CAT_ID[args.genero]
    categoria = f"CADETES {genero_lbl.upper()}"
    fuente_url = f"{BASE_URL}/liga-federal/comparativa-equipos/{comp_cat_id}"
    detalle_url = LFF_U15_DETALLE_URL[args.genero]

    print(f"Categoría: U15 Cadetes ({genero_lbl})", file=sys.stderr)
    print(f"compCatId: {comp_cat_id}", file=sys.stderr)
    print(f"Torneo: {detalle_url}", file=sys.stderr)
    print(f"Descargando comparativa: {fuente_url}", file=sys.stderr)

    session = requests.Session()
    html = fetch_comparativa_html(comp_cat_id, session=session)
    rows = parse_comparativa_lanzamiento(html)
    print(f"Equipos: {len(rows)}", file=sys.stderr)

    out = args.output or str(
        ROOT / "outputs" / "lff" / f"lanzamiento_equipos_cadetes_{genero_lbl}_{args.temporada.strip()}.csv"
    )
    escribir_csv(
        Path(out),
        rows,
        comp_cat_id=comp_cat_id,
        categoria=categoria,
        temporada=args.temporada.strip(),
        fuente_url=fuente_url,
    )
    print(f"Guardado: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
