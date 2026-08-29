# -*- coding: utf-8 -*-
"""
Descarga estadísticas de lanzamiento por equipo (promedio por partido) de
la liga formativa U15 Pioniri (Serbia) vía Digital Score + KSS Live.

Calendario: https://new-api.dscore.live/leagues/{grupo}/public-schedule
Boxscore:   https://kss-live.com/live/{slug}.php  (slug desde link_stat del partido)

Grupos por defecto: 252-255 (fase de grupos) + 263 (Final 8).

Ejemplo:
  python analysis/descargar_stats_dscore_serbia.py
  python analysis/descargar_stats_dscore_serbia.py --grupos 252 263 --temporada 2025/26
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent

API_BASE = "https://new-api.dscore.live"
KSS_LIVE_BASE = "https://kss-live.com/live"
DEFAULT_GRUPOS = [252, 253, 254, 255, 263]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/138.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


@dataclass
class TiroAcum:
    partidos: int = 0
    pts: int = 0
    t2m: int = 0
    t2a: int = 0
    t3m: int = 0
    t3a: int = 0
    ftm: int = 0
    fta: int = 0

    def add(self, *, pts: int, t2m: int, t2a: int, t3m: int, t3a: int, ftm: int, fta: int) -> None:
        self.partidos += 1
        self.pts += pts
        self.t2m += t2m
        self.t2a += t2a
        self.t3m += t3m
        self.t3a += t3a
        self.ftm += ftm
        self.fta += fta


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


def _fmt_equipo(team: dict) -> str:
    prefix = (team.get("prefix") or "").strip()
    name = (team.get("name") or "").strip()
    if prefix and not name.upper().startswith(prefix.upper()):
        return f"{prefix} {name}".strip()
    return name


def _slug_from_link_stat(link: str) -> Optional[str]:
    if not link:
        return None
    q = parse_qs(urlparse(link).query)
    slug = (q.get("id") or [None])[0]
    return str(slug).strip() if slug else None


def _int(parts: List[str], idx: int) -> int:
    try:
        return int((parts[idx] if idx < len(parts) else "0") or "0")
    except ValueError:
        return 0


def _parse_player_line(raw: str) -> Optional[Dict[str, int]]:
    """Parsea una fila de jugador (d1, d2, … / g1, g2, …) del boxscore KSS Live."""
    if not raw:
        return None
    p = raw.split(";")
    if len(p) < 15:
        return None
    pts = _int(p, 3)
    if pts <= 0:
        return None

    t3m, t3a = _int(p, 10), _int(p, 11)
    if t3m > t3a:
        return None

    fta13, fta14 = _int(p, 13), _int(p, 14)
    options: List[Dict[str, int]] = []

    for t2m, t2a in ((_int(p, 4), _int(p, 5)), (_int(p, 7), _int(p, 8))):
        if t2m > t2a:
            continue
        ftm = pts - 2 * t2m - 3 * t3m
        if ftm < 0:
            continue
        if ftm <= fta13:
            fta = fta13
        elif ftm <= fta14:
            fta = fta14
        else:
            continue
        if 2 * t2m + 3 * t3m + ftm != pts:
            continue
        options.append(
            {
                "pts": pts,
                "t2m": t2m,
                "t2a": t2a,
                "t3m": t3m,
                "t3a": t3a,
                "ftm": ftm,
                "fta": fta,
            }
        )

    if not options:
        return None
    # Si ambos bloques de 2P cuadran, preferir el que no infla tiros libres.
    return min(options, key=lambda x: x["ftm"])


def _parse_team_from_players(html: str, prefix: str) -> Optional[Dict[str, int]]:
    totals = {"pts": 0, "t2m": 0, "t2a": 0, "t3m": 0, "t3a": 0, "ftm": 0, "fta": 0}
    found = False
    for m in re.finditer(rf"<DIV id={prefix}\d+>(.*?)</DIV>", html, re.I | re.S):
        st = _parse_player_line(m.group(1))
        if not st:
            continue
        found = True
        for k in totals:
            totals[k] += st[k]
    return totals if found else None


def _get_div(html: str, div_id: str) -> str:
    m = re.search(rf"<DIV id={div_id}>(.*?)</DIV>", html, re.I | re.S)
    return m.group(1) if m else ""


def fetch_boxscore(slug: str, timeout: int) -> Optional[Tuple[Dict[str, int], Dict[str, int]]]:
    url = f"{KSS_LIVE_BASE}/{slug}.php"
    r = requests.get(url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=timeout)
    if r.status_code != 200:
        return None
    home = _parse_team_from_players(r.text, "d")
    away = _parse_team_from_players(r.text, "g")
    if not home or not away:
        return None
    return home, away


def fetch_schedule(grupo_id: int, timeout: int) -> dict:
    url = f"{API_BASE}/leagues/{grupo_id}/public-schedule"
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def listar_partidos(grupos: List[int], timeout: int) -> List[dict]:
    partidos: List[dict] = []
    visto: set[int] = set()

    for gid in grupos:
        data = fetch_schedule(gid, timeout)
        league = data.get("league") or {}
        for c in data.get("contests") or []:
            cid = c.get("id")
            if not cid or cid in visto:
                continue
            visto.add(cid)
            slug = _slug_from_link_stat(c.get("link_stat") or "")
            if not slug:
                continue
            score = c.get("score") or {}
            if not score:
                continue
            partidos.append(
                {
                    "contest_id": cid,
                    "grupo_id": gid,
                    "grupo": league.get("name", str(gid)),
                    "slug": slug,
                    "home": _fmt_equipo(c.get("first_team") or {}),
                    "away": _fmt_equipo(c.get("second_team") or {}),
                }
            )
    return partidos


def agregar_equipos(
    partidos: List[dict],
    *,
    timeout: int,
    workers: int,
    sleep_s: float,
) -> Tuple[Dict[str, TiroAcum], int]:
    acum: Dict[str, TiroAcum] = {}
    canon: Dict[str, str] = {}
    errores = 0

    def work(p: dict) -> Optional[Tuple[str, str, Dict[str, int]]]:
        if sleep_s:
            time.sleep(sleep_s)
        box = fetch_boxscore(p["slug"], timeout)
        if not box:
            return None
        home, away = box
        return p["home"], p["away"], home, away

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = {ex.submit(work, p): p for p in partidos}
        for fut in as_completed(futs):
            p = futs[fut]
            try:
                result = fut.result()
            except Exception:
                errores += 1
                continue
            if not result:
                errores += 1
                continue
            home_name, away_name, home_stats, away_stats = result
            for nombre, st in ((home_name, home_stats), (away_name, away_stats)):
                key = _norm_equipo(nombre)
                if key not in canon:
                    canon[key] = nombre
                if key not in acum:
                    acum[key] = TiroAcum()
                acum[key].add(**st)

    return {canon[k]: v for k, v in acum.items()}, errores


def escribir_csv(
    path: Path,
    acum: Dict[str, TiroAcum],
    *,
    nombre: str,
    edad: str,
    temporada: str,
    grupos: List[int],
) -> None:
    fieldnames = [
        "competicion",
        "edad",
        "temporada",
        "grupos",
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
        fgm = t.t2m + t.t3m
        fga = t.t2a + t.t3a
        rows.append(
            {
                "competicion": nombre,
                "edad": edad,
                "temporada": temporada,
                "grupos": ",".join(str(g) for g in grupos),
                "equipo": equipo,
                "partidos": p,
                "pts_total": t.pts,
                "pts_pp": _pp(t.pts, p),
                "tl_total": t.fta,
                "tl_pp": _pp(t.fta, p),
                "tl_aciertos": t.ftm,
                "tl_aciertos_pp": _pp(t.ftm, p),
                "tl_pct": _pct(t.ftm, t.fta),
                "t2_total": t.t2a,
                "t2_pp": _pp(t.t2a, p),
                "t2_aciertos": t.t2m,
                "t2_aciertos_pp": _pp(t.t2m, p),
                "t2_pct": _pct(t.t2m, t.t2a),
                "t3_total": t.t3a,
                "t3_pp": _pp(t.t3a, p),
                "t3_aciertos": t.t3m,
                "t3_aciertos_pp": _pp(t.t3m, p),
                "t3_pct": _pct(t.t3m, t.t3a),
                "fg_pct": _pct(fgm, fga),
                "efg_pct": _efg(fgm, t.t3m, fga),
                "ts_pct": _ts(t.pts, fga, t.fta),
            }
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    p = argparse.ArgumentParser(description="Lanzamiento por equipo — Serbia U15 Pioniri (dscore.live)")
    p.add_argument("--grupos", type=int, nargs="+", default=DEFAULT_GRUPOS)
    p.add_argument("--temporada", default="2025/26")
    p.add_argument("--output", default="")
    p.add_argument("--timeout", type=int, default=45)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--sleep", type=float, default=0.05)
    args = p.parse_args()

    print(
        f"Descargando PF U15 Pioniri {args.temporada} (grupos {args.grupos})",
        file=sys.stderr,
    )

    try:
        partidos = listar_partidos(args.grupos, args.timeout)
    except Exception as exc:
        print(f"Error leyendo calendarios: {exc}", file=sys.stderr)
        return 1

    print(f"Partidos con estadísticas: {len(partidos)}", file=sys.stderr)
    if not partidos:
        return 1

    acum, errores = agregar_equipos(
        partidos,
        timeout=args.timeout,
        workers=args.workers,
        sleep_s=args.sleep,
    )
    if errores:
        print(f"Partidos con error: {errores}", file=sys.stderr)

    print(f"Equipos con estadísticas: {len(acum)}", file=sys.stderr)
    if not acum:
        return 1

    out = args.output or str(ROOT / "outputs" / "serbia" / "lanzamiento_u15_pioniri_2025.csv")
    escribir_csv(
        Path(out),
        acum,
        nombre="PF U15 Pioniri",
        edad="U15",
        temporada=args.temporada,
        grupos=args.grupos,
    )
    print(f"Guardado: {out}")

    n = len(acum)
    pts = sum(t.pts / t.partidos for t in acum.values()) / n
    t2 = sum(t.t2a / t.partidos for t in acum.values()) / n
    t3 = sum(t.t3a / t.partidos for t in acum.values()) / n
    tl = sum(t.fta / t.partidos for t in acum.values()) / n
    print(
        f"\nPromedio liga ({n} equipos, {len(partidos)} partidos): "
        f"PTS {pts:.1f} | 2PA {t2:.1f} | 3PA {t3:.1f} | TLA {tl:.1f}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
