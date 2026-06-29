# -*- coding: utf-8 -*-
"""
Analiza el play-by-play (en-vivo) de los partidos MINI MASCULINO / TORNEO DE
CLASIFICACION para detectar:

  - Sustituciones DURANTE el 3er cuarto (reloj < 10:00).
  - Jugadores que estuvieron en cancha en cuartos consecutivos.

Lee la lista de partidos de outputs/mini_masc_clasificacion_partidos.csv
(generada por extraer_marcadores_raros_mini_clasificacion.py) y consulta el
PBP en argentina.basketball para cada uno.

Salidas:
  - outputs/mini_masc/pbp_analisis.json  (detalle por partido, para el informe)
  - outputs/mini_masc/pbp_resumen.csv    (una fila por partido)

Ejemplo:
  python analysis/analizar_pbp_mini.py --progress
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.argbasket.pbp_reglas import fetch_y_analizar

CSV_PARTIDOS = ROOT / "outputs" / "mini_masc_clasificacion_partidos.csv"
OUT_JSON = ROOT / "outputs" / "mini_masc" / "pbp_analisis.json"
OUT_CSV = ROOT / "outputs" / "mini_masc" / "pbp_resumen.csv"

CSV_HEADER = (
    "Fecha",
    "Local",
    "Visitante",
    "PTS_LOCAL",
    "PTS_VISITANTE",
    "ID_PARTIDO",
    "TIENE_PBP",
    "HUBO_SUBS_Q3",
    "SUBS_Q3_ENTRA",
    "SUBS_Q3_SALE",
    "HUBO_CONSECUTIVOS",
    "N_CONSECUTIVOS",
    "DETALLE_SUBS_Q3",
    "DETALLE_CONSECUTIVOS",
)


def _leer_partidos() -> List[Dict[str, str]]:
    with CSV_PARTIDOS.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _fmt_subs(subs: List[Dict[str, object]]) -> str:
    partes = []
    for s in subs:
        eq = "A" if s.get("equipo") == "local" else ("B" if s.get("equipo") == "visitante" else "?")
        partes.append(f"{eq} {s.get('accion')} #{s.get('dorsal')} {s.get('nombre') or ''} ({s.get('clock')})")
    return " | ".join(partes)


def _fmt_consec(jug: List[Dict[str, object]]) -> str:
    partes = []
    for c in jug:
        eq = "A" if c.get("equipo") == "local" else ("B" if c.get("equipo") == "visitante" else "?")
        pares = ",".join(f"{a}-{b}" for a, b in c.get("pares", []))
        partes.append(f"{eq} #{c.get('dorsal')} {c.get('nombre') or ''} [{pares}]")
    return " | ".join(partes)


def _analizar_uno(
    row: Dict[str, str], session: requests.Session
) -> Dict[str, object]:
    token = (row.get("ID_PARTIDO") or "").strip()
    base = {
        "Fecha": row.get("Fecha") or "",
        "Local": row.get("Local") or "",
        "Visitante": row.get("Visitante") or "",
        "PTS_LOCAL": row.get("PTS_LOCAL") or "",
        "PTS_VISITANTE": row.get("PTS_VISITANTE") or "",
        "ID_PARTIDO": token,
    }
    if not token:
        return {**base, "tiene_pbp": False, "error": "sin token"}
    try:
        res = fetch_y_analizar(token, session=session)
    except Exception as exc:
        return {**base, "tiene_pbp": False, "error": str(exc)}
    return {**base, **res}


def main() -> int:
    p = argparse.ArgumentParser(description="Analiza PBP de MINI MASC (subs Q3 + cuartos consecutivos)")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--limit", type=int, default=0, help="Procesar solo los primeros N (debug)")
    p.add_argument("--progress", action="store_true")
    args = p.parse_args()

    partidos = _leer_partidos()
    if args.limit > 0:
        partidos = partidos[: args.limit]
    total = len(partidos)
    if args.progress:
        print(f"Partidos a analizar: {total}", file=sys.stderr)

    resultados: List[Optional[Dict[str, object]]] = [None] * total
    session = requests.Session()

    def _task(idx: int, row: Dict[str, str]):
        return idx, _analizar_uno(row, session)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(_task, i, r) for i, r in enumerate(partidos)]
        done = 0
        for fut in as_completed(futures):
            idx, res = fut.result()
            resultados[idx] = res
            done += 1
            if args.progress and (done % 25 == 0 or done == total):
                print(f"  pbp {done}/{total}", file=sys.stderr, flush=True)

    resultados = [r for r in resultados if r is not None]

    # JSON por partido (keyed por ID_PARTIDO)
    por_partido: Dict[str, Dict[str, object]] = {}
    for r in resultados:
        token = str(r.get("ID_PARTIDO") or "")
        por_partido[token] = {
            "fecha": r.get("Fecha"),
            "local": r.get("Local"),
            "visitante": r.get("Visitante"),
            "pts_local": r.get("PTS_LOCAL"),
            "pts_visitante": r.get("PTS_VISITANTE"),
            "tiene_pbp": bool(r.get("tiene_pbp")),
            "hubo_subs_q3": bool(r.get("hubo_subs_q3")),
            "subs_q3_entra": int(r.get("subs_q3_entra") or 0),
            "subs_q3_sale": int(r.get("subs_q3_sale") or 0),
            "subs_q3": r.get("subs_q3") or [],
            "hubo_consecutivos": bool(r.get("hubo_consecutivos")),
            "n_consecutivos": int(r.get("n_consecutivos") or 0),
            "jugadores_consecutivos": r.get("jugadores_consecutivos") or [],
            "error": r.get("error"),
        }

    con_pbp = [r for r in resultados if r.get("tiene_pbp")]
    resumen = {
        "total_partidos": total,
        "con_pbp": len(con_pbp),
        "sin_pbp": total - len(con_pbp),
        "con_subs_q3": sum(1 for r in con_pbp if r.get("hubo_subs_q3")),
        "con_consecutivos": sum(1 for r in con_pbp if r.get("hubo_consecutivos")),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump({"resumen": resumen, "partidos": por_partido}, f, ensure_ascii=False, indent=2)

    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(CSV_HEADER))
        w.writeheader()
        for r in resultados:
            w.writerow(
                {
                    "Fecha": r.get("Fecha"),
                    "Local": r.get("Local"),
                    "Visitante": r.get("Visitante"),
                    "PTS_LOCAL": r.get("PTS_LOCAL"),
                    "PTS_VISITANTE": r.get("PTS_VISITANTE"),
                    "ID_PARTIDO": r.get("ID_PARTIDO"),
                    "TIENE_PBP": "1" if r.get("tiene_pbp") else "0",
                    "HUBO_SUBS_Q3": "1" if r.get("hubo_subs_q3") else "0",
                    "SUBS_Q3_ENTRA": r.get("subs_q3_entra") or 0,
                    "SUBS_Q3_SALE": r.get("subs_q3_sale") or 0,
                    "HUBO_CONSECUTIVOS": "1" if r.get("hubo_consecutivos") else "0",
                    "N_CONSECUTIVOS": r.get("n_consecutivos") or 0,
                    "DETALLE_SUBS_Q3": _fmt_subs(r.get("subs_q3") or []),
                    "DETALLE_CONSECUTIVOS": _fmt_consec(r.get("jugadores_consecutivos") or []),
                }
            )

    print(json.dumps({"resumen": resumen, "json": str(OUT_JSON), "csv": str(OUT_CSV)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
