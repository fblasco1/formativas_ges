from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple


CSV_HEADER: Sequence[str] = (
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


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


@dataclass(frozen=True)
class Flags:
    missing_pts: bool
    missing_hora_inicio: bool
    missing_hora_fin: bool
    marcador_raro: bool

    def any(self) -> bool:
        return self.missing_pts or self.missing_hora_inicio or self.missing_hora_fin or self.marcador_raro


def _marcador_raro(pl: Optional[int], pv: Optional[int]) -> bool:
    """
    Casos pedidos:
    - 0 - 0
    - 0 - 20
    - 20 - 0
    - 20 - <vacío> o <vacío> - 20 (tokens incompletos)
    """
    if pl is None and pv is None:
        return False
    if pl == 0 and pv == 0:
        return True
    if pl == 0 and pv == 20:
        return True
    if pl == 20 and pv == 0:
        return True
    if pl == 20 and pv is None:
        return True
    if pv == 20 and pl is None:
        return True
    return False


def _flags_for_row(r: Dict[str, str]) -> Flags:
    pl = _to_int(r.get("PTS_LOCAL"))
    pv = _to_int(r.get("PTS_VISITANTE"))
    missing_pts = pl is None or pv is None
    missing_hora_inicio = _is_blank(r.get("hora_inicio_partido"))
    missing_hora_fin = _is_blank(r.get("hora_fin_partido"))
    marcador_raro = _marcador_raro(pl, pv)
    return Flags(
        missing_pts=missing_pts,
        missing_hora_inicio=missing_hora_inicio,
        missing_hora_fin=missing_hora_fin,
        marcador_raro=marcador_raro,
    )


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(
        description=(
            "Filtra partidos problemáticos desde fixture_consolidado*.csv: "
            "sin puntos, sin horas, o marcador raro (0-0, 0-20, 20-0, 20-)."
        )
    )
    p.add_argument(
        "--csv",
        default="fixture_consolidado.desde_bd.csv",
        help="CSV de entrada (ej: fixture_consolidado.desde_bd.csv).",
    )
    p.add_argument(
        "--out",
        default="fixture_consolidado.filtrado.csv",
        help="CSV de salida con filas que matchean algún criterio.",
    )
    p.add_argument(
        "--motivo",
        choices=["cualquiera", "sin_pts", "sin_inicio", "sin_fin", "marcador_raro"],
        default="cualquiera",
        help="Filtrar por un motivo específico o cualquiera.",
    )
    args = p.parse_args()

    total = 0
    kept = 0
    cnt_missing_pts = 0
    cnt_missing_inicio = 0
    cnt_missing_fin = 0
    cnt_marcador_raro = 0

    out_rows: List[Dict[str, str]] = []

    with open(args.csv, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            r = {k: (row.get(k) or "").strip() for k in CSV_HEADER}
            flags = _flags_for_row(r)

            if flags.missing_pts:
                cnt_missing_pts += 1
            if flags.missing_hora_inicio:
                cnt_missing_inicio += 1
            if flags.missing_hora_fin:
                cnt_missing_fin += 1
            if flags.marcador_raro:
                cnt_marcador_raro += 1

            if args.motivo == "sin_pts":
                ok = flags.missing_pts
            elif args.motivo == "sin_inicio":
                ok = flags.missing_hora_inicio
            elif args.motivo == "sin_fin":
                ok = flags.missing_hora_fin
            elif args.motivo == "marcador_raro":
                ok = flags.marcador_raro
            else:
                ok = flags.any()

            if not ok:
                continue

            # Anexamos columnas auxiliares al final (sin romper el formato principal).
            r_out = dict(r)
            r_out["_missing_pts"] = "1" if flags.missing_pts else "0"
            r_out["_missing_inicio"] = "1" if flags.missing_hora_inicio else "0"
            r_out["_missing_fin"] = "1" if flags.missing_hora_fin else "0"
            r_out["_marcador_raro"] = "1" if flags.marcador_raro else "0"
            out_rows.append(r_out)
            kept += 1

    out_header = list(CSV_HEADER) + [
        "_missing_pts",
        "_missing_inicio",
        "_missing_fin",
        "_marcador_raro",
    ]
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_header)
        w.writeheader()
        w.writerows(out_rows)

    print(
        json.dumps(
            {
                "csv_in": args.csv,
                "csv_out": args.out,
                "total_rows": total,
                "kept_rows": kept,
                "filter_motivo": args.motivo,
                "counts_overall": {
                    "missing_pts": cnt_missing_pts,
                    "missing_hora_inicio": cnt_missing_inicio,
                    "missing_hora_fin": cnt_missing_fin,
                    "marcador_raro": cnt_marcador_raro,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

