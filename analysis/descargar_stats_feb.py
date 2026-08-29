# -*- coding: utf-8 -*-
"""
Descarga estadísticas de lanzamiento por equipo (medias por partido) desde feb.es.

Competición por defecto: Campeonato de España de Clubes Cadete Masculino (U16).
URL ejemplo:
  https://www.feb.es/competiciones/estadisticas/cespclubescadmasc/35/2025

Ejemplo:
  python analysis/descargar_stats_feb.py --competicion cespclubescadmasc --temporada 2025
  python analysis/descargar_stats_feb.py --fase PLAY-OFF
  python analysis/descargar_stats_feb.py --fase-id -44960
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/138.0.0.0 Safari/537.36",
}

COMPETICIONES: Dict[str, Dict[str, object]] = {
    "cespclubescadmasc": {"g": 35, "nombre": "C ESP CLUBES CAD MASC", "edad": "U16"},
    "cespclubescadfem": {"g": 36, "nombre": "C ESP CLUBES CAD FEM", "edad": "U16"},
    "cespclubesjrmasc": {"g": 21, "nombre": "C ESP CLUBES JR MASC", "edad": "U18"},
    "cespclubesjrfem": {"g": 22, "nombre": "C ESP CLUBES JR FEM", "edad": "U18"},
    "cespclubesinfmasc": {"g": 37, "nombre": "C ESP CLUBES INF MASC", "edad": "U14"},
    "cespclubesinffem": {"g": 38, "nombre": "C ESP CLUBES INF FEM", "edad": "U14"},
}

PHASE_TARGET = "_ctl0:MainContentPlaceHolderMaster:fasesGruposDropDownList"
YEAR_TARGET = "_ctl0:MainContentPlaceHolderMaster:temporadasDropDownList"


@dataclass
class StatEquipo:
    competicion: str
    temporada: str
    fase: str
    fase_id: str
    equipo: str
    partidos: int
    pts_total: int
    pts_pp: float
    t2_a: int
    t2_i: int
    t2_pct: float
    t3_a: int
    t3_i: int
    t3_pct: float
    tl_a: int
    tl_i: int
    tl_pct: float


def _pct(a: int, i: int) -> str:
    if i <= 0:
        return ""
    return f"{100.0 * a / i:.1f}"


def _pp(val: float, partidos: int) -> str:
    if partidos <= 0:
        return ""
    return f"{val:.2f}"


def _efg(fgm: int, tpm: int, fga: int) -> str:
    if fga <= 0:
        return ""
    return f"{100.0 * (fgm + 0.5 * tpm) / fga:.1f}"


def _ts(pts: int, fga: int, fta: int) -> str:
    denom = 2 * (fga + 0.44 * fta)
    if denom <= 0:
        return ""
    return f"{100.0 * pts / denom:.1f}"


def _num_es(texto: str) -> float:
    t = (texto or "").strip().replace("%", "").replace(".", "").replace(",", ".")
    return float(t) if t else 0.0


def _parse_shot(tot: str) -> Tuple[int, int]:
    tot = (tot or "").strip()
    if "/" not in tot:
        return 0, 0
    a, b = tot.split("/", 1)
    return int(a.strip()), int(b.strip())


def _hidden_fields(soup: BeautifulSoup) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for inp in soup.find_all("input"):
        name = inp.get("name")
        if name:
            out[name] = inp.get("value", "")
    for sel in soup.find_all("select"):
        name = sel.get("name")
        if not name:
            continue
        opt = sel.find("option", selected=True) or sel.find("option")
        out[name] = opt.get("value", "") if opt else ""
    return out


def _url(competicion: str, g: int, temporada: int) -> str:
    return f"https://www.feb.es/competiciones/estadisticas/{competicion}/{g}/{temporada}"


def _postback(session: requests.Session, url: str, soup: BeautifulSoup, target: str, value: str) -> BeautifulSoup:
    data = _hidden_fields(soup)
    data["__EVENTTARGET"] = target
    data["__EVENTARGUMENT"] = ""
    data[target] = value
    r = session.post(
        url,
        data=data,
        headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def listar_fases(session: requests.Session, url: str) -> List[Tuple[str, str]]:
    r = session.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    sel = soup.select_one(f'select[name="{PHASE_TARGET}"]')
    if not sel:
        return []
    return [(o.get("value", ""), o.get_text(strip=True)) for o in sel.find_all("option") if o.get("value")]


def parse_tabla(soup: BeautifulSoup, *, competicion: str, temporada: int, fase: str, fase_id: str) -> List[StatEquipo]:
    rows: List[StatEquipo] = []
    for tr in soup.select("table tbody tr"):
        team_td = tr.select_one("td.nombre.equipo")
        part_td = tr.select_one("td.partidos")
        if not team_td or not part_td:
            continue

        partidos = int(part_td.get_text(strip=True) or "0")
        if partidos <= 0:
            continue

        equipo = team_td.get_text(strip=True)
        pts_total = int(tr.select_one("td.puntos span.tot").get_text(strip=True))
        pts_pp = _num_es(tr.select_one("td.puntos span.med").get_text(strip=True))

        t2_a, t2_i = _parse_shot(tr.select_one("td.tiros.dos span.tot").get_text(strip=True))
        t2_pct = _num_es(tr.select_one("td.tiros.dos span.med").get_text(strip=True))
        t3_a, t3_i = _parse_shot(tr.select_one("td.tiros.tres span.tot").get_text(strip=True))
        t3_pct = _num_es(tr.select_one("td.tiros.tres span.med").get_text(strip=True))
        tl_a, tl_i = _parse_shot(tr.select_one("td.tiros.libres span.tot").get_text(strip=True))
        tl_pct = _num_es(tr.select_one("td.tiros.libres span.med").get_text(strip=True))

        rows.append(
            StatEquipo(
                competicion=competicion,
                temporada=f"{temporada}/{temporada + 1}",
                fase=fase,
                fase_id=fase_id,
                equipo=equipo,
                partidos=partidos,
                pts_total=pts_total,
                pts_pp=pts_pp,
                t2_a=t2_a,
                t2_i=t2_i,
                t2_pct=t2_pct,
                t3_a=t3_a,
                t3_i=t3_i,
                t3_pct=t3_pct,
                tl_a=tl_a,
                tl_i=tl_i,
                tl_pct=tl_pct,
            )
        )
    return rows


def descargar_fase(
    session: requests.Session,
    url: str,
    soup: BeautifulSoup,
    fase_id: str,
    fase_nombre: str,
    *,
    competicion: str,
    temporada: int,
    sleep_s: float,
) -> Tuple[BeautifulSoup, List[StatEquipo]]:
    if sleep_s:
        time.sleep(sleep_s)
    soup = _postback(session, url, soup, PHASE_TARGET, fase_id)
    rows = parse_tabla(soup, competicion=competicion, temporada=temporada, fase=fase_nombre, fase_id=fase_id)
    return soup, rows


def descargar(
    *,
    competicion: str,
    temporada: int,
    fase_filter: Optional[str],
    fase_id: Optional[str],
    sleep_s: float,
) -> List[StatEquipo]:
    meta = COMPETICIONES[competicion]
    g = int(meta["g"])
    url = _url(competicion, g, temporada)

    session = requests.Session()
    r = session.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    fases = listar_fases(session, url)
    if not fases:
        return parse_tabla(soup, competicion=competicion, temporada=temporada, fase="", fase_id="")

    seleccion: List[Tuple[str, str]] = []
    if fase_id:
        seleccion = [(fid, fn) for fid, fn in fases if fid == fase_id]
        if not seleccion:
            raise ValueError(f"fase-id {fase_id!r} no encontrada")
    elif fase_filter:
        key = fase_filter.strip().upper()
        if key in ("TODAS", "ALL", "*"):
            seleccion = fases
        else:
            seleccion = [(fid, fn) for fid, fn in fases if key in fn.upper() or fn.upper() == key]
            if not seleccion and key == "PLAY-OFF":
                seleccion = [(fid, fn) for fid, fn in fases if fn.upper() == "PLAY-OFF"]
        if not seleccion:
            raise ValueError(f"No hay fase que coincida con {fase_filter!r}")
    else:
        seleccion = fases

    out: List[StatEquipo] = []
    for fid, fn in seleccion:
        soup, rows = descargar_fase(
            session,
            url,
            soup,
            fid,
            fn,
            competicion=competicion,
            temporada=temporada,
            sleep_s=sleep_s,
        )
        out.extend(rows)

    return out


def escribir_csv(path: Path, rows: List[StatEquipo], *, edad: str) -> None:
    fieldnames = [
        "competicion",
        "edad",
        "temporada",
        "fase",
        "fase_id",
        "equipo",
        "partidos",
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
    csv_rows = []
    for r in rows:
        p = r.partidos
        fgm = r.t2_a + r.t3_a
        fga = r.t2_i + r.t3_i
        csv_rows.append(
            {
                "competicion": r.competicion,
                "edad": edad,
                "temporada": r.temporada,
                "fase": r.fase,
                "fase_id": r.fase_id,
                "equipo": r.equipo,
                "partidos": p,
                "pts_total": r.pts_total,
                "pts_pp": _pp(r.pts_pp, 1),
                "tl_total": r.tl_i,
                "tl_pp": _pp(r.tl_i / p, 1),
                "tl_aciertos": r.tl_a,
                "tl_aciertos_pp": _pp(r.tl_a / p, 1),
                "tl_pct": _pct(r.tl_a, r.tl_i) or f"{r.tl_pct:.1f}",
                "t2_total": r.t2_i,
                "t2_pp": _pp(r.t2_i / p, 1),
                "t2_aciertos": r.t2_a,
                "t2_aciertos_pp": _pp(r.t2_a / p, 1),
                "t2_pct": _pct(r.t2_a, r.t2_i) or f"{r.t2_pct:.1f}",
                "t3_total": r.t3_i,
                "t3_pp": _pp(r.t3_i / p, 1),
                "t3_aciertos": r.t3_a,
                "t3_aciertos_pp": _pp(r.t3_a / p, 1),
                "t3_pct": _pct(r.t3_a, r.t3_i) or f"{r.t3_pct:.1f}",
                "fg_pct": _pct(fgm, fga),
                "efg_pct": _efg(fgm, r.t3_a, fga),
                "ts_pct": _ts(r.pts_total, fga, r.tl_i),
            }
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(csv_rows)


def main() -> int:
    p = argparse.ArgumentParser(description="Estadísticas de lanzamiento por equipo — FEB España")
    p.add_argument("--competicion", default="cespclubescadmasc", choices=sorted(COMPETICIONES))
    p.add_argument("--temporada", type=int, default=2025)
    p.add_argument(
        "--fase",
        default="TODAS",
        help="Filtrar fase por nombre (PLAY-OFF, PRIMERA FASE A, TODAS, etc.)",
    )
    p.add_argument("--fase-id", default="", help="ID exacto de fase/grupo (ej. -44960 para PLAY-OFF agregado)")
    p.add_argument("--output", default="", help="CSV de salida")
    p.add_argument("--sleep", type=float, default=0.15)
    args = p.parse_args()

    meta = COMPETICIONES[args.competicion]
    print(
        f"Descargando {meta['nombre']} {args.temporada}/{args.temporada + 1} "
        f"(feb.es, {meta['edad']})",
        file=sys.stderr,
    )

    try:
        rows = descargar(
            competicion=args.competicion,
            temporada=args.temporada,
            fase_filter=None if args.fase_id else args.fase,
            fase_id=args.fase_id or None,
            sleep_s=args.sleep,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Filas exportadas: {len(rows)}", file=sys.stderr)

    slug = args.competicion
    fase_slug = (args.fase_id or args.fase).lower().replace(" ", "_").replace("/", "-")
    out = args.output or str(ROOT / "outputs" / "feb" / f"lanzamiento_{slug}_{args.temporada}_{fase_slug}.csv")
    escribir_csv(Path(out), rows, edad=str(meta["edad"]))
    print(f"Guardado: {out}")

    if rows:
        pts = [r.pts_pp for r in rows]
        t2 = [r.t2_i / r.partidos for r in rows if r.partidos]
        t3 = [r.t3_i / r.partidos for r in rows if r.partidos]
        tl = [r.tl_i / r.partidos for r in rows if r.partidos]
        print(
            f"\nPromedio equipos ({len(rows)} filas): "
            f"PTS {sum(pts)/len(pts):.1f} | 2PA {sum(t2)/len(t2):.1f} | "
            f"3PA {sum(t3)/len(t3):.1f} | TLA {sum(tl)/len(tl):.1f}",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
