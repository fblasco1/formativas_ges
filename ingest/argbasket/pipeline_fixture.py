from __future__ import annotations

import argparse

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
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []

    for comp_cat_id, categoria in COMP_CAT_ID_A_CATEGORIA.items():
        rows = get_fixture_partidos_argentina_basketball(
            comp_cat_id=comp_cat_id,
            fecha_ini=fecha_ini,
            fecha_fin=fecha_fin,
            base_url=base_url,
            incluir_horas_reales=incluir_horas_reales,
            max_horas_requests=max_horas_por_categoria,
            sleep_s_entre_horas=sleep_s_entre_horas,
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
    args = parser.parse_args()

    rows = generar_fixture_consolidado(
        fecha_ini=args.fecha_ini,
        fecha_fin=args.fecha_fin,
        base_url=args.base_url,
        incluir_horas_reales=not args.sin_horas_reales,
        max_horas_por_categoria=args.max_horas_por_categoria,
        sleep_s_entre_horas=args.sleep_horas,
    )
    write_csv(args.output, rows)
    print(f"OK: {len(rows)} filas -> {args.output}")

