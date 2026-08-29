# -*- coding: utf-8 -*-
"""
Descarga estadísticas de lanzamiento por equipo (promedio por partido) del
campeonato brasileño CBB en Genius Sports.

Por defecto: CBI U15 Masculino 2025 (competition_id=41761).
Fuente: https://cbb.web.geniussports.com/competitions/?WHurl=%2Fcompetition%2F41761%2Fschedule

Ejemplo:
  python analysis/descargar_stats_cbb_genius.py --competition-id 41761 --temporada 2025
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent

EMBED_BASE = "https://hosted.dcd.shared.geniussports.com/embednf/CBB/pt"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/138.0.0.0 Safari/537.36",
}

COMPETICIONES = {
    41761: {"nombre": "CBI U15 Masc", "edad": "U15"},
    41760: {"nombre": "CBI U15 Fem", "edad": "U15"},
}


@dataclass
class TiroAcum:
    partidos: int = 0
    pts: int = 0
    fga: int = 0
    fgm: int = 0
    t3a: int = 0
    t3m: int = 0
    fta: int = 0
    ftm: int = 0

    def add(self, *, pts: int, fga: int, fgm: int, t3a: int, t3m: int, fta: int, ftm: int) -> None:
        self.partidos += 1
        self.pts += pts
        self.fga += fga
        self.fgm += fgm
        self.t3a += t3a
        self.t3m += t3m
        self.fta += fta
        self.ftm += ftm


def _pct(a: int, i: int) -> str:
    if i <= 0:
        return ""
    return f"{100.0 * a / i:.1f}"


def _pp(total: int, partidos: int) -> str:
    if partidos <= 0:
        return ""
    return f"{total / partidos:.2f}"


def _efg(fgm: int, t3m: int, fga: int) -> str:
    if fga <= 0:
        return ""
    return f"{100.0 * (fgm + 0.5 * t3m) / fga:.1f}"


def _ts(pts: int, fga: int, fta: int) -> str:
    denom = 2 * (fga + 0.44 * fta)
    if denom <= 0:
        return ""
    return f"{100.0 * pts / denom:.1f}"


def _norm_equipo(nombre: str) -> str:
    t = unicodedata.normalize("NFKD", nombre or "")
    t = t.encode("ascii", "ignore").decode("ascii")
    return " ".join(t.upper().split())


def _fetch_html(path: str, session: requests.Session, timeout: int) -> str:
    r = session.get(f"{EMBED_BASE}{path}", headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    text = r.text.strip()
    if text.startswith("{"):
        return json.loads(text).get("html", "")
    return text


def _int_cell(text: str) -> int:
    t = (text or "").strip().replace(",", ".")
    if not t or t in ("-", "&nbsp;"):
        return 0
    try:
        return int(float(t))
    except ValueError:
        return 0


def _parse_fecha(text: str) -> Optional[date]:
    m = re.search(r"Date / Time:\s*(\d{2}/\d{2}/\d{4})", text or "")
    if not m:
        return None
    return datetime.strptime(m.group(1), "%d/%m/%Y").date()


def _parse_fecha_arg(text: str) -> date:
    return datetime.strptime(text.strip(), "%d/%m/%Y").date()


def listar_partidos(
    competition_id: int,
    session: requests.Session,
    timeout: int,
    *,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
) -> List[str]:
    html = _fetch_html(f"/competition/{competition_id}/schedule", session, timeout)
    soup = BeautifulSoup(html, "html.parser")
    ids: List[str] = []
    for div in soup.select("div.match-wrap.STATUS_COMPLETE"):
        m = re.search(r"extfix_(\d+)", div.get("id", ""))
        if not m:
            continue
        if fecha_desde or fecha_hasta:
            partido_fecha = _parse_fecha(div.get_text(" ", strip=True))
            if partido_fecha is None:
                continue
            if fecha_desde and partido_fecha < fecha_desde:
                continue
            if fecha_hasta and partido_fecha > fecha_hasta:
                continue
        ids.append(m.group(1))
    if not ids:
        # fallback: todos los enlaces a partido (sin filtro de fecha)
        if not fecha_desde and not fecha_hasta:
            ids = sorted(set(re.findall(r"/match/(\d+)/", html)))
    return ids


def _header_index(table: BeautifulSoup) -> Dict[str, int]:
    row = table.find("thead")
    if not row:
        return {}
    headers = row.find_all("th")
    out: Dict[str, int] = {}
    for i, th in enumerate(headers):
        key = th.get_text(strip=True)
        if key:
            out[key] = i
    return out


def _parse_team_name(table: BeautifulSoup) -> str:
    h4 = table.find_previous("h4")
    if h4:
        return h4.get_text(strip=True)
    link = table.find_previous("a", href=re.compile(r"/team/\d+"))
    if link:
        t = link.get_text(strip=True)
        if t:
            return t
        title = link.get("title")
        if title:
            return title.strip()
    return ""


def _parse_boxscore_table(table: BeautifulSoup) -> Optional[Dict[str, int]]:
    idx = _header_index(table)
    needed = ("AT", "PAEF", "LLT", "LLC", "3PTST", "3PTSC", "PTS")
    if not all(k in idx for k in needed):
        return None
    tfoot = table.find("tfoot")
    if not tfoot:
        return None
    cells = tfoot.find("tr").find_all("td")
    if not cells:
        return None

    def cell(key: str) -> int:
        i = idx[key]
        return _int_cell(cells[i].get_text()) if i < len(cells) else 0

    return {
        "pts": cell("PTS"),
        "fga": cell("AT"),
        "fgm": cell("PAEF"),
        "fta": cell("LLT"),
        "ftm": cell("LLC"),
        "t3a": cell("3PTST"),
        "t3m": cell("3PTSC"),
    }


def parse_boxscore(html: str) -> List[Tuple[str, Dict[str, int]]]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Tuple[str, Dict[str, int]]] = []

    tables = soup.select("table.tableClass")
    for i, table in enumerate(tables):
        stats = _parse_boxscore_table(table)
        if not stats:
            continue
        name = _parse_team_name(table)
        if not name:
            name = f"Equipo_{i+1}"
        out.append((name, stats))
    return out


def fetch_match_stats(
    competition_id: int,
    match_id: str,
    timeout: int,
    sleep_s: float,
) -> List[Tuple[str, Dict[str, int]]]:
    if sleep_s:
        time.sleep(sleep_s)
    session = requests.Session()
    html = _fetch_html(f"/competition/{competition_id}/match/{match_id}/boxscore", session, timeout)
    return parse_boxscore(html)


def agregar_equipos(
    competition_id: int,
    match_ids: List[str],
    *,
    timeout: int,
    workers: int,
    sleep_s: float,
) -> Dict[str, TiroAcum]:
    acum: Dict[str, TiroAcum] = {}
    canon: Dict[str, str] = {}
    errores = 0

    def work(mid: str) -> List[Tuple[str, Dict[str, int]]]:
        return fetch_match_stats(competition_id, mid, timeout, sleep_s)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = {ex.submit(work, mid): mid for mid in match_ids}
        for fut in as_completed(futs):
            try:
                rows = fut.result()
            except Exception:
                errores += 1
                continue
            for nombre, st in rows:
                key = _norm_equipo(nombre)
                if key not in canon:
                    canon[key] = nombre
                if key not in acum:
                    acum[key] = TiroAcum()
                acum[key].add(**st)

    if errores:
        print(f"Partidos con error: {errores}", file=sys.stderr)
    return {canon[k]: v for k, v in acum.items()}


def escribir_csv(
    path: Path,
    acum: Dict[str, TiroAcum],
    *,
    competition_id: int,
    nombre: str,
    edad: str,
    temporada: str,
) -> None:
    fieldnames = [
        "competicion",
        "competition_id",
        "edad",
        "temporada",
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
    rows = []
    for equipo, t in sorted(acum.items()):
        p = t.partidos
        t2a = t.fgm - t.t3m
        t2i = t.fga - t.t3a
        rows.append(
            {
                "competicion": nombre,
                "competition_id": competition_id,
                "edad": edad,
                "temporada": temporada,
                "equipo": equipo,
                "partidos": p,
                "pts_total": t.pts,
                "pts_pp": _pp(t.pts, p),
                "tl_total": t.fta,
                "tl_pp": _pp(t.fta, p),
                "tl_aciertos": t.ftm,
                "tl_aciertos_pp": _pp(t.ftm, p),
                "tl_pct": _pct(t.ftm, t.fta),
                "t2_total": t2i,
                "t2_pp": _pp(t2i, p),
                "t2_aciertos": t2a,
                "t2_aciertos_pp": _pp(t2a, p),
                "t2_pct": _pct(t2a, t2i),
                "t3_total": t.t3a,
                "t3_pp": _pp(t.t3a, p),
                "t3_aciertos": t.t3m,
                "t3_aciertos_pp": _pp(t.t3m, p),
                "t3_pct": _pct(t.t3m, t.t3a),
                "fg_pct": _pct(t.fgm, t.fga),
                "efg_pct": _efg(t.fgm, t.t3m, t.fga),
                "ts_pct": _ts(t.pts, t.fga, t.fta),
            }
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    p = argparse.ArgumentParser(description="Lanzamiento por equipo — CBB Brasil (Genius Sports)")
    p.add_argument("--competition-id", type=int, default=41761)
    p.add_argument("--temporada", default="2025")
    p.add_argument("--output", default="")
    p.add_argument("--timeout", type=int, default=45)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--sleep", type=float, default=0.05)
    p.add_argument(
        "--desde",
        default="16/11/2025",
        help="Fecha mínima del partido (DD/MM/YYYY). Vacío = sin límite inferior.",
    )
    p.add_argument(
        "--hasta",
        default="24/11/2025",
        help="Fecha máxima del partido (DD/MM/YYYY). Vacío = sin límite superior.",
    )
    args = p.parse_args()

    meta = COMPETICIONES.get(args.competition_id, {"nombre": f"Comp {args.competition_id}", "edad": ""})
    print(
        f"Descargando {meta['nombre']} {args.temporada} (Genius Sports, comp={args.competition_id})",
        file=sys.stderr,
    )

    fecha_desde = _parse_fecha_arg(args.desde) if args.desde.strip() else None
    fecha_hasta = _parse_fecha_arg(args.hasta) if args.hasta.strip() else None

    session = requests.Session()
    try:
        match_ids = listar_partidos(
            args.competition_id,
            session,
            args.timeout,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )
    except Exception as exc:
        print(f"Error leyendo calendario: {exc}", file=sys.stderr)
        return 1

    if fecha_desde or fecha_hasta:
        rango = f"{fecha_desde.strftime('%d/%m/%Y') if fecha_desde else '…'}"
        rango += f" – {fecha_hasta.strftime('%d/%m/%Y') if fecha_hasta else '…'}"
        print(f"Ventana de fechas: {rango}", file=sys.stderr)
    print(f"Partidos finalizados: {len(match_ids)}", file=sys.stderr)
    if not match_ids:
        return 1

    acum = agregar_equipos(
        args.competition_id,
        match_ids,
        timeout=args.timeout,
        workers=args.workers,
        sleep_s=args.sleep,
    )
    print(f"Equipos con estadísticas: {len(acum)}", file=sys.stderr)

    slug = meta["nombre"].lower().replace(" ", "_")
    out = args.output or str(
        ROOT / "outputs" / "cbb" / f"lanzamiento_{slug}_{args.temporada}.csv"
    )
    escribir_csv(
        Path(out),
        acum,
        competition_id=args.competition_id,
        nombre=meta["nombre"],
        edad=meta["edad"],
        temporada=args.temporada,
    )
    print(f"Guardado: {out}")

    if acum:
        n = len(acum)
        pts = sum(t.pts / t.partidos for t in acum.values()) / n
        t2 = sum((t.fga - t.t3a) / t.partidos for t in acum.values()) / n
        t3 = sum(t.t3a / t.partidos for t in acum.values()) / n
        tl = sum(t.fta / t.partidos for t in acum.values()) / n
        print(
            f"\nPromedio liga ({n} equipos): PTS {pts:.1f} | 2PA {t2:.1f} | "
            f"3PA {t3:.1f} | TLA {tl:.1f}",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
