# -*- coding: utf-8 -*-
"""
Descarga fixture Liga Federal Cadetes (U15) desde GES.

Fuente principal: widget de partidos + calendario en competicion.aspx.
  competencia GES 1619, id_categoria 4643 (masc) / 4644 (fem)

Ejemplo (misma fase/grupo que la URL del usuario):
  python analysis/descargar_fixture_lff_ges.py --genero masc --fase 15707 --grupo 31205

Fixture completo (todas las fases/grupos):
  python analysis/descargar_fixture_lff_ges.py --genero masc
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

from ingest.argbasket.lff_constants import LFF_GES_COMPETENCIA_ID, LFF_GES_ID_CATEGORIA
from ingest.ges.extractor import GesDeportivaExtractor
from ingest.ges.lff_fixture import _widget_a_fila, fetch_lff_cadetes_fixture_ges
from ingest.http_client import HttpClient, SessionProvider


def _load_widget_key() -> str:
    cfg_path = ROOT / "config" / "competencias.json"
    with cfg_path.open(encoding="utf-8") as f:
        return json.load(f).get("widget_key", "")


def main() -> int:
    p = argparse.ArgumentParser(description="Fixture LFF Cadetes U15 desde GES (widget + competicion)")
    p.add_argument("--temporada", default="2025")
    p.add_argument("--genero", choices=("masc", "fem"), default="masc")
    p.add_argument("--comp-id", type=int, default=LFF_GES_COMPETENCIA_ID)
    p.add_argument("--fecha-ini", default="2025-01-01")
    p.add_argument("--fecha-fin", default="2026-05-10")
    p.add_argument("--fase", type=int, default=0, help="Si se indica, solo esa fase (ej. 15707)")
    p.add_argument("--grupo", type=int, default=0, help="Si se indica, solo ese grupo (ej. 31205)")
    p.add_argument("--widget-key", default="", help="Key del widget (default: config/competencias.json)")
    p.add_argument("--solo-widget", action="store_true", help="No usar calendario competicion.aspx")
    p.add_argument("--output", default="")
    args = p.parse_args()

    genero_lbl = "masculino" if args.genero == "masc" else "femenino"
    id_cat = LFF_GES_ID_CATEGORIA[args.genero]
    widget_key = args.widget_key or _load_widget_key()
    if not widget_key:
        print("Falta widget_key (config/competencias.json o --widget-key)", file=sys.stderr)
        return 1

    print(f"GES competencia: {args.comp_id}", file=sys.stderr)
    print(f"Categoría Cadetes ({genero_lbl}): id_categoria={id_cat}", file=sys.stderr)
    print(f"Rango fechas widget: {args.fecha_ini} .. {args.fecha_fin}", file=sys.stderr)

    if args.fase or args.grupo:
        ges = GesDeportivaExtractor(HttpClient(SessionProvider.get_session()))
        batch = ges.get_info_partidos(
            id_cat,
            args.fecha_ini,
            args.fecha_fin,
            key=widget_key,
            id_fase=args.fase or -1,
            id_grupo=args.grupo or -1,
        )
        rows = [
            _widget_a_fila(
                p,
                nombre_fase=str(args.fase or ""),
                nombre_grupo=str(args.grupo or ""),
                id_categoria=id_cat,
                id_competencia=args.comp_id,
            )
            for p in batch
        ]
        print(
            f"Widget fase={args.fase or -1} grupo={args.grupo or -1}: {len(rows)} partidos",
            file=sys.stderr,
        )
    else:
        rows = fetch_lff_cadetes_fixture_ges(
            args.genero,
            fecha_inicio=args.fecha_ini,
            fecha_fin=args.fecha_fin,
            widget_key=widget_key,
            id_competencia=args.comp_id,
            include_calendar=not args.solo_widget,
        )
        fuentes = {}
        for r in rows:
            fuentes[r.get("fuente", "?")] = fuentes.get(r.get("fuente", "?"), 0) + 1
        print(f"Partidos totales: {len(rows)} ({fuentes})", file=sys.stderr)

    fieldnames = [
        "id_partido_token",
        "id_competencia",
        "id_categoria",
        "id_fase",
        "id_grupo",
        "fase_ges",
        "grupo_ges",
        "fuente",
        "Local",
        "Visitante",
        "PTS_LOCAL",
        "PTS_VISITANTE",
        "DIF_PTS",
        "Fecha_Programada",
        "URL_Estadisticas",
    ]
    out = args.output or str(
        ROOT / "outputs" / "lff" / f"fixture_cadetes_ges_{genero_lbl}_{args.temporada.strip()}.csv"
    )
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with Path(out).open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print(f"Guardado: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
