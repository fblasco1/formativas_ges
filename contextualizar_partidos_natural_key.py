# -*- coding: utf-8 -*-
"""
Actualiza en PostgreSQL el contexto de torneo (fase_ges, grupo_ges, fase, grupo,
zona, ronda, nivel) emparejando filas ya persistidas por clave natural:
fecha (DD/MM/YYYY) + equipo local + equipo visitante.

La referencia es un CSV (o JSON array) con al menos: fecha, local, visitante,
y el texto de los combos GES ``fase_ges`` + ``grupo_ges`` (para aplicar
``merge_contexto_torneo``), o bien columnas ya normalizadas en modo directo.

Uso típico (solo lectura de impacto):
  python contextualizar_partidos_natural_key.py --referencia ref.csv --temporada 2025 --dry-run

Recorriendo la página de competencia GES (sin widget):
  python contextualizar_partidos_natural_key.py --desde-competicion --competencia 1178 --temporada 2024 --comp-id 1178 --dry-run

Aplicar:
  python contextualizar_partidos_natural_key.py --referencia ref.csv --temporada 2025
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

import psycopg

from ingest.febamba.fixture_contexto import merge_contexto_torneo
from ingest.febamba.natural_key import (
    extract_fecha_dd_mm_yyyy,
    natural_key_from_db_partido_row,
    natural_match_key,
)


def load_config(path: str = "config.json") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_dsn(cfg: Dict[str, Any]) -> str:
    db = cfg.get("db", {})
    host = db.get("host", "localhost")
    port = db.get("port", 5432)
    user = db.get("user")
    password = db.get("password")
    name = db.get("name")
    if not user or not password or not name:
        raise RuntimeError("Config incompleta en config.json (db.user/db.password/db.name)")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def get_conn(config_path: Optional[str] = None) -> psycopg.Connection:
    path = config_path or os.environ.get("CONFIG_PATH", "config.json")
    cfg = load_config(path)
    return psycopg.connect(build_dsn(cfg))


def setup_logger(log_path: str) -> logging.Logger:
    logger = logging.getLogger("contextualizar")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


def ensure_partidos_torneo_columns(conn: psycopg.Connection, logger: logging.Logger) -> None:
    """
    Evita el error: psycopg.errors.UndefinedColumn (p.fase_ges, etc.)
    Migración idempotente.
    """
    stmts = [
        "ALTER TABLE partidos ADD COLUMN IF NOT EXISTS fase_ges TEXT",
        "ALTER TABLE partidos ADD COLUMN IF NOT EXISTS grupo_ges TEXT",
        "ALTER TABLE partidos ADD COLUMN IF NOT EXISTS zona TEXT",
        "ALTER TABLE partidos ADD COLUMN IF NOT EXISTS ronda TEXT",
        "ALTER TABLE partidos ADD COLUMN IF NOT EXISTS nivel TEXT",
        "ALTER TABLE partidos ADD COLUMN IF NOT EXISTS fase TEXT",
        "ALTER TABLE partidos ADD COLUMN IF NOT EXISTS grupo TEXT",
        "ALTER TABLE partidos ADD COLUMN IF NOT EXISTS fase_id INTEGER",
        "ALTER TABLE partidos ADD COLUMN IF NOT EXISTS grupo_id INTEGER",
    ]
    with conn.cursor() as cur:
        for sql in stmts:
            cur.execute(sql)
    conn.commit()
    logger.info("OK: columnas de torneo verificadas/migradas en `partidos`.")


def _lower_row(d: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if k is None:
            continue
        key = str(k).strip().lower()
        out[key] = v
    return out


def natural_key_from_reference_row(row: Dict[str, Any]) -> str:
    r = _lower_row(row)
    fecha_raw = str(r.get("fecha") or "").strip()
    fe = extract_fecha_dd_mm_yyyy(fecha_raw)
    loc = str(r.get("local") or "").strip()
    vis = str(r.get("visitante") or "").strip()
    if not fe or not loc or not vis:
        return ""
    return natural_match_key(fe, loc, vis)


def pick_fase_grupo_ges(row: Dict[str, Any]) -> Tuple[str, str]:
    r = _lower_row(row)
    fase = str(
        r.get("fase_ges")
        or r.get("fase_combo")
        or r.get("nombre_fase")
        or r.get("combo_fase")
        or ""
    ).strip()
    grupo = str(
        r.get("grupo_ges")
        or r.get("grupo_combo")
        or r.get("nombre_grupo")
        or r.get("combo_grupo")
        or ""
    ).strip()
    return fase, grupo


def _s(v: Any) -> Optional[str]:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    return str(v).strip()


def ctx_desde_referencia(
    row: Dict[str, Any], temporada: str, *, modo_directo: bool
) -> Optional[Dict[str, Any]]:
    """
    Por defecto: textos de combo GES ``fase_ges`` / ``grupo_ges`` → ``merge_contexto_torneo``.
    Con ``--modo-directo``: columnas ya normalizadas (fase, grupo, zona, ronda, nivel, …) sin merge.
    """
    r = _lower_row(row)
    if modo_directo:
        return {
            "fase": _s(r.get("fase")),
            "grupo": _s(r.get("grupo")),
            "fase_ges": _s(r.get("fase_ges") or r.get("fase_combo")),
            "grupo_ges": _s(r.get("grupo_ges") or r.get("grupo_combo")),
            "zona": _s(r.get("zona")),
            "ronda": _s(r.get("ronda")),
            "nivel": _s(r.get("nivel")),
        }
    fase_ges, grupo_ges = pick_fase_grupo_ges(row)
    if not fase_ges and not grupo_ges:
        return None
    return merge_contexto_torneo(temporada, fase_ges or "TODAS", grupo_ges or "TODOS")


def load_referencia_csv(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_referencia_json(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "partidos" in data:
        return list(data["partidos"])
    raise ValueError("JSON: se espera una lista de objetos o { \"partidos\": [...] }")


def load_referencia(path: str) -> List[Dict[str, Any]]:
    low = path.lower()
    if low.endswith(".json"):
        return load_referencia_json(path)
    return load_referencia_csv(path)


def fetch_partidos_db(
    cur: psycopg.Cursor,
    *,
    temporada: str,
    comp_id: Optional[int],
    solo_sin_contexto: bool,
) -> List[Dict[str, Any]]:
    cond = ["p.temporada = %(temporada)s"]
    params: Dict[str, Any] = {"temporada": temporada}
    if comp_id is not None:
        cond.append("p.comp_id = %(comp_id)s")
        params["comp_id"] = comp_id
    if solo_sin_contexto:
        cond.append("(p.fase_ges IS NULL OR trim(p.fase_ges) = '')")
        cond.append("(p.grupo_ges IS NULL OR trim(p.grupo_ges) = '')")
    sql = f"""
        SELECT p.partido_id, p.fecha, p.local, p.visitante,
               p.fase_ges, p.grupo_ges, p.fase, p.grupo, p.zona, p.ronda, p.nivel,
               p.fase_id, p.grupo_id
        FROM partidos p
        WHERE {" AND ".join(cond)}
    """
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def indexar_por_clave_natural(rows: Sequence[Dict[str, Any]]) -> Dict[str, List[str]]:
    idx: Dict[str, List[str]] = {}
    for r in rows:
        k = natural_key_from_db_partido_row(r)
        if not k:
            continue
        idx.setdefault(k, []).append(str(r["partido_id"]))
    return idx


UPDATE_SQL = """
UPDATE partidos SET
    fase_ges = %(fase_ges)s,
    grupo_ges = %(grupo_ges)s,
    fase = %(fase)s,
    grupo = %(grupo)s,
    zona = %(zona)s,
    ronda = %(ronda)s,
    nivel = %(nivel)s,
    fase_id = COALESCE(%(fase_id)s, fase_id),
    grupo_id = COALESCE(%(grupo_id)s, grupo_id)
WHERE partido_id = %(partido_id)s
"""


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Contextualiza partidos en BD por clave natural (fecha + local + visitante)."
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--referencia",
        help="CSV o JSON con columnas fecha, local, visitante y fase_ges/grupo_ges (o modo directo).",
    )
    src.add_argument(
        "--desde-competicion",
        action="store_true",
        help="Armar la referencia recorriendo competicion.aspx (postbacks categoría/fase/grupo).",
    )
    p.add_argument(
        "--competencia",
        type=int,
        help="id_competencia GES (query competencia=) cuando se usa --desde-competicion.",
    )
    p.add_argument(
        "--categoria-id",
        type=int,
        dest="categoria_id",
        help="Solo una categoría (id DDLCategorias); si se omite, se recorren todas.",
    )
    p.add_argument(
        "--sleep-entre-posts",
        type=float,
        default=0.35,
        dest="sleep_posts",
        help="Pausa en segundos entre POSTs a competicion.aspx (default 0.35).",
    )
    p.add_argument("--temporada", required=True, help="Ej: 2025")
    p.add_argument(
        "--comp-id",
        type=int,
        dest="comp_id",
        help="Limitar UPDATE a partidos.comp_id (debe coincidir con --competencia si aplica).",
    )
    p.add_argument(
        "--solo-sin-contexto",
        action="store_true",
        help="Solo filas sin fase_ges ni grupo_ges en BD (recomendado).",
    )
    p.add_argument("--dry-run", action="store_true", help="No ejecuta UPDATE")
    p.add_argument(
        "--modo-directo",
        action="store_true",
        help="La referencia ya trae fase, grupo, zona, ronda, nivel (y opcionalmente fase_ges/grupo_ges); no aplica merge_contexto_torneo.",
    )
    p.add_argument("--config", dest="config_path", default=None, help="Ruta a config.json")
    p.add_argument(
        "--log",
        dest="log_path",
        default="contextualizar_partidos_natural_key.log",
        help="Ruta del archivo .log (default contextualizar_partidos_natural_key.log)",
    )
    ns = p.parse_args(argv)
    if ns.desde_competicion:
        if ns.competencia is None:
            p.error("--desde-competicion requiere --competencia <id>")
    else:
        if not ns.referencia:
            p.error("Indique --referencia archivo.csv|.json o use --desde-competicion")
    return ns


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logger = setup_logger(args.log_path)
    logger.info(
        "Inicio | temporada=%s comp_id=%s dry_run=%s solo_sin_contexto=%s fuente=%s",
        args.temporada,
        args.comp_id,
        args.dry_run,
        args.solo_sin_contexto,
        "competicion.aspx" if args.desde_competicion else (args.referencia or ""),
    )

    if args.desde_competicion:
        from ingest.febamba.competicion_calendar import CompeticionCalendarScraper
        from ingest.http_client import HttpClient

        scraper = CompeticionCalendarScraper(
            HttpClient(), sleep_s=float(args.sleep_posts or 0.35)
        )
        ref_rows = []
        seen_nk: set[str] = set()
        n_raw = 0
        for row in scraper.iter_skeleton_rows(
            int(args.competencia), id_categoria=args.categoria_id
        ):
            n_raw += 1
            nk = natural_key_from_reference_row(row)
            if nk and nk not in seen_nk:
                seen_nk.add(nk)
                ref_rows.append(row)
            if n_raw % 250 == 0:
                logger.info(
                    "competicion.aspx progreso: filas=%s unicas_por_clave=%s",
                    n_raw,
                    len(ref_rows),
                )
        logger.info(
            "competicion.aspx fin: filas=%s unicas_por_clave=%s",
            n_raw,
            len(ref_rows),
        )
    else:
        ref_rows = load_referencia(args.referencia)
    config_path = args.config_path or os.environ.get("CONFIG_PATH", "config.json")

    matched = 0
    updated = 0
    sin_clave_ref = 0
    sin_ctx = 0
    sin_match_bd = 0
    colision_bd = 0

    with get_conn(config_path) as conn:
        ensure_partidos_torneo_columns(conn, logger)
        with conn.cursor() as cur:
            db_rows = fetch_partidos_db(
                cur,
                temporada=args.temporada,
                comp_id=args.comp_id,
                solo_sin_contexto=args.solo_sin_contexto,
            )
        idx = indexar_por_clave_natural(db_rows)
        logger.info(
            "BD cargada: partidos=%s claves_naturales=%s",
            len(db_rows),
            len(idx),
        )

        for raw in ref_rows:
            nk = natural_key_from_reference_row(raw)
            if not nk:
                sin_clave_ref += 1
                continue
            ctx = ctx_desde_referencia(
                raw, args.temporada, modo_directo=args.modo_directo
            )
            if not ctx or not (
                ctx.get("fase_ges")
                or ctx.get("grupo_ges")
                or ctx.get("fase")
                or ctx.get("zona")
            ):
                sin_ctx += 1
                continue
            pids = idx.get(nk, [])
            if not pids:
                sin_match_bd += 1
                continue
            if len(pids) > 1:
                colision_bd += 1
            lr = _lower_row(raw)

            def _optional_int(val: Any) -> Optional[int]:
                if val is None:
                    return None
                s = str(val).strip()
                if s.lstrip("-").isdigit():
                    return int(s)
                return None

            fase_id_i = _optional_int(lr.get("fase_id"))
            grupo_id_i = _optional_int(lr.get("grupo_id"))
            for pid in pids:
                matched += 1
                payload = {
                    "partido_id": pid,
                    "fase_ges": ctx.get("fase_ges"),
                    "grupo_ges": ctx.get("grupo_ges"),
                    "fase": ctx.get("fase"),
                    "grupo": ctx.get("grupo"),
                    "zona": ctx.get("zona"),
                    "ronda": ctx.get("ronda"),
                    "nivel": ctx.get("nivel"),
                    "fase_id": fase_id_i,
                    "grupo_id": grupo_id_i,
                }
                if args.dry_run:
                    updated += 1
                    continue
                with conn.cursor() as cur2:
                    cur2.execute(UPDATE_SQL, payload)
                updated += 1
            if (matched % 500) == 0:
                logger.info(
                    "Progreso: matched=%s updates=%s sin_match_bd=%s colisiones=%s",
                    matched,
                    updated,
                    sin_match_bd,
                    colision_bd,
                )
        if not args.dry_run:
            conn.commit()

    logger.info(
        f"Referencias: {len(ref_rows)} | clave ref vacía: {sin_clave_ref} | sin contexto parseable: {sin_ctx}\n"
        f"Emparejamientos partido_id: {matched} | filas ref sin match en BD: {sin_match_bd}\n"
        f"Claves BD con >1 partido_id: {colision_bd} | updates {'simulados' if args.dry_run else 'ejecutados'}: {updated}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
