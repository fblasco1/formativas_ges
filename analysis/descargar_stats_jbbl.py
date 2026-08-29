# -*- coding: utf-8 -*-
"""
Descarga estadísticas de lanzamiento por equipo (promedio por partido) de
NBBL/JBBL (Alemania) vía API pública de nbbl-basketball.de.

JBBL = U16 masculino/femenino (según competición; por defecto JBBL masculina).
NBBL = U19.

Ejemplo U16 masculino, temporada 2025/2026:
  python analysis/descargar_stats_jbbl.py --liga jbbl --temporada 2025
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

ROOT = Path(__file__).resolve().parent.parent

STATS_PAGE = "https://nbbl-basketball.de/nbbl/stats"
API_BASE = "https://api.bbl.scb.world/v2"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/138.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Origin": "https://nbbl-basketball.de",
    "Referer": "https://nbbl-basketball.de/",
}

ROUND_LABELS = {
    "ALL": "Temporada completa",
    "PRE_ROUND": "Vorrunde",
    "MAIN_ROUND": "Hauptrunde",
    "RELEGATION": "Abstiegsrunde",
    "PO_EIGHTH_FINALS": "Achtelfinale",
    "PO_QUARTER_FINALS": "Viertelfinale",
    "PO_SEMI_FINALS": "Halbfinale",
    "PO_TOP4_SEMI_FINAL": "Top-4 Halbfinale",
    "PO_TOP4_FINAL": "Top-4 Finale",
}


@dataclass
class StatEquipo:
    equipo: str
    team_id: int
    grupo: str
    partidos: int
    pts: int
    t2_a: int
    t2_i: int
    t3_a: int
    t3_i: int
    tl_a: int
    tl_i: int
    ronda: str


def _pct(a: int, i: int) -> str:
    if i <= 0:
        return ""
    return f"{100.0 * a / i:.1f}"


def _pp(total: float, partidos: int) -> str:
    if partidos <= 0:
        return ""
    return f"{total / partidos:.2f}"


def _efg(fgm: int, tpm: int, fga: int) -> str:
    if fga <= 0:
        return ""
    return f"{100.0 * (fgm + 0.5 * tpm) / fga:.1f}"


def _ts(pts: int, fga: int, fta: int) -> str:
    denom = 2 * (fga + 0.44 * fta)
    if denom <= 0:
        return ""
    return f"{100.0 * pts / denom:.1f}"


def fetch_api_keys(session: requests.Session) -> Dict[str, str]:
    r = session.get(STATS_PAGE, headers=HEADERS, timeout=30)
    if r.status_code not in (200, 404):
        r.raise_for_status()
    m = re.search(r"apiKeys:\{([^}]+)\}", r.text)
    if not m:
        raise RuntimeError("No se encontraron apiKeys en la página de estadísticas NBBL/JBBL")
    raw = "{" + m.group(1) + "}"
    # Nuxt embebe claves sin comillas en claves: NBBL:"...", JBBL:"..."
    pairs = re.findall(r"([A-Za-z]+):\"([^\"]+)\"", raw)
    if not pairs:
        raise RuntimeError("Formato apiKeys inesperado")
    return {k.lower(): v for k, v in pairs}


def api_get(session: requests.Session, path: str, api_key: str, timeout: int) -> object:
    h = {**HEADERS, "x-api-key": api_key}
    url = f"{API_BASE}{path}"
    r = session.get(url, headers=h, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _aggregate_stats(rows: List[dict]) -> Optional[dict]:
    if not rows:
        return None
    gp = sum(int(s.get("GP") or 0) for s in rows)
    if gp <= 0:
        return None
    out = {
        "GP": gp,
        "PTS": sum(int(s.get("PTS") or 0) for s in rows),
        "2PM": sum(int(s.get("2PM") or 0) for s in rows),
        "2PA": sum(int(s.get("2PA") or 0) for s in rows),
        "3PM": sum(int(s.get("3PM") or 0) for s in rows),
        "3PA": sum(int(s.get("3PA") or 0) for s in rows),
        "FTM": sum(int(s.get("FTM") or 0) for s in rows),
        "FTA": sum(int(s.get("FTA") or 0) for s in rows),
        "FGM": sum(int(s.get("FGM") or 0) for s in rows),
        "FGA": sum(int(s.get("FGA") or 0) for s in rows),
    }
    return out


def _row_from_api(team: dict, stats: dict, ronda: str) -> StatEquipo:
    gp = int(stats["GP"])
    return StatEquipo(
        equipo=team["name"],
        team_id=int(team["id"]),
        grupo=str(team.get("group") or ""),
        partidos=gp,
        pts=int(stats["PTS"]),
        t2_a=int(stats["2PM"]),
        t2_i=int(stats["2PA"]),
        t3_a=int(stats["3PM"]),
        t3_i=int(stats["3PA"]),
        tl_a=int(stats["FTM"]),
        tl_i=int(stats["FTA"]),
        ronda=ronda,
    )


def fetch_team_stat(
    session: requests.Session,
    team: dict,
    season: int,
    api_key: str,
    ronda: str,
    timeout: int,
) -> Optional[StatEquipo]:
    data = api_get(session, f"/teamStats/{team['id']}/{season}", api_key, timeout)
    team_stats = data.get("teamStats") or []
    if not team_stats:
        return None

    if ronda.upper() == "ALL":
        agg = _aggregate_stats(team_stats)
        if not agg:
            return None
        return _row_from_api(team, agg, "ALL")

    matches = [s for s in team_stats if s.get("round") == ronda]
    if not matches:
        return None
    # Si hay varias filas para la misma ronda, tomar la de más partidos.
    best = max(matches, key=lambda s: int(s.get("GP") or 0))
    return _row_from_api(team, best, ronda)


def descargar_equipos(
    *,
    liga: str,
    temporada: int,
    ronda: str,
    timeout: int,
    workers: int,
    sleep_s: float,
) -> List[StatEquipo]:
    session = requests.Session()
    keys = fetch_api_keys(session)
    liga = liga.lower()
    if liga not in keys:
        raise ValueError(f"Liga desconocida {liga!r}. Disponibles: {sorted(keys)}")
    api_key = keys[liga]

    teams_raw = api_get(session, f"/teams/{temporada}", api_key, timeout)
    if not isinstance(teams_raw, list):
        raise RuntimeError("Respuesta inesperada de /teams")

    resultados: List[StatEquipo] = []

    def work(team: dict) -> Optional[StatEquipo]:
        s = requests.Session()
        if sleep_s:
            time.sleep(sleep_s)
        return fetch_team_stat(s, team, temporada, api_key, ronda, timeout)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = {ex.submit(work, t): t for t in teams_raw}
        for fut in as_completed(futs):
            row = fut.result()
            if row:
                resultados.append(row)

    resultados.sort(key=lambda r: r.equipo)
    return resultados


def escribir_csv(path: Path, rows: List[StatEquipo], *, liga: str, temporada: int) -> None:
    fieldnames = [
        "liga",
        "temporada",
        "ronda",
        "equipo",
        "team_id",
        "grupo",
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
    out_rows = []
    for r in rows:
        p = r.partidos
        fgm = r.t2_a + r.t3_a
        fga = r.t2_i + r.t3_i
        out_rows.append(
            {
                "liga": liga.upper(),
                "temporada": f"{temporada}/{temporada + 1}",
                "ronda": r.ronda,
                "equipo": r.equipo,
                "team_id": r.team_id,
                "grupo": r.grupo,
                "partidos": p,
                "pts_total": r.pts,
                "pts_pp": _pp(r.pts, p),
                "tl_total": r.tl_i,
                "tl_pp": _pp(r.tl_i, p),
                "tl_aciertos": r.tl_a,
                "tl_aciertos_pp": _pp(r.tl_a, p),
                "tl_pct": _pct(r.tl_a, r.tl_i),
                "t2_total": r.t2_i,
                "t2_pp": _pp(r.t2_i, p),
                "t2_aciertos": r.t2_a,
                "t2_aciertos_pp": _pp(r.t2_a, p),
                "t2_pct": _pct(r.t2_a, r.t2_i),
                "t3_total": r.t3_i,
                "t3_pp": _pp(r.t3_i, p),
                "t3_aciertos": r.t3_a,
                "t3_aciertos_pp": _pp(r.t3_a, p),
                "t3_pct": _pct(r.t3_a, r.t3_i),
                "fg_pct": _pct(fgm, fga),
                "efg_pct": _efg(fgm, r.t3_a, fga),
                "ts_pct": _ts(r.pts, fga, r.tl_i),
            }
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)


def main() -> int:
    p = argparse.ArgumentParser(description="Estadísticas de lanzamiento por equipo — JBBL/NBBL Alemania")
    p.add_argument("--liga", choices=("jbbl", "nbbl"), default="jbbl", help="JBBL=U16, NBBL=U19")
    p.add_argument("--temporada", type=int, default=2025, help="Año inicio temporada (ej. 2025 = 2025/26)")
    p.add_argument(
        "--ronda",
        default="ALL",
        help="Fase: ALL (toda la temporada), MAIN_ROUND, PRE_ROUND, RELEGATION, etc.",
    )
    p.add_argument("--output", default="", help="CSV de salida")
    p.add_argument("--timeout", type=int, default=30)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--sleep", type=float, default=0.05)
    args = p.parse_args()

    ronda = args.ronda.upper()
    if ronda != "ALL" and ronda not in ROUND_LABELS:
        print(f"Ronda desconocida {ronda}. Opciones: ALL, {', '.join(k for k in ROUND_LABELS if k != 'ALL')}", file=sys.stderr)
        return 1

    lbl = ROUND_LABELS.get(ronda, ronda)
    print(f"Descargando {args.liga.upper()} temporada {args.temporada}/{args.temporada + 1}, ronda={lbl}", file=sys.stderr)

    try:
        rows = descargar_equipos(
            liga=args.liga,
            temporada=args.temporada,
            ronda=ronda,
            timeout=args.timeout,
            workers=args.workers,
            sleep_s=args.sleep,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Equipos con estadísticas: {len(rows)}", file=sys.stderr)

    if not args.output:
        out = ROOT / "outputs" / "jbbl" / f"lanzamiento_equipos_{args.liga}_{args.temporada}_{ronda.lower()}.csv"
    else:
        out = Path(args.output)

    escribir_csv(out, rows, liga=args.liga, temporada=args.temporada)
    print(f"Guardado: {out}")

    if rows:
        n = len(rows)
        pts_pp = sum(r.pts / r.partidos for r in rows if r.partidos) / n
        t2_pp = sum(r.t2_i / r.partidos for r in rows if r.partidos) / n
        t3_pp = sum(r.t3_i / r.partidos for r in rows if r.partidos) / n
        tl_pp = sum(r.tl_i / r.partidos for r in rows if r.partidos) / n
        gp_avg = sum(r.partidos for r in rows) / n
        print(
            f"\nPromedio liga ({n} equipos, ~{gp_avg:.1f} PJ/equipo): "
            f"PTS {pts_pp:.1f} | 2PA {t2_pp:.1f} | 3PA {t3_pp:.1f} | TLA {tl_pp:.1f}",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
