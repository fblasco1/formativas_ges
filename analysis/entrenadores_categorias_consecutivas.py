# -*- coding: utf-8 -*-
"""
Entrenadores principales por club y categoría formativa, y conteo de las 63
combinaciones posibles de categorías a cargo (C(6,1)+…+C(6,6)).

Criterio de entrenador principal en (club, categoría): el que más partidos
dirigió esa categoría en ese club. Si hubo empate, gana el nombre alfabético.

Categorías base: PRE MINI, MINI, INFANTILES, CADETES, JUVENILES, LIGA PROXIMO.

Entrada:
  - PostgreSQL (--desde-db, por defecto si hay config.json y conexión OK)
  - CSV con columnas Categoria, Equipo, Entrenador (--csv, repetible).
    Para contar partidos use filas sin unificar (una por aparición en partido).

Salida (por defecto en outputs/entrenadores/):
  - entrenadores_club_categorias.csv  → Entrenador, Club, Categorias_A_Cargo
  - combinaciones_categorias.csv      → Combinacion, Cantidad, N_Categorias
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import DefaultDict, Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FECHA_INI_DEFAULT = "2026-03-01"
FECHA_FIN_DEFAULT = "2026-05-31"

CATEGORIAS_BASE: Tuple[str, ...] = (
    "PRE MINI",
    "MINI",
    "INFANTILES",
    "CADETES",
    "JUVENILES",
    "LIGA PROXIMO",
)

_RE_WS = re.compile(r"\s+")


def _norm_entrenador(s: str) -> str:
    s = (s or "").strip().upper()
    s = _RE_WS.sub(" ", s)
    # Casos tipo "APELLIDO, NOMBRE, APELLIDO, NOMBRE" (mismo nombre duplicado).
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if len(parts) >= 2 and len(set(parts)) == 1:
        s = parts[0]
    return s


def _norm_equipo(s: str) -> str:
    return (s or "").strip()


def categoria_a_base(categoria: str) -> Optional[str]:
    c = (categoria or "").strip().upper()
    if not c:
        return None
    if c.startswith("PRE MINI") or c.startswith("U9"):
        return "PRE MINI"
    if c.startswith("MINI"):
        return "MINI"
    if c.startswith("INFANTILES"):
        return "INFANTILES"
    if c.startswith("CADETES"):
        return "CADETES"
    if c.startswith("JUVENILES"):
        return "JUVENILES"
    if c.startswith("LIGA PROXIMO"):
        return "LIGA PROXIMO"
    return None


def _split_entrenadores(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    text = str(raw).strip()
    if not text:
        return []
    # "COACH1, COACH2" con apellido,nombre → no partir si hay un solo bloque APELLIDO, NOMBRE.
    if text.count(",") == 1:
        return [_norm_entrenador(text)]
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) == 2 and all(" " in p for p in parts):
        return [_norm_entrenador(text)]
    out: List[str] = []
    seen: Set[str] = set()
    for p in parts:
        n = _norm_entrenador(p)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    if not out:
        n = _norm_entrenador(text)
        if n:
            out.append(n)
    return out


def _format_combinacion(cats: Sequence[str]) -> str:
    orden = {c: i for i, c in enumerate(CATEGORIAS_BASE)}
    return ", ".join(sorted(cats, key=lambda x: orden[x]))


def generar_todas_combinaciones() -> List[Tuple[str, ...]]:
    out: List[Tuple[str, ...]] = []
    for k in range(1, len(CATEGORIAS_BASE) + 1):
        for combo in combinations(CATEGORIAS_BASE, k):
            out.append(combo)
    return out


def cargar_mapeo_equipo_club(config_path: Path) -> Dict[str, str]:
    try:
        import psycopg
    except ImportError:
        return {}

    cfg = json.loads(config_path.read_text(encoding="utf-8"))["db"]
    conn = psycopg.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        dbname=cfg["name"],
    )
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT ON (UPPER(TRIM(e.nombre)))
            e.nombre,
            c.nombre
        FROM equipos e
        JOIN clubes c ON c.club_id = e.club_id
        WHERE e.nombre IS NOT NULL AND c.nombre IS NOT NULL
        ORDER BY UPPER(TRIM(e.nombre)), e.equipo_id
        """
    )
    mapeo: Dict[str, str] = {}
    for equipo, club in cur.fetchall():
        key = _norm_equipo(equipo).upper()
        if key:
            mapeo[key] = _norm_equipo(club)
    conn.close()
    return mapeo


def _equipo_a_club(equipo: str, mapeo: Dict[str, str]) -> str:
    key = _norm_equipo(equipo).upper()
    return mapeo.get(key, _norm_equipo(equipo))


def cargar_desde_db(
    config_path: Path,
    mapeo_equipo_club: Dict[str, str],
    *,
    temporada: Optional[str] = None,
) -> List[Tuple[str, str, str]]:
    import psycopg

    cfg = json.loads(config_path.read_text(encoding="utf-8"))["db"]
    conn = psycopg.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        dbname=cfg["name"],
    )
    cur = conn.cursor()
    sql = """
        SELECT categoria, local, visitante, entrenador_local, entrenador_visitante
        FROM partidos
        WHERE categoria IS NOT NULL
    """
    params: Tuple[object, ...] = ()
    if temporada:
        sql += " AND temporada = %s"
        params = (temporada,)
    cur.execute(sql, params)
    filas: List[Tuple[str, str, str]] = []
    for cat, local, visit, ent_l, ent_v in cur.fetchall():
        cat_base = categoria_a_base(cat)
        if not cat_base:
            continue
        club_local = _equipo_a_club(local or "", mapeo_equipo_club)
        club_visit = _equipo_a_club(visit or "", mapeo_equipo_club)
        for ent in _split_entrenadores(ent_l):
            filas.append((club_local, cat_base, ent))
        for ent in _split_entrenadores(ent_v):
            filas.append((club_visit, cat_base, ent))
    conn.close()
    return filas


def cargar_desde_csv(
    paths: Sequence[str],
    mapeo_equipo_club: Dict[str, str],
) -> List[Tuple[str, str, str]]:
    filas: List[Tuple[str, str, str]] = []
    for path in paths:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                cat_base = categoria_a_base(row.get("Categoria") or "")
                if not cat_base:
                    continue
                equipo = _norm_equipo(row.get("Equipo") or "")
                if not equipo:
                    continue
                club = _equipo_a_club(equipo, mapeo_equipo_club)
                for ent in _split_entrenadores(row.get("Entrenador")):
                    filas.append((club, cat_base, ent))
    return filas


def entrenador_principal_por_club_categoria(
    apariciones: Iterable[Tuple[str, str, str]],
) -> Dict[Tuple[str, str], str]:
    conteo: Counter[Tuple[str, str, str]] = Counter(apariciones)
    por_club_cat: DefaultDict[Tuple[str, str], List[Tuple[str, int]]] = defaultdict(list)
    for (club, cat, ent), n in conteo.items():
        por_club_cat[(club, cat)].append((ent, n))

    principal: Dict[Tuple[str, str], str] = {}
    for key, candidatos in por_club_cat.items():
        candidatos.sort(key=lambda x: (-x[1], x[0]))
        principal[key] = candidatos[0][0]
    return principal


def categorias_por_entrenador_club(
    principal: Dict[Tuple[str, str], str],
) -> Dict[Tuple[str, str], Set[str]]:
    out: DefaultDict[Tuple[str, str], Set[str]] = defaultdict(set)
    for (club, cat), ent in principal.items():
        out[(ent, club)].add(cat)
    return out


def contar_combinaciones(
    por_ent_club: Dict[Tuple[str, str], Set[str]],
) -> Counter[str]:
    conteo: Counter[str] = Counter()
    for cats in por_ent_club.values():
        if not cats:
            continue
        combo = _format_combinacion(tuple(cats))
        conteo[combo] += 1
    return conteo


def analizar(
    apariciones: List[Tuple[str, str, str]],
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    principal = entrenador_principal_por_club_categoria(apariciones)
    por_ent_club = categorias_por_entrenador_club(principal)

    listado: List[Dict[str, str]] = []
    for (ent, club), cats in sorted(por_ent_club.items(), key=lambda x: (x[0][1], x[0][0])):
        listado.append(
            {
                "Entrenador": ent,
                "Club": club,
                "Categorias_A_Cargo": _format_combinacion(tuple(cats)),
            }
        )

    conteo = contar_combinaciones(por_ent_club)
    tabla: List[Dict[str, str]] = []
    for combo in generar_todas_combinaciones():
        etiqueta = _format_combinacion(combo)
        tabla.append(
            {
                "Combinacion": etiqueta,
                "Cantidad": str(conteo.get(etiqueta, 0)),
                "N_Categorias": str(len(combo)),
            }
        )
    return listado, tabla


def escribir_csv(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def extraer_apariciones_portal(
    *,
    fecha_ini: str,
    fecha_fin: str,
    out_dir: Path,
    mapeo_equipo_club: Dict[str, str],
    workers: int = 4,
) -> List[Tuple[str, str, str]]:
    from ingest.argbasket.pipeline_fixture import generar_fixture_consolidado, write_csv

    out_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = out_dir / "fixture_2026.csv"
    raw_path = out_dir / "entrenadores_raw_2026.csv"

    print(f"Descargando fixture {fecha_ini} .. {fecha_fin} (5075-5080)...", flush=True)
    rows = generar_fixture_consolidado(
        fecha_ini=fecha_ini,
        fecha_fin=fecha_fin,
        base_url="https://argentina.basketball",
        incluir_horas_reales=False,
        max_horas_por_categoria=0,
        sleep_s_entre_horas=0.0,
        progress=True,
    )
    write_csv(str(fixture_path), rows)
    print(f"Fixture: {len(rows)} filas -> {fixture_path}", flush=True)

    cmd = [
        sys.executable,
        str(ROOT / "extraer_entrenadores_partidos_2026.py"),
        "--fixture",
        str(fixture_path),
        "--out",
        str(raw_path),
        "--mantener-duplicados",
        "--fecha-ini",
        fecha_ini,
        "--fecha-fin",
        fecha_fin,
        "--workers",
        str(workers),
    ]
    print("Extrayendo entrenadores por partido...", flush=True)
    subprocess.check_call(cmd, cwd=str(ROOT))

    return cargar_desde_csv([str(raw_path)], mapeo_equipo_club)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Entrenadores principales por club y combinaciones de categorías (63 grupos)."
    )
    p.add_argument(
        "--csv",
        action="append",
        dest="csvs",
        default=[],
        help="CSV(s) Categoria,Equipo,Entrenador (repetible). Si no se usa --desde-db.",
    )
    p.add_argument(
        "--desde-db",
        action="store_true",
        help="Leer partidos desde PostgreSQL (config.json).",
    )
    p.add_argument(
        "--extraer-portal",
        action="store_true",
        help="Descargar fixture y entrenadores desde argentina.basketball (5075-5080).",
    )
    p.add_argument(
        "--fecha-ini",
        default=FECHA_INI_DEFAULT,
        help=f"Inicio inclusive del rango (YYYY-MM-DD). Por defecto: {FECHA_INI_DEFAULT}.",
    )
    p.add_argument(
        "--fecha-fin",
        default=FECHA_FIN_DEFAULT,
        help=f"Fin inclusive del rango (YYYY-MM-DD). Por defecto: {FECHA_FIN_DEFAULT}.",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Descargas concurrentes al extraer entrenadores del portal.",
    )
    p.add_argument(
        "--config",
        default=str(ROOT / "config.json"),
        help="Ruta a config.json con credenciales DB.",
    )
    p.add_argument(
        "--temporada",
        default="2026",
        help="Temporada en PostgreSQL (columna partidos.temporada). Por defecto: 2026.",
    )
    p.add_argument(
        "--out-dir",
        default=str(ROOT / "outputs" / "entrenadores"),
        help="Directorio de salida.",
    )
    args = p.parse_args()

    config_path = Path(args.config)
    usar_db = args.desde_db
    usar_portal = args.extraer_portal or (not args.csvs and not args.desde_db)
    apariciones: List[Tuple[str, str, str]] = []

    mapeo: Dict[str, str] = {}
    if config_path.is_file():
        try:
            mapeo = cargar_mapeo_equipo_club(config_path)
        except Exception as exc:
            print(f"Aviso: no se pudo cargar mapeo equipo→club: {exc}", file=sys.stderr)

    if usar_portal:
        try:
            apariciones = extraer_apariciones_portal(
                fecha_ini=args.fecha_ini,
                fecha_fin=args.fecha_fin,
                out_dir=Path(args.out_dir),
                mapeo_equipo_club=mapeo,
                workers=args.workers,
            )
        except Exception as exc:
            print(f"Error extrayendo desde portal: {exc}", file=sys.stderr)
            return 1
    elif usar_db:
        if not config_path.is_file():
            print(f"No existe {config_path}; use --csv.", file=sys.stderr)
            return 1
        try:
            apariciones = cargar_desde_db(
                config_path,
                mapeo,
                temporada=(args.temporada or None),
            )
        except Exception as exc:
            print(f"Error leyendo DB: {exc}", file=sys.stderr)
            return 1
    else:
        apariciones = cargar_desde_csv(args.csvs, mapeo)

    if not apariciones:
        print("Sin apariciones válidas (revisar categorías o fuente de datos).", file=sys.stderr)
        return 1

    listado, tabla = analizar(apariciones)
    out_dir = Path(args.out_dir)
    path_listado = out_dir / f"entrenadores_club_categorias_{args.temporada or 'todas'}.csv"
    path_tabla = out_dir / f"combinaciones_categorias_{args.temporada or 'todas'}.csv"
    escribir_csv(path_listado, listado, ["Entrenador", "Club", "Categorias_A_Cargo"])
    escribir_csv(path_tabla, tabla, ["Combinacion", "Cantidad", "N_Categorias"])

    fuente = f"portal {args.fecha_ini} .. {args.fecha_fin}" if usar_portal else (
        f"PostgreSQL (temporada {args.temporada})" if usar_db else f"{len(args.csvs)} CSV"
    )
    print(f"Fuente: {fuente}")
    print(f"Apariciones (club, categoría, entrenador): {len(apariciones):,}")
    print(f"Entrenadores con categorías a cargo: {len(listado):,}")
    print(f"Listado -> {path_listado}")
    print(f"Combinaciones (63 filas) -> {path_tabla}")
    print()
    print("Resumen por cantidad de categorías:")
    buckets: Counter[str] = Counter()
    for row in tabla:
        if int(row["Cantidad"]) > 0:
            buckets[row["N_Categorias"]] += int(row["Cantidad"])
    for k in sorted(buckets, key=int):
        print(f"  {k} categoría(s): {buckets[k]} entrenador(es)-club")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
