# -*- coding: utf-8 -*-
"""
Descarga /liga-federal/partido/estadisticas/ por partido y exporta CSV estándar:
  Categoria, Equipo, Entrenador.

Por defecto se ordena (Equipo, luego categoría LIGA PROXIMO…MINI) y se **unifica**:
una sola fila por combinación (Categoria, Equipo, Entrenador), sin duplicados.
Las filas sin nombre de entrenador se descartan salvo que uses ``--mantener-sin-entrenador``.
Use ``--mantener-duplicados`` para conservar una fila por aparición en partidos.

Filtra por año en ``Fecha_Programada`` (por defecto 2026). Reutiliza HTML por
``id_partido_token`` para no repetir requests si el fixture trae filas duplicadas.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Dict, Iterable, List, Optional, Tuple

import requests

from ingest.argbasket.partido import fetch_partido_estadisticas_html, parse_equipo_entrenadores_estadisticas_html

# Orden de categoría (PRE MINI antes que MINI por el prefijo; SUPERIOR primero).
_CATEGORIA_PREFIJOS_ORDEN: Tuple[str, ...] = (
    "SUPERIOR",
    "LIGA PROXIMO",
    "JUVENILES",
    "CADETES",
    "INFANTILES",
    "PRE MINI",
    "MINI",
)


def _categoria_sort_index(categoria: str) -> int:
    c = (categoria or "").strip().upper()
    for i, pref in enumerate(_CATEGORIA_PREFIJOS_ORDEN):
        if c.startswith(pref.upper()):
            return i
    return len(_CATEGORIA_PREFIJOS_ORDEN)


def ordenar_filas_entrenadores(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Orden estable: Equipo (A-Z), luego categoría según ``_CATEGORIA_PREFIJOS_ORDEN``."""
    fn = _fieldnames()

    def key(r: Dict[str, str]) -> Tuple[str, int, str, str]:
        eq = (r.get("Equipo") or "").strip().upper()
        cat = (r.get("Categoria") or "").strip()
        ent = (r.get("Entrenador") or "").strip().upper()
        return (eq, _categoria_sort_index(cat), cat.upper(), ent)

    return sorted(rows, key=key)


def _clave_unificacion(r: Dict[str, str]) -> Tuple[str, str, str]:
    """Clave insensible a mayúsculas para detectar filas repetidas."""
    c = (r.get("Categoria") or "").strip().upper()
    e = (r.get("Equipo") or "").strip().upper()
    t = (r.get("Entrenador") or "").strip().upper()
    return (c, e, t)


def unificar_filas_entrenadores(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Una fila por (Categoria, Equipo, Entrenador), conservando la primera aparición
    (texto con el mismo formato que traía esa fila). ``rows`` debe estar ya ordenado
    si se desea salida ordenada.
    """
    fn = _fieldnames()
    seen: set[Tuple[str, str, str]] = set()
    out: List[Dict[str, str]] = []
    for r in rows:
        key = _clave_unificacion(r)
        if key in seen:
            continue
        seen.add(key)
        out.append({k: (r.get(k) or "").strip() for k in fn})
    return out


def _postprocesar_filas_entrenadores(
    rows: List[Dict[str, str]],
    *,
    mantener_duplicados: bool,
    mantener_sin_entrenador: bool = False,
) -> List[Dict[str, str]]:
    ordered = ordenar_filas_entrenadores(rows)
    if mantener_duplicados:
        out = ordered
    else:
        out = unificar_filas_entrenadores(ordered)
    if not mantener_sin_entrenador:
        out = [r for r in out if (r.get("Entrenador") or "").strip()]
    return out


def _year_from_fecha_programada(s: str) -> Optional[int]:
    d = _date_from_fecha_programada(s)
    return d.year if d else None


def _date_from_fecha_programada(s: str) -> Optional[date]:
    s = (s or "").strip()
    if not s:
        return None
    part = s.split()[0]
    bits = part.split("/")
    if len(bits) >= 3 and bits[0].isdigit() and bits[1].isdigit() and bits[2].isdigit():
        return date(int(bits[2]), int(bits[1]), int(bits[0]))
    return None


def _parse_iso_date(s: str) -> Optional[date]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _fecha_en_rango(
    fecha_programada: str,
    *,
    fecha_ini: Optional[date],
    fecha_fin: Optional[date],
) -> bool:
    d = _date_from_fecha_programada(fecha_programada)
    if d is None:
        return False
    if fecha_ini and d < fecha_ini:
        return False
    if fecha_fin and d > fecha_fin:
        return False
    return True


def _filtrar_fixture_por_fecha(
    rows: List[Dict[str, str]],
    *,
    year: Optional[int],
    fecha_ini: Optional[date],
    fecha_fin: Optional[date],
) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for r in rows:
        fp = r.get("Fecha_Programada") or ""
        if fecha_ini or fecha_fin:
            if not _fecha_en_rango(fp, fecha_ini=fecha_ini, fecha_fin=fecha_fin):
                continue
        elif year is not None and _year_from_fecha_programada(fp) != year:
            continue
        tok = (r.get("id_partido_token") or "").strip()
        if not tok:
            continue
        out.append(r)
    return out


def _load_fixture_rows(path: str) -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _fieldnames() -> List[str]:
    return ["Categoria", "Equipo", "Entrenador"]


def _rows_for_html(
    row: Dict[str, str],
    html: str,
) -> List[Dict[str, str]]:
    bloques = parse_equipo_entrenadores_estadisticas_html(html)
    categoria = (row.get("Categoria") or "").strip()
    out: List[Dict[str, str]] = []
    for b in bloques:
        equipo = str(b.get("nombre") or "").strip()
        coaches = b.get("entrenadores")
        if not isinstance(coaches, list):
            coaches = []
        if not coaches:
            out.append({"Categoria": categoria, "Equipo": equipo, "Entrenador": ""})
            continue
        for ent in coaches:
            out.append(
                {
                    "Categoria": categoria,
                    "Equipo": equipo,
                    "Entrenador": str(ent).strip(),
                }
            )
    return out


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


def main(argv: Optional[Iterable[str]] = None) -> int:
    p = argparse.ArgumentParser(description="CSV Equipo / Categoría / Entrenador desde estadísticas 2026.")
    p.add_argument(
        "--fixture",
        default="fixture_consolidado.csv",
        help="CSV con columnas id_partido_token, Categoria, Fecha_Programada, URL_Estadisticas, ...",
    )
    p.add_argument("--out", default="entrenadores_partidos_2026.csv", help="Ruta del CSV de salida.")
    p.add_argument("--year", type=int, default=0, help="Filtrar por año en Fecha_Programada (DD/MM/AAAA). 0=sin filtro por año.")
    p.add_argument("--fecha-ini", default="", help="Filtro inclusive YYYY-MM-DD en Fecha_Programada.")
    p.add_argument("--fecha-fin", default="", help="Filtro inclusive YYYY-MM-DD en Fecha_Programada.")
    p.add_argument("--base-url", default="https://argentina.basketball", help="Origen del portal.")
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("--workers", type=int, default=4, help="Descargas concurrentes por token distinto.")
    p.add_argument("--sleep", type=float, default=0.0, help="Pausa en segundos tras cada request (secuencial implícito si workers=1).")
    p.add_argument(
        "--limite",
        type=int,
        default=0,
        help="Si > 0, solo descarga los primeros N id_partido_token distintos (prueba).",
    )
    p.add_argument(
        "--solo-reordenar",
        action="store_true",
        help="Solo ordena un CSV ya generado (Categoria, Equipo, Entrenador); no descarga el portal.",
    )
    p.add_argument(
        "--entrada",
        default="entrenadores_partidos_2026.csv",
        help="CSV de entrenadores de entrada cuando se usa --solo-reordenar.",
    )
    p.add_argument(
        "--mantener-duplicados",
        action="store_true",
        help="No unificar: conserva una fila por cada aparición (p. ej. por partido).",
    )
    p.add_argument(
        "--mantener-sin-entrenador",
        action="store_true",
        help="Conservar filas con Entrenador vacío (por defecto se eliminan).",
    )
    args = p.parse_args(list(argv) if argv is not None else None)

    if args.solo_reordenar:
        try:
            raw = _load_fixture_rows(args.entrada)
        except OSError as e:
            print(f"No se pudo leer {args.entrada}: {e}", file=sys.stderr)
            return 1
        out_rows = _postprocesar_filas_entrenadores(
            raw,
            mantener_duplicados=args.mantener_duplicados,
            mantener_sin_entrenador=args.mantener_sin_entrenador,
        )
        fn = _fieldnames()
        with open(args.out, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fn)
            w.writeheader()
            for row in out_rows:
                w.writerow({k: row.get(k, "") for k in fn})
        modo = "orden+unificado" if not args.mantener_duplicados else "solo orden"
        print(f"Filas ({modo}): {len(out_rows)} -> {args.out}")
        return 0

    try:
        all_rows = _load_fixture_rows(args.fixture)
    except OSError as e:
        print(f"No se pudo leer {args.fixture}: {e}", file=sys.stderr)
        return 1

    fecha_ini = _parse_iso_date(args.fecha_ini)
    fecha_fin = _parse_iso_date(args.fecha_fin)
    year = args.year if args.year > 0 else None
    if not fecha_ini and not fecha_fin and year is None:
        year = 2026
    work = _filtrar_fixture_por_fecha(
        all_rows,
        year=year,
        fecha_ini=fecha_ini,
        fecha_fin=fecha_fin,
    )

    tokens_order: List[str] = []
    seen_tok: set[str] = set()
    for r in work:
        t = (r.get("id_partido_token") or "").strip()
        if t not in seen_tok:
            seen_tok.add(t)
            tokens_order.append(t)
            if args.limite and len(tokens_order) >= args.limite:
                break

    allow = set(tokens_order)
    work = [r for r in work if (r.get("id_partido_token") or "").strip() in allow]

    html_by_token: Dict[str, str] = {}
    if args.workers <= 1:
        session = requests.Session()
        for i, tok in enumerate(tokens_order):
            _, html = _fetch_one(session, tok, base_url=args.base_url, timeout_s=args.timeout)
            if html:
                html_by_token[tok] = html
            if args.sleep > 0:
                time.sleep(args.sleep)
            if (i + 1) % 50 == 0:
                print(f"Descargados {i + 1}/{len(tokens_order)} partidos unicos...", flush=True)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {}
            for tok in tokens_order:
                sess = requests.Session()
                futures[ex.submit(_fetch_one, sess, tok, base_url=args.base_url, timeout_s=args.timeout)] = tok
            for fut in as_completed(futures):
                tok, html = fut.result()
                if html:
                    html_by_token[tok] = html

    out_rows: List[Dict[str, str]] = []
    for r in work:
        tok = (r.get("id_partido_token") or "").strip()
        html = html_by_token.get(tok)
        if not html:
            continue
        out_rows.extend(_rows_for_html(r, html))

    out_rows = _postprocesar_filas_entrenadores(
        out_rows,
        mantener_duplicados=args.mantener_duplicados,
        mantener_sin_entrenador=args.mantener_sin_entrenador,
    )

    fn = _fieldnames()
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fn)
        w.writeheader()
        for row in out_rows:
            w.writerow({k: row.get(k, "") for k in fn})

    sufijo = " (con duplicados)" if args.mantener_duplicados else " (unificado)"
    rango = ""
    if fecha_ini or fecha_fin:
        rango = f"{args.fecha_ini or '…'} .. {args.fecha_fin or '…'}"
    elif year is not None:
        rango = str(year)
    print(
        f"Filas escritas{sufijo}: {len(out_rows)} -> {args.out} "
        f"(partidos en rango {rango}: {len(work)}, tokens unicos: {len(tokens_order)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
