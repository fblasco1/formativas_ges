from __future__ import annotations

import argparse
import sys

from ingest.argbasket.fixture import get_fixture_partidos_argentina_basketball
from ingest.argbasket.io import write_csv_rows


COMP_CAT_ID_A_CATEGORIA: dict[int, str] = {
    5075: "LIGA PROXIMO MASCULINO",
    5076: "JUVENILES MASCULINO",
    5077: "CADETES MASCULINO",
    5078: "INFANTILES MASCULINO",
    5079: "MINI MASCULINO",
    5080: "PRE MINI MASCULINO",
}


CONSOLIDADO_FIELDNAMES = [
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
]


def generar_fixture_consolidado(
    *,
    fecha_ini: str,
    fecha_fin: str,
    base_url: str,
    incluir_horas_reales: bool,
    max_horas_por_categoria: int,
    sleep_s_entre_horas: float,
    progress: bool = False,
    progress_cada: int = 25,
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    total_cats = len(COMP_CAT_ID_A_CATEGORIA)
    for i, (comp_cat_id, categoria) in enumerate(COMP_CAT_ID_A_CATEGORIA.items(), start=1):
        if progress:
            print(
                f"[pipeline] Categoría {i}/{total_cats}: {comp_cat_id} {categoria}",
                file=sys.stderr,
                flush=True,
            )
        rows = get_fixture_partidos_argentina_basketball(
            comp_cat_id=comp_cat_id,
            fecha_ini=fecha_ini,
            fecha_fin=fecha_fin,
            base_url=base_url,
            incluir_horas_reales=incluir_horas_reales,
            max_horas_requests=max_horas_por_categoria,
            sleep_s_entre_horas=sleep_s_entre_horas,
            progress=progress,
            progress_cada=progress_cada,
        )
        for r in rows:
            r["Categoria"] = categoria
            r["compCatId"] = str(comp_cat_id)
        out.extend(rows)

    return out


def write_csv(path: str, rows: list[dict[str, str]]) -> None:
    write_csv_rows(path, rows, CONSOLIDADO_FIELDNAMES)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fixture consolidado argentina.basketball (5075-5080) con columna Categoria"
    )
    parser.add_argument("--fecha-ini", required=True, help="YYYY-MM-DD")
    parser.add_argument("--fecha-fin", required=True, help="YYYY-MM-DD")
    parser.add_argument("--base-url", default="https://argentina.basketball")
    parser.add_argument("--output", default="fixture_consolidado.csv")
    parser.add_argument("--sin-horas-reales", action="store_true")
    parser.add_argument("--max-horas-por-categoria", type=int, default=0)
    parser.add_argument("--sleep-horas", type=float, default=0.0)
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Imprime avance por stderr (categoría y peticiones en-vivo).",
    )
    parser.add_argument(
        "--progress-cada",
        type=int,
        default=25,
        metavar="N",
        help="Cada N horas reales una línea de aviso (solo con --progress).",
    )
    args = parser.parse_args()

    if args.progress:
        print(
            f"[pipeline] Rango {args.fecha_ini} .. {args.fecha_fin} -> {args.output}",
            file=sys.stderr,
            flush=True,
        )

    rows = generar_fixture_consolidado(
        fecha_ini=args.fecha_ini,
        fecha_fin=args.fecha_fin,
        base_url=args.base_url,
        incluir_horas_reales=not args.sin_horas_reales,
        max_horas_por_categoria=args.max_horas_por_categoria,
        sleep_s_entre_horas=args.sleep_horas,
        progress=args.progress,
        progress_cada=args.progress_cada,
    )
    if args.progress:
        print(f"[pipeline] Escribiendo CSV: {len(rows)} filas...", file=sys.stderr, flush=True)
    write_csv(args.output, rows)
    print(f"OK: {len(rows)} filas -> {args.output}")

