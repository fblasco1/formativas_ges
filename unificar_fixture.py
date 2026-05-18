from __future__ import annotations

import csv
import json
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


BD_CSV_DEFAULT = "fixture_consolidado.desde_bd.csv"
CSV_2026_DEFAULT = "fixture_consolidado.csv"
OUT_DEFAULT = "fixture_consolidado.unificado.csv"


HEADER_WITH_URL: Sequence[str] = (
    "compCatId",
    "Categoria",
    "id_partido_token",
    "Local",
    "Visitante",
    "PTS_LOCAL",
    "PTS_VISITANTE",
    "DIF_PTS",
    "Fecha_Programada",
    "hora_inicio_partido",
    "hora_fin_partido",
    "URL_Estadisticas",
)


HEADER_NO_URL: Sequence[str] = tuple([h for h in HEADER_WITH_URL if h != "URL_Estadisticas"])


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if not s:
        return None
    if s.lstrip("-").isdigit():
        return int(s)
    return None


def _blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _row_key(r: Dict[str, str]) -> Optional[Tuple[int, str]]:
    comp = _to_int(r.get("compCatId"))
    token = (r.get("id_partido_token") or "").strip()
    if comp is None or not token:
        return None
    return (comp, token)


def _marcador_raro(pl: Optional[int], pv: Optional[int]) -> bool:
    # Solo los raros que pediste explícitamente
    return (pl == 0 and pv == 0) or (pl == 20 and pv == 0) or (pl == 0 and pv == 20)


def _read_csv(path: str) -> Iterable[Dict[str, str]]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield {k: (row.get(k) or "").strip() for k in row.keys()}


def _normalize_row_with_url(r: Dict[str, str]) -> Dict[str, str]:
    # Asegurar que existan todas las columnas esperadas
    out: Dict[str, str] = {}
    for h in HEADER_WITH_URL:
        out[h] = (r.get(h) or "").strip()
    return out


def _drop_url_column(r: Dict[str, str]) -> Dict[str, str]:
    return {h: (r.get(h) or "").strip() for h in HEADER_NO_URL}


def _filter_bd_row(r: Dict[str, str]) -> Tuple[bool, Dict[str, str]]:
    """
    Filtrado pedido sobre fixture_consolidado.desde_bd.csv:
    - eliminar marcadores raros (0-0, 20-0, 0-20)
    - eliminar si falta hora_inicio_partido y/o hora_fin_partido
    """
    rr = _normalize_row_with_url(r)
    pl = _to_int(rr.get("PTS_LOCAL"))
    pv = _to_int(rr.get("PTS_VISITANTE"))
    if _marcador_raro(pl, pv):
        return (False, rr)
    if _blank(rr.get("hora_inicio_partido")) or _blank(rr.get("hora_fin_partido")):
        return (False, rr)
    return (True, rr)


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(
        description=(
            "Unifica fixture_consolidado.desde_bd.csv (filtrado) con fixture_consolidado.csv (2026) "
            "eliminando la columna URL_Estadisticas."
        )
    )
    p.add_argument("--bd", default=BD_CSV_DEFAULT, help="CSV desde BD (fixture_consolidado.desde_bd.csv).")
    p.add_argument("--csv-2026", default=CSV_2026_DEFAULT, help="CSV 2026 (fixture_consolidado.csv).")
    p.add_argument("--out", default=OUT_DEFAULT, help="CSV unificado de salida.")
    p.add_argument(
        "--progress",
        action="store_true",
        help="Imprime avance por stderr al leer y escribir.",
    )
    args = p.parse_args()

    def _log(msg: str) -> None:
        if args.progress:
            print(msg, file=sys.stderr, flush=True)

    # 1) Cargar 2026 como fuente prioritaria y sin URL
    _log(f"[unificar] Leyendo CSV 2026: {args.csv_2026}")
    base_2026: Dict[Tuple[int, str], Dict[str, str]] = {}
    cnt_2026 = 0
    for row in _read_csv(args.csv_2026):
        cnt_2026 += 1
        rr = _normalize_row_with_url(row)
        key = _row_key(rr)
        if key is None:
            continue
        base_2026[key] = _drop_url_column(rr)

    _log(f"[unificar] CSV 2026: {cnt_2026} filas leídas, {len(base_2026)} claves únicas (compCatId+token).")

    # 2) Cargar BD filtrada y sumar solo keys que no estén en 2026
    _log(f"[unificar] Leyendo BD: {args.bd}")
    appended_from_bd = 0
    removed_rare = 0
    removed_missing_hours = 0
    cnt_bd_total = 0
    kept_bd = 0

    for row in _read_csv(args.bd):
        cnt_bd_total += 1
        ok, rr = _filter_bd_row(row)
        if not ok:
            pl = _to_int(rr.get("PTS_LOCAL"))
            pv = _to_int(rr.get("PTS_VISITANTE"))
            if _marcador_raro(pl, pv):
                removed_rare += 1
            elif _blank(rr.get("hora_inicio_partido")) or _blank(rr.get("hora_fin_partido")):
                removed_missing_hours += 1
            continue
        kept_bd += 1
        key = _row_key(rr)
        if key is None:
            continue
        if key in base_2026:
            continue
        base_2026[key] = _drop_url_column(rr)
        appended_from_bd += 1

    _log(
        f"[unificar] BD: total {cnt_bd_total}, tras filtro {kept_bd}, "
        f"añadidas al merge {appended_from_bd} (no estaban en 2026)."
    )

    # 3) Escribir salida
    out_rows = list(base_2026.values())
    # Orden determinista: compCatId, fecha_programada, token
    def sort_key(r: Dict[str, str]) -> Tuple[int, str, str]:
        return (_to_int(r.get("compCatId")) or 0, r.get("Fecha_Programada") or "", r.get("id_partido_token") or "")

    out_rows.sort(key=sort_key)

    _log(f"[unificar] Escribiendo {len(out_rows)} filas -> {args.out}")
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(HEADER_NO_URL))
        w.writeheader()
        w.writerows(out_rows)

    print(
        json.dumps(
            {
                "csv_2026_in_rows": cnt_2026,
                "bd_in_rows": cnt_bd_total,
                "bd_kept_after_filter": kept_bd,
                "bd_removed_rare": removed_rare,
                "bd_removed_missing_hours": removed_missing_hours,
                "appended_from_bd": appended_from_bd,
                "out_rows": len(out_rows),
                "out": args.out,
                "url_column_removed": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

