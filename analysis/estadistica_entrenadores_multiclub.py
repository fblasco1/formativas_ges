# -*- coding: utf-8 -*-
"""
Estadísticas desde un CSV Categoria, Equipo, Entrenador:

  - Cantidad de entrenadores distintos (nombre normalizado).
  - Por vínculo entrenador + club: cuántas categorías distintas dirige en ese club
    (1 / 2 / 3 o más).
  - Por entrenador: trabaja en 1 solo club vs 2 o más clubes.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import DefaultDict, Dict, List, Set, Tuple


def _norm_entrenador(s: str) -> str:
    s = (s or "").strip().upper()
    s = re.sub(r"\s+", " ", s)
    return s


def _norm_equipo(s: str) -> str:
    return (s or "").strip()


def cargar_pares_categorias(path: str) -> Tuple[int, DefaultDict[Tuple[str, str], Set[str]]]:
    """
    Por cada par (entrenador, club) acumula el conjunto de categorías en las que dirige
    en ese club.
    """
    por_par: DefaultDict[Tuple[str, str], Set[str]] = defaultdict(set)
    n_filas = 0
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            ent = _norm_entrenador(row.get("Entrenador") or "")
            eq = _norm_equipo(row.get("Equipo") or "")
            cat = (row.get("Categoria") or "").strip()
            if not ent or not eq or not cat:
                continue
            n_filas += 1
            por_par[(ent, eq)].add(cat)
    return n_filas, por_par


@dataclass(frozen=True)
class EstadisticaEntrenadores:
    archivo: str
    filas_csv: int
    entrenadores_distintos: int
    vinculos_1_cat: int
    vinculos_2_cat: int
    vinculos_3_o_mas: int
    total_vinculos: int
    entrenadores_1_club: int
    entrenadores_2_o_mas_clubes: int


def calcular_estadisticas(path: str) -> EstadisticaEntrenadores:
    n_filas, por_par = cargar_pares_categorias(path)

    n_una_cat = sum(1 for cats in por_par.values() if len(cats) == 1)
    n_dos_cat = sum(1 for cats in por_par.values() if len(cats) == 2)
    n_tres_o_mas = sum(1 for cats in por_par.values() if len(cats) >= 3)
    n_vinculos = len(por_par)

    clubes_por_ent: DefaultDict[str, Set[str]] = defaultdict(set)
    for (ent, eq) in por_par:
        clubes_por_ent[ent].add(eq)

    total_entrenadores = len(clubes_por_ent)
    n_un_solo_club = sum(1 for cl in clubes_por_ent.values() if len(cl) == 1)
    n_dos_o_mas_clubes = sum(1 for cl in clubes_por_ent.values() if len(cl) >= 2)

    return EstadisticaEntrenadores(
        archivo=path,
        filas_csv=n_filas,
        entrenadores_distintos=total_entrenadores,
        vinculos_1_cat=n_una_cat,
        vinculos_2_cat=n_dos_cat,
        vinculos_3_o_mas=n_tres_o_mas,
        total_vinculos=n_vinculos,
        entrenadores_1_club=n_un_solo_club,
        entrenadores_2_o_mas_clubes=n_dos_o_mas_clubes,
    )


def formatear_informe(e: EstadisticaEntrenadores) -> str:
    lines = [
        f"Archivo: {e.archivo}",
        f"Filas CSV usadas (entrenador, club y categoria no vacios): {e.filas_csv}",
        "",
        f"ENTRENADORES DISTINTOS: {e.entrenadores_distintos}",
        "",
        "Entrenador que dirige en un mismo club — cantidad de VINCULOS (entrenador+club)",
        "segun categorias distintas en ese club:",
        f"      1 categoria:     {e.vinculos_1_cat}",
        f"      2 categorias:    {e.vinculos_2_cat}",
        f"      3 o mas:         {e.vinculos_3_o_mas}",
        f"  (total vinculos:   {e.total_vinculos})",
    ]
    if e.vinculos_1_cat + e.vinculos_2_cat + e.vinculos_3_o_mas != e.total_vinculos:
        lines.append("  [advertencia: suma de buckets != total vinculos]")
    lines.extend(
        [
            "",
            "Entrenador que trabaja en:",
            f"      1 solo club:     {e.entrenadores_1_club}",
            f"      2 o mas clubs:   {e.entrenadores_2_o_mas_clubes}",
        ]
    )
    if e.entrenadores_1_club + e.entrenadores_2_o_mas_clubes != e.entrenadores_distintos:
        lines.append("  [advertencia: suma != total entrenadores]")
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="entrenadores_partidos_2026.csv")
    p.add_argument(
        "--informe",
        default="",
        help="Si se indica, escribe el texto del informe en este archivo (UTF-8).",
    )
    args = p.parse_args()

    e = calcular_estadisticas(args.csv)
    texto = formatear_informe(e)
    print(texto, end="")
    if args.informe:
        with open(args.informe, "w", encoding="utf-8") as f:
            f.write(texto)
        print(f"(Informe guardado en {args.informe})", flush=True)


if __name__ == "__main__":
    main()
