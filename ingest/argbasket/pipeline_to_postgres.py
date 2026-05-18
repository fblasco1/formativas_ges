from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Sequence, Tuple

import requests

from ingest.argbasket.partido import (
    BASE_URL_DEFAULT,
    fetch_partido_en_vivo_html,
    fetch_partido_estadisticas_html,
    parse_boxscore_html,
    parse_play_by_play_html,
)
from ingest.argbasket.pipeline_fixture import generar_fixture_consolidado, write_csv
from persist.persistir_postgres import (
    build_argbasket_partido_row,
    connect,
    ensure_schema_argbasket,
    replace_play_by_play_events,
    upsert_partido_argbasket,
)


def normalize_argbasket_token(token: str) -> str:
    t = (token or "").strip()
    if not t:
        return ""
    if not t.endswith("=="):
        t = t + "=="
    return t


def _fetch_boxscore_pbp(
    token: str,
    *,
    base_url: str,
    timeout_s: int,
    want_stats: bool = True,
    want_pbp: bool = True,
) -> Tuple[Optional[Dict[str, object]], List[Dict[str, object]], Optional[str]]:
    tok = normalize_argbasket_token(token)
    if not tok:
        return None, [], "token_vacio"
    if not want_stats and not want_pbp:
        return None, [], None
    s = requests.Session()
    try:
        box: Optional[Dict[str, object]] = None
        typed_pbp: List[Dict[str, object]] = []
        if want_stats:
            stats_html = fetch_partido_estadisticas_html(
                id_partido_token=tok,
                base_url=base_url,
                session=s,
                timeout_s=timeout_s,
            )
            b = parse_boxscore_html(stats_html)
            box = b if isinstance(b, dict) else {}
        if want_pbp:
            pbp_html = fetch_partido_en_vivo_html(
                id_partido_token=tok,
                base_url=base_url,
                session=s,
                timeout_s=timeout_s,
            )
            pbp = parse_play_by_play_html(pbp_html)
            if not isinstance(pbp, list):
                pbp = []
            typed_pbp = [e for e in pbp if isinstance(e, dict)]
        return box, typed_pbp, None
    except Exception as exc:
        return None, [], str(exc)


def estadisticas_con_boxscore(box: Dict[str, object]) -> Dict[str, object]:
    out: Dict[str, object] = {"fuente": "argentina.basketball"}
    for k, v in box.items():
        out[k] = v
    return out


def _jsonb_a_dict(value: object) -> Dict[str, object]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _process_one_match(
    r: Dict[str, str],
    *,
    base_url: str,
    temporada: str,
    competencia: str,
    skip_stats: bool,
    skip_pbp: bool,
    timeout_s: int,
) -> Dict[str, object]:
    tok = r["id_partido_token"]
    comp_cat = int((r.get("compCatId") or "0").strip() or "0")
    cat = (r.get("Categoria") or "").strip()
    fecha = (r.get("Fecha_Programada") or "").strip()
    loc = (r.get("Local") or "").strip()
    vis = (r.get("Visitante") or "").strip()
    pl = (r.get("PTS_LOCAL") or "").strip()
    pv = (r.get("PTS_VISITANTE") or "").strip()

    conn = connect()
    try:
        box: Optional[Dict[str, object]] = None
        pbp_events: List[Dict[str, object]] = []
        err: Optional[str] = None

        if not skip_stats or not skip_pbp:
            box, pbp_events, err = _fetch_boxscore_pbp(
                tok,
                base_url=base_url,
                timeout_s=timeout_s,
                want_stats=not skip_stats,
                want_pbp=not skip_pbp,
            )

        prev_stats: Dict[str, object] = {}
        with conn.cursor() as cur:
            cur.execute(
                "SELECT estadisticas FROM partidos WHERE partido_id = %s",
                (tok,),
            )
            ex = cur.fetchone()
            if ex and ex[0] is not None:
                prev_stats = _jsonb_a_dict(ex[0])

        if skip_stats:
            est_obj: object = prev_stats
        elif box:
            est_obj = estadisticas_con_boxscore(box)
        else:
            est_obj = prev_stats if prev_stats else {}

        with conn.cursor() as cur:
            row_db = build_argbasket_partido_row(
                partido_id=tok,
                comp_cat_id=comp_cat,
                categoria=cat,
                fecha=fecha,
                local=loc,
                visitante=vis,
                pts_local=pl or None,
                pts_visitante=pv or None,
                estadisticas=est_obj,
                temporada=temporada,
                competencia=competencia,
            )
            upsert_partido_argbasket(cur, row_db)
            if pbp_events and not skip_pbp:
                replace_play_by_play_events(cur, tok, pbp_events)
            elif not skip_pbp and not pbp_events and not err:
                replace_play_by_play_events(cur, tok, [])
        conn.commit()

        return {
            "partido_id": tok,
            "fetch_error": err,
            "stats_ok": bool(box) and not skip_stats and not err,
            "pbp_ok": bool(pbp_events) and not skip_pbp and not err,
        }
    finally:
        conn.close()


def run_ingest(
    *,
    fecha_ini: str,
    fecha_fin: str,
    base_url: str = BASE_URL_DEFAULT,
    temporada: str = "2026",
    competencia: str = "LIGA FEDERAL FORMATIVAS",
    incluir_horas_reales: bool = True,
    max_horas_por_categoria: int = 0,
    sleep_s_entre_horas: float = 0.0,
    progress: bool = False,
    progress_cada: int = 25,
    skip_stats: bool = False,
    skip_pbp: bool = False,
    limite: int = 0,
    workers: int = 1,
    sleep_s_entre_partidos: float = 0.0,
    timeout_s: int = 60,
    export_csv: Optional[str] = None,
    config_path: Optional[str] = None,
) -> Dict[str, object]:
    if config_path:
        import os

        os.environ["CONFIG_PATH"] = config_path

    rows = generar_fixture_consolidado(
        fecha_ini=fecha_ini,
        fecha_fin=fecha_fin,
        base_url=base_url,
        incluir_horas_reales=incluir_horas_reales,
        max_horas_por_categoria=max_horas_por_categoria,
        sleep_s_entre_horas=sleep_s_entre_horas,
        progress=progress,
        progress_cada=progress_cada,
    )

    if export_csv:
        write_csv(export_csv, rows)
        if progress:
            print(f"[ingest] CSV exportado: {export_csv} ({len(rows)} filas)", file=sys.stderr)

    seen: set[str] = set()
    work: List[Dict[str, str]] = []
    for r in rows:
        tok = normalize_argbasket_token((r.get("id_partido_token") or "").strip())
        if not tok or tok in seen:
            continue
        seen.add(tok)
        rr = dict(r)
        rr["id_partido_token"] = tok
        work.append(rr)
        if limite and len(work) >= limite:
            break

    with connect() as conn:
        with conn.cursor() as cur:
            ensure_schema_argbasket(cur)
        conn.commit()

    stats_ok = 0
    stats_err = 0
    pbp_ok = 0
    pbp_err = 0

    if workers <= 1:
        for i, r in enumerate(work):
            out = _process_one_match(
                r,
                base_url=base_url,
                temporada=temporada,
                competencia=competencia,
                skip_stats=skip_stats,
                skip_pbp=skip_pbp,
                timeout_s=timeout_s,
            )
            if out.get("fetch_error"):
                stats_err += 1
                pbp_err += 1
            else:
                if out.get("stats_ok"):
                    stats_ok += 1
                elif not skip_stats:
                    stats_err += 1
                if out.get("pbp_ok"):
                    pbp_ok += 1
                elif not skip_pbp:
                    pbp_err += 1
            if sleep_s_entre_partidos > 0:
                time.sleep(sleep_s_entre_partidos)
            if progress and (i + 1) % 25 == 0:
                print(
                    f"[ingest] {i + 1}/{len(work)} stats_ok={stats_ok} pbp_ok={pbp_ok}",
                    file=sys.stderr,
                )
    else:
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {
                ex.submit(
                    _process_one_match,
                    r,
                    base_url=base_url,
                    temporada=temporada,
                    competencia=competencia,
                    skip_stats=skip_stats,
                    skip_pbp=skip_pbp,
                    timeout_s=timeout_s,
                ): r
                for r in work
            }
            for fut in as_completed(futs):
                done += 1
                try:
                    out = fut.result()
                except Exception as exc:
                    stats_err += 1
                    pbp_err += 1
                    if progress:
                        print(f"[ingest] error worker: {exc}", file=sys.stderr)
                    continue
                if out.get("fetch_error"):
                    stats_err += 1
                    pbp_err += 1
                else:
                    if out.get("stats_ok"):
                        stats_ok += 1
                    elif not skip_stats:
                        stats_err += 1
                    if out.get("pbp_ok"):
                        pbp_ok += 1
                    elif not skip_pbp:
                        pbp_err += 1
                if progress and done % 25 == 0:
                    print(
                        f"[ingest] {done}/{len(work)} stats_ok={stats_ok} pbp_ok={pbp_ok}",
                        file=sys.stderr,
                    )

    return {
        "fixture_rows": len(rows),
        "partidos_unicos": len(work),
        "partidos_upsert": len(work),
        "stats_ok": stats_ok,
        "stats_err": stats_err,
        "pbp_ok": pbp_ok,
        "pbp_err": pbp_err,
        "export_csv": export_csv,
        "workers": workers,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Fixture 2026 argentina.basketball → PostgreSQL (partidos + play_by_play)."
    )
    p.add_argument("--fecha-ini", required=True, help="YYYY-MM-DD")
    p.add_argument("--fecha-fin", required=True, help="YYYY-MM-DD")
    p.add_argument("--base-url", default=BASE_URL_DEFAULT)
    p.add_argument("--temporada", default="2026")
    p.add_argument("--competencia", default="LIGA FEDERAL FORMATIVAS")
    p.add_argument("--sin-horas-reales", action="store_true")
    p.add_argument("--max-horas-por-categoria", type=int, default=0)
    p.add_argument("--sleep-horas", type=float, default=0.0)
    p.add_argument("--progress", action="store_true")
    p.add_argument("--progress-cada", type=int, default=25)
    p.add_argument("--skip-stats", action="store_true")
    p.add_argument("--skip-pbp", action="store_true")
    p.add_argument("--limite", type=int, default=0, help="Solo N partidos únicos (prueba).")
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--sleep-partido", type=float, default=0.0)
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument(
        "--export-csv",
        default="",
        help="Si se indica ruta, escribe fixture consolidado además de persistir.",
    )
    p.add_argument("--config", dest="config_path", default="", help="Ruta config.json (DB).")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    export = args.export_csv.strip() or None
    cfg = args.config_path.strip() or None

    result = run_ingest(
        fecha_ini=args.fecha_ini,
        fecha_fin=args.fecha_fin,
        base_url=args.base_url,
        temporada=args.temporada,
        competencia=args.competencia,
        incluir_horas_reales=not args.sin_horas_reales,
        max_horas_por_categoria=args.max_horas_por_categoria,
        sleep_s_entre_horas=args.sleep_horas,
        progress=args.progress,
        progress_cada=args.progress_cada,
        skip_stats=args.skip_stats,
        skip_pbp=args.skip_pbp,
        limite=args.limite,
        workers=max(1, int(args.workers)),
        sleep_s_entre_partidos=args.sleep_partido,
        timeout_s=args.timeout,
        export_csv=export,
        config_path=cfg,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
