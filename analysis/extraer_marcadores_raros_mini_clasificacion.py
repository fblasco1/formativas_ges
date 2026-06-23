# -*- coding: utf-8 -*-
"""
Extrae partidos con resultado de MINI MASCULINO / TORNEO DE CLASIFICACION (GES 2015).

Para marcadores 0-0, 20-0 y 0-20 consulta el boxscore en argentina.basketball y agrega:
  - PTS_BOX_LOCAL / PTS_BOX_VISITANTE (fila Totales del acta)
  - conteo de jugadores con >= 10:00 min (regla: al menos 12 por equipo)
  - análisis de ganador, fixture en contra y casos especiales

Ejemplo:
  python analysis/extraer_marcadores_raros_mini_clasificacion.py
  python analysis/extraer_marcadores_raros_mini_clasificacion.py --solo-raros
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.febamba.mini_masc_regla_plantilla import (
    MIN_JUGADORES_REGLA,
    analizar_partido,
    observaciones_regla,
)
from ingest.argbasket.partido import parse_boxscore_html
from ingest.ges.extractor import GesDeportivaExtractor
from ingest.http_client import HttpClient, SessionProvider

ID_COMPETENCIA = 2015
ID_CATEGORIA_MINI_MASC = 5079
NOMBRE_FASE = "TORNEO DE CLASIFICACION"
FECHA_INI = "2025-1-1"
FECHA_FIN = "2026-12-31"

HEADER_BASE = (
    "Fecha",
    "Local",
    "Visitante",
    "PTS_LOCAL",
    "PTS_VISITANTE",
    "DIF_PTS",
    "ID_PARTIDO",
    "URL_Estadisticas",
)

HEADER_RAROS_EXTRA = (
    "PTS_BOX_LOCAL",
    "PTS_BOX_VISITANTE",
    "JUG_REG_LOCAL",
    "JUG_REG_VISITANTE",
    "CUMPLE_LOCAL",
    "CUMPLE_VISITANTE",
    "GANADOR_BOX",
    "NP_LOCAL",
    "NP_VISITANTE",
    "ESPECIAL",
    "OTRO",
    "FLAGS",
    "DIF_BOX",
    "OBSERVACIONES",
)


def _empty_enriched(extra_obs: str = "") -> Dict[str, str]:
    return {
        "PTS_BOX_LOCAL": "",
        "PTS_BOX_VISITANTE": "",
        "JUG_REG_LOCAL": "",
        "JUG_REG_VISITANTE": "",
        "CUMPLE_LOCAL": "",
        "CUMPLE_VISITANTE": "",
        "GANADOR_BOX": "",
        "NP_LOCAL": "",
        "NP_VISITANTE": "",
        "ESPECIAL": "",
        "OTRO": "",
        "FLAGS": "",
        "DIF_BOX": "",
        "OBSERVACIONES": extra_obs,
    }


def _load_widget_key() -> str:
    cfg_path = ROOT / "config" / "competencias.json"
    with cfg_path.open(encoding="utf-8") as f:
        return json.load(f).get("widget_key", "")


def _to_int(value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    return None


def _marcador_raro(pl: Optional[int], pv: Optional[int]) -> bool:
    return (pl == 0 and pv == 0) or (pl == 20 and pv == 0) or (pl == 0 and pv == 20)


def _resolve_fase_id(ges: GesDeportivaExtractor) -> int:
    fases, _ = ges.get_ids_fases_grupos(ID_COMPETENCIA, id_categoria=ID_CATEGORIA_MINI_MASC)
    for nombre, fid in fases.items():
        if nombre.strip().upper() == NOMBRE_FASE.upper():
            return int(fid)
    raise RuntimeError(f"No se encontró la fase {NOMBRE_FASE!r}. Fases: {list(fases)}")


def _boxscore_url(token: str) -> str:
    return (
        "https://argentina.basketball/liga-federal/partido/estadisticas/"
        f"{token.strip()}==?key="
    )


def _team_totales_pts(html: str) -> List[Optional[int]]:
    """Puntos por equipo desde la fila Totales de cada tabla de boxscore."""
    soup = BeautifulSoup(html, "html.parser")
    out: List[Optional[int]] = []
    for tbl in soup.find_all("table"):
        ttext = (tbl.get_text(" ", strip=True) or "").upper()
        if "PTOS" not in ttext or "MIN" not in ttext:
            continue
        tbody = tbl.find("tbody") or tbl
        pts_equipo: Optional[int] = None
        for tr in tbody.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if not cells:
                continue
            if cells[0].lower().startswith("total"):
                pts_equipo = _to_int(cells[2] if len(cells) > 2 else "")
                break
        if pts_equipo is not None:
            out.append(pts_equipo)
    return out


def _fetch_boxscore_enriched(
    token: str,
    *,
    pl_fix: Optional[int] = None,
    pv_fix: Optional[int] = None,
) -> Dict[str, str]:
    url = _boxscore_url(token)
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/138.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,*/*",
            },
            timeout=45,
        )
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:
        return _empty_enriched(f"Error al descargar boxscore: {exc}")

    if len(html) < 8000:
        return _empty_enriched("Boxscore no disponible o acta vacía")

    parsed = parse_boxscore_html(html)
    equipos = parsed.get("equipos") or []
    totales = _team_totales_pts(html)

    pl_box = pv_box = None
    if len(totales) >= 2:
        pl_box, pv_box = totales[0], totales[1]
    elif len(equipos) >= 2:
        pl_box = sum(_to_int(j.get("pts")) or 0 for j in equipos[0].get("jugadores") or [])
        pv_box = sum(_to_int(j.get("pts")) or 0 for j in equipos[1].get("jugadores") or [])

    jug_local = (equipos[0].get("jugadores") or []) if equipos else []
    jug_visit = (equipos[1].get("jugadores") or []) if len(equipos) > 1 else []

    return _enriquecer_desde_boxscore(
        pl_fix=pl_fix,
        pv_fix=pv_fix,
        pl_box=pl_box,
        pv_box=pv_box,
        jug_local=jug_local,
        jug_visit=jug_visit,
    )


def _enriquecer_desde_boxscore(
    *,
    pl_fix: Optional[int] = None,
    pv_fix: Optional[int] = None,
    pl_box: Optional[int],
    pv_box: Optional[int],
    jug_local: List[Dict[str, object]],
    jug_visit: List[Dict[str, object]],
) -> Dict[str, str]:
    analisis = analizar_partido(
        pl_fix=pl_fix,
        pv_fix=pv_fix,
        pl_box=pl_box,
        pv_box=pv_box,
        jug_local=jug_local,
        jug_visit=jug_visit,
    )
    j_reg_local = analisis["JUG_REG_LOCAL"]
    j_reg_visit = analisis["JUG_REG_VISITANTE"]

    def _fmt_int(v: object) -> str:
        return "" if v is None else str(v)

    def _fmt_bool(v: object) -> str:
        return "1" if v else "0"

    return {
        "PTS_BOX_LOCAL": _fmt_int(pl_box),
        "PTS_BOX_VISITANTE": _fmt_int(pv_box),
        "JUG_REG_LOCAL": str(j_reg_local),
        "JUG_REG_VISITANTE": str(j_reg_visit),
        "CUMPLE_LOCAL": _fmt_bool(analisis["CUMPLE_LOCAL"]),
        "CUMPLE_VISITANTE": _fmt_bool(analisis["CUMPLE_VISITANTE"]),
        "GANADOR_BOX": str(analisis["GANADOR_BOX"]),
        "NP_LOCAL": _fmt_bool(analisis["NP_LOCAL"]),
        "NP_VISITANTE": _fmt_bool(analisis["NP_VISITANTE"]),
        "ESPECIAL": _fmt_bool(analisis["ESPECIAL"]),
        "OTRO": _fmt_bool(analisis["OTRO"]),
        "FLAGS": str(analisis["FLAGS"]),
        "DIF_BOX": _fmt_int(analisis["DIF_BOX"]),
        "OBSERVACIONES": observaciones_regla(int(j_reg_local), int(j_reg_visit)),
    }


def _partido_a_fila(p: Dict[str, str]) -> Dict[str, str]:
    token = (p.get("ID_PARTIDO") or "").strip()
    url = p.get("URL") or ""
    if not url and token:
        url = _boxscore_url(token)
    return {
        "Fecha": p.get("Fecha") or "",
        "Local": p.get("Local") or "",
        "Visitante": p.get("Visitante") or "",
        "PTS_LOCAL": p.get("PTS_LOCAL") or "",
        "PTS_VISITANTE": p.get("PTS_VISITANTE") or "",
        "DIF_PTS": p.get("DIF_PTS") or "",
        "ID_PARTIDO": token,
        "URL_Estadisticas": url,
    }


def _enriquecer_raros(
    raros: List[Dict[str, str]], *, workers: int, progress: bool
) -> List[Dict[str, str]]:
    out: List[Optional[Dict[str, str]]] = [None] * len(raros)

    def _task(idx: int, row: Dict[str, str]) -> Tuple[int, Dict[str, str]]:
        enriched = _fetch_boxscore_enriched(
            row["ID_PARTIDO"],
            pl_fix=_to_int(row.get("PTS_LOCAL")),
            pv_fix=_to_int(row.get("PTS_VISITANTE")),
        )
        merged = dict(row)
        merged.update(enriched)
        return idx, merged

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_task, i, r) for i, r in enumerate(raros)]
        done = 0
        for fut in as_completed(futures):
            idx, merged = fut.result()
            out[idx] = merged
            done += 1
            if progress and (done % 25 == 0 or done == len(raros)):
                print(f"  boxscores {done}/{len(raros)}", file=sys.stderr, flush=True)

    return [r for r in out if r is not None]


def main() -> int:
    p = argparse.ArgumentParser(
        description="Partidos MINI MASC / TORNEO DE CLASIFICACION con revisión de marcadores raros"
    )
    p.add_argument("--comp-id", type=int, default=ID_COMPETENCIA)
    p.add_argument("--widget-key", default="", help="Default: config/competencias.json")
    p.add_argument("--workers", type=int, default=8, help="Hilos para descargar boxscores")
    p.add_argument(
        "--out-todos",
        default=str(ROOT / "outputs" / "mini_masc_clasificacion_partidos.csv"),
    )
    p.add_argument(
        "--out-raros",
        default=str(ROOT / "outputs" / "mini_masc_clasificacion_marcadores_raros.csv"),
    )
    p.add_argument(
        "--solo-raros",
        action="store_true",
        help="Solo genera CSV de marcadores raros (no el listado completo)",
    )
    p.add_argument("--progress", action="store_true")
    args = p.parse_args()

    widget_key = args.widget_key or _load_widget_key()
    if not widget_key:
        print("Falta widget_key", file=sys.stderr)
        return 1

    ges = GesDeportivaExtractor(HttpClient(SessionProvider.get_session()))
    id_fase = _resolve_fase_id(ges)
    if args.progress:
        print(f"Fase {NOMBRE_FASE} -> id {id_fase}", file=sys.stderr)

    partidos = ges.get_info_partidos(
        ID_CATEGORIA_MINI_MASC,
        FECHA_INI,
        FECHA_FIN,
        key=widget_key,
        id_fase=id_fase,
        id_grupo=-1,
    )
    con_resultado = [p for p in partidos if p.get("Estado") == "COMPLETO"]
    filas_todos = [_partido_a_fila(p) for p in con_resultado]

    raros_base: List[Dict[str, str]] = []
    for fila in filas_todos:
        pl = _to_int(fila.get("PTS_LOCAL"))
        pv = _to_int(fila.get("PTS_VISITANTE"))
        if _marcador_raro(pl, pv):
            raros_base.append(dict(fila))

    if args.progress:
        print(
            f"Partidos con resultado: {len(filas_todos)} | Marcadores raros: {len(raros_base)}",
            file=sys.stderr,
        )

    if not args.solo_raros:
        out_todos = Path(args.out_todos)
        out_todos.parent.mkdir(parents=True, exist_ok=True)
        with out_todos.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(HEADER_BASE))
            w.writeheader()
            w.writerows(filas_todos)
        if args.progress:
            print(f"Escrito {out_todos} ({len(filas_todos)} filas)", file=sys.stderr)

    if args.progress:
        print("Descargando boxscores de marcadores raros...", file=sys.stderr)
    filas_raros = _enriquecer_raros(raros_base, workers=args.workers, progress=args.progress)

    out_raros = Path(args.out_raros)
    out_raros.parent.mkdir(parents=True, exist_ok=True)
    header_raros = list(HEADER_BASE) + list(HEADER_RAROS_EXTRA)
    with out_raros.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header_raros)
        w.writeheader()
        w.writerows(filas_raros)

    resumen = {
        "competencia": args.comp_id,
        "categoria": "MINI MASCULINO",
        "fase": NOMBRE_FASE,
        "id_fase": id_fase,
        "partidos_con_resultado": len(filas_todos),
        "marcadores_raros": len(filas_raros),
        "out_todos": None if args.solo_raros else str(out_todos),
        "out_raros": str(out_raros),
    }
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
