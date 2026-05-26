# -*- coding: utf-8 -*-
"""
Lista fases y grupos tal como aparecen en GES (sin scrapear partidos).
Útil para ajustar parsers de fase/ronda/nivel.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time

from bs4 import BeautifulSoup

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mapeos.loader import cargar_mapeo_categorias  # noqa: E402
from parsers.fases import parsear_fase  # noqa: E402
from parsers.grupos import parsear_grupo  # noqa: E402
from pipelines.scrape_temporadas import TORNEOS  # noqa: E402
from utils.requester import hacer_solicitud  # noqa: E402


def auditar_torneo(year: int) -> list[dict]:
    t = TORNEOS[year]
    url_base = t["url"]
    cat_map = cargar_mapeo_categorias()
    filas = []

    html = hacer_solicitud(url_base)
    if not html:
        return filas
    soup = BeautifulSoup(html, "html.parser")
    cat_sel = soup.find("select", {"name": "DDLCategorias"})
    if not cat_sel:
        return filas

    for opt in cat_sel.find_all("option"):
        cat_id = opt.get("value")
        cat_web = opt.text.strip()
        if not cat_id or cat_id == "0" or "Seleccionar" in cat_web:
            continue
        if cat_web.lower() == "mosquitos":
            continue
        cat_mapa = cat_map.get(cat_web, cat_web)

        url_cat = f"{url_base}&categoria={cat_id}"
        html_f = hacer_solicitud(url_cat)
        time.sleep(0.3)
        if not html_f:
            continue
        soup_f = BeautifulSoup(html_f, "html.parser")
        fase_sel = soup_f.find("select", {"name": "DDLFases"})
        if not fase_sel:
            continue

        for fopt in fase_sel.find_all("option"):
            fase_id = fopt.get("value")
            fase_text = fopt.text.strip()
            if not fase_id or fase_id == "0" or "Seleccionar" in fase_text:
                continue

            parsed_f = parsear_fase(year, fase_text)
            url_fase = f"{url_cat}&fase={fase_id}"
            html_g = hacer_solicitud(url_fase)
            time.sleep(0.3)
            grupos = []
            if html_g:
                soup_g = BeautifulSoup(html_g, "html.parser")
                gsel = soup_g.find("select", {"name": "DDLGrupos"})
                if gsel:
                    for gopt in gsel.find_all("option"):
                        gid = gopt.get("value")
                        gtext = gopt.text.strip()
                        if not gid or gid == "0" or "Seleccionar" in gtext:
                            continue
                        pg = parsear_grupo(year, fase_text, gtext)
                        grupos.append(
                            {
                                "grupo_ges": gtext,
                                "grupo_nivel": pg.get("nivel"),
                                "grupo_zona": pg.get("zona"),
                                "grupo_grupo": pg.get("grupo"),
                            }
                        )
                else:
                    grupos.append({"grupo_ges": "(sin DDLGrupos)", "grupo_nivel": "", "grupo_zona": "", "grupo_grupo": ""})

            if not grupos:
                grupos = [{"grupo_ges": "", "grupo_nivel": "", "grupo_zona": "", "grupo_grupo": ""}]

            for g in grupos:
                filas.append(
                    {
                        "anio": year,
                        "categoria_ges": cat_web,
                        "categoria": cat_mapa,
                        "fase_ges": fase_text,
                        "fase": parsed_f.get("fase"),
                        "ronda_fase": parsed_f.get("ronda"),
                        "nivel_fase": parsed_f.get("nivel"),
                        "zona_fase": parsed_f.get("zona"),
                        **g,
                    }
                )

    return filas


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("years", type=int, nargs="+")
    p.add_argument("--out", default="outputs/auditoria_estructura_ges.csv")
    args = p.parse_args()

    todas = []
    for y in args.years:
        print(f"Auditando {y}...", flush=True)
        todas.extend(auditar_torneo(y))

    out = args.out
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    if not todas:
        print("Sin filas")
        return 1
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(todas[0].keys()))
        w.writeheader()
        w.writerows(todas)
    print(f"Escrito {len(todas)} filas -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
