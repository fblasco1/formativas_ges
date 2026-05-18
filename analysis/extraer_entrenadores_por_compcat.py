# -*- coding: utf-8 -*-
"""
Descarga el fixture ``CargarFixture`` para un ``compCatId`` y rango de fechas,
luego baja el HTML de estadísticas por partido y arma el CSV de entrenadores
(misma lógica de unificación que ``extraer_entrenadores_partidos_2026.py``).

Ejemplo (Superior Masculino):
  python analysis/extraer_entrenadores_por_compcat.py \\
    --comp-cat-id 5074 --fecha-ini 2025-03-01 --fecha-fin 2026-05-10 \\
    --categoria "SUPERIOR MASCULINO"
"""

from __future__ import annotations

import argparse
import csv
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from extraer_entrenadores_partidos_2026 import (  # noqa: E402
    _fieldnames,
    _postprocesar_filas_entrenadores,
    _rows_for_html,
)
from ingest.argbasket.partido import fetch_partido_estadisticas_html  # noqa: E402
from ingest.febamba.fixture_parser_arg import ArgentinaFixtureParser  # noqa: E402


def _fetch_one(
    session: requests.Session,
    token: str,
    *,
    base_url: str,
    timeout_s: int,
) -> Tuple[str, Optional[str]]:
    try:
        html = fetch_partido_estadisticas_html(
            id_partido_token=token,
            base_url=base_url,
            session=session,
            timeout_s=timeout_s,
        )
        return token, html
    except Exception:
        return token, None


def main() -> int:
    p = argparse.ArgumentParser(description="Entrenadores desde fixture compCatId + estadísticas.")
    p.add_argument("--comp-cat-id", type=int, required=True)
    p.add_argument("--fecha-ini", required=True, help="YYYY-MM-DD")
    p.add_argument("--fecha-fin", required=True, help="YYYY-MM-DD")
    p.add_argument(
        "--categoria",
        required=True,
        help='Etiqueta de categoría en el CSV (ej. "SUPERIOR MASCULINO").',
    )
    p.add_argument("--out", default="", help="CSV salida (default: entrenadores_compcat_{id}.csv)")
    p.add_argument("--base-url", default="https://argentina.basketball")
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--chunk-days", type=int, default=45)
    p.add_argument("--mantener-duplicados", action="store_true")
    p.add_argument("--mantener-sin-entrenador", action="store_true")
    args = p.parse_args()

    out_path = args.out or f"entrenadores_compcat_{args.comp_cat_id}.csv"

    parser = ArgentinaFixtureParser(
        base_url=args.base_url,
        timeout_s=args.timeout,
        chunk_days=args.chunk_days,
    )
    raw_fixture = parser.fetch_all_chunked(
        args.comp_cat_id,
        args.fecha_ini,
        args.fecha_fin,
    )

    tokens_order: List[str] = []
    seen: set[str] = set()
    for row in raw_fixture:
        t = (row.get("id_partido_token") or "").strip()
        if t and t not in seen:
            seen.add(t)
            tokens_order.append(t)

    print(f"Partidos únicos en fixture: {len(tokens_order)}", flush=True)

    html_by_token: Dict[str, str] = {}
    if args.workers <= 1:
        session = requests.Session()
        for i, tok in enumerate(tokens_order):
            _, html = _fetch_one(session, tok, base_url=args.base_url, timeout_s=args.timeout)
            if html:
                html_by_token[tok] = html
            if (i + 1) % 50 == 0:
                print(f"  Estadísticas {i + 1}/{len(tokens_order)}...", flush=True)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {}
            for tok in tokens_order:
                sess = requests.Session()
                futs[ex.submit(_fetch_one, sess, tok, base_url=args.base_url, timeout_s=args.timeout)] = tok
            for fut in as_completed(futs):
                tok, html = fut.result()
                if html:
                    html_by_token[tok] = html

    categoria = args.categoria.strip()
    out_rows: List[Dict[str, str]] = []
    stub = {"Categoria": categoria}
    for tok in tokens_order:
        html = html_by_token.get(tok)
        if not html:
            continue
        out_rows.extend(_rows_for_html(stub, html))

    out_rows = _postprocesar_filas_entrenadores(
        out_rows,
        mantener_duplicados=args.mantener_duplicados,
        mantener_sin_entrenador=args.mantener_sin_entrenador,
    )

    fn = _fieldnames()
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fn)
        w.writeheader()
        for row in out_rows:
            w.writerow({k: row.get(k, "") for k in fn})

    # Entrenadores distintos (nombre normalizado como en estadistica_entrenadores_multiclub)
    import re

    def _norm(s: str) -> str:
        s = (s or "").strip().upper()
        return re.sub(r"\s+", " ", s)

    distintos = {_norm(r.get("Entrenador", "")) for r in out_rows if (r.get("Entrenador") or "").strip()}
    print(f"Filas CSV: {len(out_rows)} -> {out_path}")
    print(f"Entrenadores distintos (con dato): {len(distintos)}")
    print(f"Partidos sin estadísticas descargables: {len(tokens_order) - len(html_by_token)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
