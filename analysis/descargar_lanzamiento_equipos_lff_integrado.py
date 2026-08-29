# -*- coding: utf-8 -*-
"""
Lanzamiento por equipo — Cadetes U15 integrando GES + argentina.basketball.

Flujo ideal:
  1. Fixture GES (competicion 1619, id_categoria 4643) → partidos por equipo.
  2. Widget GES con id_partido → boxscores → agregación partido a partido.
  3. Si el widget no devuelve IDs (situación actual), usa Comparativa de Equipos
     en argentina.basketball como fuente de lanzamiento PP.

Ejemplo:
  python analysis/descargar_lanzamiento_equipos_lff_integrado.py --genero masc
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_lff_mod_path = ROOT / "analysis" / "descargar_lanzamiento_equipos_lff.py"
_spec = importlib.util.spec_from_file_location("descargar_lanzamiento_equipos_lff", _lff_mod_path)
_lff_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_lff_mod)
fetch_comparativa_html = _lff_mod.fetch_comparativa_html
parse_comparativa_lanzamiento = _lff_mod.parse_comparativa_lanzamiento
escribir_comparativa_csv = _lff_mod.escribir_csv
from ingest.argbasket.lff_constants import (
    BASE_URL,
    LFF_GES_COMPETENCIA_ID,
    LFF_GES_ID_CATEGORIA,
    LFF_U15_TORNEO_COMP_CAT_ID,
)
from ingest.ges.extractor import GesDeportivaExtractor
from ingest.ges.lff_fixture import fetch_lff_cadetes_fixture_ges
from ingest.ges.partido_ids import es_id_sintetico
from ingest.http_client import HttpClient, SessionProvider


@dataclass
class TiroAcum:
    partidos: int = 0
    t2_a: int = 0
    t2_i: int = 0
    t3_a: int = 0
    t3_i: int = 0
    tl_a: int = 0
    tl_i: int = 0

    def add(self, t2a: int, t2i: int, t3a: int, t3i: int, tla: int, tli: int) -> None:
        self.partidos += 1
        self.t2_a += t2a
        self.t2_i += t2i
        self.t3_a += t3a
        self.t3_i += t3i
        self.tl_a += tla
        self.tl_i += tli


def _load_widget_key() -> str:
    with (ROOT / "config" / "competencias.json").open(encoding="utf-8") as f:
        return json.load(f).get("widget_key", "")


def _normalizar_equipo(nombre: str) -> str:
    t = (nombre or "").upper().strip()
    for o, n in [("Ó", "O"), ("Í", "I"), ("Á", "A"), ("É", "E"), ("Ú", "U"), ("Ñ", "N")]:
        t = t.replace(o, n)
    t = re.sub(r"\s+", " ", t)
    return t


def _pct(a: int, i: int) -> str:
    if i <= 0:
        return ""
    return f"{round(100.0 * a / i, 1)}"


def _pp(total: int, partidos: int) -> str:
    if partidos <= 0:
        return ""
    return f"{round(total / partidos, 1)}".replace(".", ",")


def _contar_partidos_fixture(fixture: List[Dict[str, str]]) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for row in fixture:
        for col in ("Local", "Visitante"):
            eq = (row.get(col) or "").strip()
            if eq:
                counts[_normalizar_equipo(eq)] += 1
    return dict(counts)


def _sumar_tiros_jugadores(jugadores: List[Dict]) -> Tuple[int, int, int, int, int, int]:
    t2a = t2i = t3a = t3i = tla = tli = 0
    for j in jugadores:
        for key, a_var, i_var in (("t2", "t2a", "t2i"), ("t3", "t3a", "t3i"), ("tl", "tla", "tli")):
            blk = j.get(key) or {}
            if isinstance(blk, dict):
                a = int(blk.get("a") or 0)
                i = int(blk.get("i") or 0)
                if key == "t2":
                    t2a += a
                    t2i += i
                elif key == "t3":
                    t3a += a
                    t3i += i
                else:
                    tla += a
                    tli += i
    return t2a, t2i, t3a, t3i, tla, tli


def _agregar_desde_boxscores(
    fixture: List[Dict[str, str]],
    *,
    widget_key: str,
) -> Tuple[Dict[str, TiroAcum], int]:
    ges = GesDeportivaExtractor(HttpClient(SessionProvider.get_session()))
    acum: Dict[str, TiroAcum] = defaultdict(TiroAcum)
    procesados = 0
    for row in fixture:
        pid = (row.get("id_partido_token") or "").strip()
        if not pid or es_id_sintetico(pid):
            continue
        try:
            parsed = ges.get_boxscore(pid, widget_key=widget_key)
        except Exception:
            continue
        if not parsed:
            continue
        for eq in parsed.get("equipos") or []:
            nombre = (eq.get("nombre") or "").strip()
            if not nombre:
                continue
            stats = _sumar_tiros_jugadores(eq.get("jugadores") or [])
            acum[_normalizar_equipo(nombre)].add(*stats)
        procesados += 1
    return dict(acum), procesados


def _acum_a_filas(acum: Dict[str, TiroAcum]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for equipo_norm, t in sorted(acum.items(), key=lambda x: x[0]):
        p = t.partidos
        rows.append(
            {
                "equipo": equipo_norm,
                "partidos": str(p),
                "tl_total": str(t.tl_i),
                "tl_pp": _pp(t.tl_i, p),
                "tl_aciertos": str(t.tl_a),
                "tl_aciertos_pp": _pp(t.tl_a, p),
                "tl_pct": _pct(t.tl_a, t.tl_i),
                "t2_total": str(t.t2_i),
                "t2_pp": _pp(t.t2_i, p),
                "t2_aciertos": str(t.t2_a),
                "t2_aciertos_pp": _pp(t.t2_a, p),
                "t2_pct": _pct(t.t2_a, t.t2_i),
                "t3_total": str(t.t3_i),
                "t3_pp": _pp(t.t3_i, p),
                "t3_aciertos": str(t.t3_a),
                "t3_aciertos_pp": _pp(t.t3_a, p),
                "t3_pct": _pct(t.t3_a, t.t3_i),
            }
        )
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description="Lanzamiento Cadetes — GES fixture + comparativa/boxscore")
    p.add_argument("--temporada", default="2025")
    p.add_argument("--genero", choices=("masc", "fem"), default="masc")
    p.add_argument("--fecha-ini", default="2025-01-01")
    p.add_argument("--fecha-fin", default="2026-05-10")
    p.add_argument("--widget-key", default="")
    p.add_argument("--output", default="")
    p.add_argument("--solo-comparativa", action="store_true", help="Omitir intento de boxscore GES")
    args = p.parse_args()

    genero_lbl = "masculino" if args.genero == "masc" else "femenino"
    comp_cat_id = LFF_U15_TORNEO_COMP_CAT_ID[args.genero]
    id_categoria = LFF_GES_ID_CATEGORIA[args.genero]
    widget_key = args.widget_key or _load_widget_key()

    print(f"Cadetes {genero_lbl} — competencia GES {LFF_GES_COMPETENCIA_ID}, cat {id_categoria}", file=sys.stderr)

    fixture = fetch_lff_cadetes_fixture_ges(
        args.genero,
        fecha_inicio=args.fecha_ini,
        fecha_fin=args.fecha_fin,
        widget_key=widget_key,
        id_competencia=LFF_GES_COMPETENCIA_ID,
    )
    partidos_fixture = _contar_partidos_fixture(fixture)
    print(f"Fixture GES: {len(fixture)} partidos, {len(partidos_fixture)} equipos", file=sys.stderr)

    fuente = "comparativa"
    lanz_rows: List[Dict[str, str]] = []

    if not args.solo_comparativa:
        acum, n_box = _agregar_desde_boxscores(fixture, widget_key=widget_key)
        print(f"Boxscores GES procesados: {n_box}", file=sys.stderr)
        if acum:
            fuente = "boxscore_ges"
            lanz_rows = _acum_a_filas(acum)

    if not lanz_rows:
        html = fetch_comparativa_html(comp_cat_id)
        lanz_rows = parse_comparativa_lanzamiento(html)
        print(f"Comparativa argentina.basketball: {len(lanz_rows)} equipos", file=sys.stderr)

    out_integrado = args.output or str(
        ROOT / "outputs" / "lff" / f"lanzamiento_cadetes_integrado_{genero_lbl}_{args.temporada.strip()}.csv"
    )
    fieldnames = [
        "fuente_lanzamiento",
        "id_competencia_ges",
        "id_categoria_ges",
        "comp_cat_id",
        "temporada",
        "equipo",
        "partidos_comparativa",
        "partidos_fixture_ges",
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
    Path(out_integrado).parent.mkdir(parents=True, exist_ok=True)
    with Path(out_integrado).open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in lanz_rows:
            eq_norm = _normalizar_equipo(row["equipo"])
            w.writerow(
                {
                    "fuente_lanzamiento": fuente,
                    "id_competencia_ges": LFF_GES_COMPETENCIA_ID,
                    "id_categoria_ges": id_categoria,
                    "comp_cat_id": comp_cat_id,
                    "temporada": args.temporada.strip(),
                    "equipo": row["equipo"],
                    "partidos_comparativa": row.get("partidos", ""),
                    "partidos_fixture_ges": partidos_fixture.get(eq_norm, ""),
                    **{k: row.get(k, "") for k in fieldnames if k.startswith(("tl_", "t2_", "t3_"))},
                }
            )

    out_comp = ROOT / "outputs" / "lff" / f"lanzamiento_equipos_cadetes_{genero_lbl}_{args.temporada.strip()}.csv"
    escribir_comparativa_csv(
        out_comp,
        lanz_rows,
        comp_cat_id=comp_cat_id,
        categoria=f"CADETES {genero_lbl.upper()}",
        temporada=args.temporada.strip(),
        fuente_url=f"{BASE_URL}/liga-federal/comparativa-equipos/{comp_cat_id}",
    )

    print(f"Fuente lanzamiento: {fuente}", file=sys.stderr)
    print(f"Guardado integrado: {out_integrado}")
    print(f"Guardado comparativa: {out_comp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
