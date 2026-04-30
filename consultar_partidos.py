from __future__ import annotations

import argparse
import csv
import json
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import psycopg


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


def get_conn() -> psycopg.Connection:
    config_path = os.environ.get("CONFIG_PATH", "config.json")
    cfg = load_config(config_path)
    dsn = build_dsn(cfg)
    return psycopg.connect(dsn)


def _add_condition(
    conditions: List[str],
    params: Dict[str, Any],
    sql_fragment: str,
    param_name: str,
    value: Any,
) -> None:
    if value is None:
        return
    conditions.append(sql_fragment)
    params[param_name] = value


def build_query(args: argparse.Namespace) -> Tuple[str, Dict[str, Any]]:
    params: Dict[str, Any] = {}
    conditions: List[str] = []

    _add_condition(conditions, params, "p.partido_id = %(partido_id)s", "partido_id", args.partido_id)
    _add_condition(conditions, params, "p.comp_id = %(comp_id)s", "comp_id", args.comp_id)
    _add_condition(conditions, params, "p.temporada = %(temporada)s", "temporada", args.temporada)
    _add_condition(conditions, params, "p.categoria ILIKE %(categoria)s", "categoria", _maybe_ilike(args.categoria))
    _add_condition(conditions, params, "p.fase ILIKE %(fase)s", "fase", _maybe_ilike(args.fase))
    _add_condition(conditions, params, "p.grupo ILIKE %(grupo)s", "grupo", _maybe_ilike(args.grupo))
    _add_condition(conditions, params, "p.zona ILIKE %(zona)s", "zona", _maybe_ilike(args.zona))
    _add_condition(conditions, params, "p.estado = %(estado)s", "estado", args.estado)

    if args.desde:
        conditions.append("to_date(split_part(p.fecha, ' ', 1), 'DD/MM/YYYY') >= to_date(%(desde)s, 'YYYY-MM-DD')")
        params["desde"] = args.desde
    if args.hasta:
        conditions.append("to_date(split_part(p.fecha, ' ', 1), 'DD/MM/YYYY') <= to_date(%(hasta)s, 'YYYY-MM-DD')")
        params["hasta"] = args.hasta

    if args.q:
        conditions.append("(p.local ILIKE %(q)s OR p.visitante ILIKE %(q)s)")
        params["q"] = f"%{args.q}%"

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    # Orden: por fecha desc, y si empata por partido_id para estabilidad.
    sql = f"""
    SELECT
        p.partido_id,
        p.comp_id,
        p.competencia,
        p.temporada,
        p.categoria,
        p.categoria_id,
        p.fase,
        p.fase_id,
        p.grupo,
        p.grupo_id,
        p.fase_ges,
        p.grupo_ges,
        p.zona,
        p.ronda,
        p.nivel,
        p.fecha,
        p.local,
        p.visitante,
        p.estado
    FROM partidos p
    {where}
    ORDER BY
        to_date(split_part(p.fecha, ' ', 1), 'DD/MM/YYYY') DESC NULLS LAST,
        p.partido_id ASC
    LIMIT %(limit)s
    OFFSET %(offset)s
    """
    params["limit"] = max(1, int(args.limit))
    params["offset"] = max(0, int(args.offset))
    return sql, params


def _maybe_ilike(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    # Si el usuario ya pasó % lo respetamos; si no, hacemos contains.
    if "%" in value:
        return value
    return f"%{value}%"


def fetch_all(sql: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
    return [dict(zip(cols, row)) for row in rows]


def print_rows(rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        print("Sin resultados.")
        return
    for r in rows:
        print(
            f"{r['fecha']:<18} | {r['estado']:<9} | "
            f"{(r.get('fase') or ''):<18} | {(r.get('zona') or ''):<10} | {(r.get('grupo') or ''):<8} | "
            f"{r['local']} vs {r['visitante']} | partido_id={r['partido_id']}"
        )
    print(f"\nTotal filas: {len(rows)}")


def write_csv(path: str, rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        raise RuntimeError("No hay filas para exportar.")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Consulta la tabla 'partidos' en la base febamba (PostgreSQL)."
    )
    p.add_argument("--partido-id", dest="partido_id", help="Partido exacto por ID")
    p.add_argument("--comp-id", dest="comp_id", type=int, help="ID de competencia (comp_id)")
    p.add_argument("--temporada", help="Ej: 2026")
    p.add_argument("--categoria", help="Filtro por texto (ILIKE). Ej: 'INFANTILES' o '%%INFANTILES%%'")
    p.add_argument("--fase", help="Filtro por texto (ILIKE). Ej: 'CLASIFICACION'")
    p.add_argument("--grupo", help="Filtro por texto (ILIKE). Ej: 'NORTE 1A'")
    p.add_argument("--zona", help="Filtro por texto (ILIKE). Ej: 'CENTRO'")
    p.add_argument("--estado", choices=["PENDIENTE", "COMPLETO"], help="Estado exacto")
    p.add_argument("--desde", help="Fecha desde (YYYY-MM-DD), compara contra p.fecha")
    p.add_argument("--hasta", help="Fecha hasta (YYYY-MM-DD), compara contra p.fecha")
    p.add_argument("-q", help="Busca en local/visitante (ILIKE)")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--csv", dest="csv_path", help="Exporta resultados a CSV (ruta destino)")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    sql, params = build_query(args)
    try:
        rows = fetch_all(sql, params)
    except Exception as exc:
        print(f"Error consultando la base: {exc}")
        return 2

    if args.csv_path:
        try:
            write_csv(args.csv_path, rows)
        except Exception as exc:
            print(f"Error exportando CSV: {exc}")
            return 3
        print(f"OK: CSV escrito en {args.csv_path} (filas={len(rows)})")
        return 0

    print_rows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

