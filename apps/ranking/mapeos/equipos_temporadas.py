# -*- coding: utf-8 -*-
"""Cruce de nombres de equipos temporada a temporada."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

import pandas as pd

from mapeos.equipos_casos import club_base
from mapeos.loader import cargar_mapeo_equipos

from analisis.Ranking.seasons import FOCUS_YEARS
from mapeos.equipos_listado import (  # noqa: E402
    NombreEnTemporada,
    filtrar_listado,
    inventario_temporada,
    listado_por_temporada,
)


@dataclass
class CruceTemporada:
    """Un club base con cómo figura en cada año."""

    id: str
    club_base: str
    por_anio: Dict[int, List[NombreEnTemporada]] = field(default_factory=dict)
    nombres_norm: Set[str] = field(default_factory=set)
    nombres_raw: Set[str] = field(default_factory=set)
    inconsistente: bool = False
    motivo: str = ""
    sugerencia: Optional[str] = None

    def celda_anio(self, anio: int) -> str:
        items = self.por_anio.get(anio, [])
        if not items:
            return "—"
        partes = []
        for it in sorted(items, key=lambda x: -x.partidos):
            flecha = f"{it.nombre_raw} → {it.nombre_norm}"
            if it.en_mapeo:
                flecha += " [mapa]"
            partes.append(f"{flecha} ({it.partidos})")
        return " | ".join(partes)

    def anios_presentes(self) -> List[int]:
        return sorted(self.por_anio.keys())


def detectar_cruce_temporadas(
    df: pd.DataFrame,
    years: Sequence[int] = FOCUS_YEARS,
    mapeo: Optional[Dict[str, str]] = None,
) -> List[CruceTemporada]:
    """
    Agrupa por club_base del nombre normalizado y detecta cambios entre años.
    """
    mapeo = mapeo if mapeo is not None else cargar_mapeo_equipos()
    inv = inventario_temporada(df, mapeo)

    # club_base -> anio -> list NombreEnTemporada (unique by raw per year)
    grupos: Dict[str, Dict[int, Dict[str, NombreEnTemporada]]] = {}

    for item in inv.values():
        if item.anio not in years:
            continue
        base = club_base(item.nombre_norm)
        grupos.setdefault(base, {}).setdefault(item.anio, {})[item.nombre_raw] = item

    casos: List[CruceTemporada] = []
    for i, (base, por_anio_dict) in enumerate(sorted(grupos.items()), start=1):
        por_anio: Dict[int, List[NombreEnTemporada]] = {
            anio: sorted(v.values(), key=lambda x: -x.partidos)
            for anio, v in sorted(por_anio_dict.items())
        }
        norms = {it.nombre_norm for items in por_anio.values() for it in items}
        raws = {it.nombre_raw for items in por_anio.values() for it in items}
        anios = sorted(por_anio.keys())

        inconsistente = False
        motivos: List[str] = []

        if len(norms) > 1:
            inconsistente = True
            motivos.append(f"{len(norms)} nombres normalizados distintos")
        if len(raws) > 1:
            # varios textos en CSV aunque norm sea uno solo
            sin_mapa = [it for items in por_anio.values() for it in items if not it.en_mapeo]
            if sin_mapa or len(norms) > 1:
                inconsistente = True
                motivos.append(f"{len(raws)} textos crudos en distintas temporadas")

        # distinto raw año a año (mismo club_base)
        if len(anios) >= 2:
            principal_raw_por_anio = []
            for anio in anios:
                items = por_anio[anio]
                principal_raw_por_anio.append(items[0].nombre_raw)
            if len(set(principal_raw_por_anio)) > 1 and len(norms) <= 1:
                inconsistente = True
                motivos.append("cambia el texto en CSV entre años (mapeo ya unifica)")
            elif len(set(principal_raw_por_anio)) > 1:
                inconsistente = True
                motivos.append("cambia el texto en CSV entre años")

        todos = [it for items in por_anio.values() for it in items]
        by_partidos: Dict[str, int] = {}
        for it in todos:
            by_partidos[it.nombre_norm] = by_partidos.get(it.nombre_norm, 0) + it.partidos
        sugerencia = max(by_partidos.items(), key=lambda x: x[1])[0]

        casos.append(
            CruceTemporada(
                id=f"t{i:04d}",
                club_base=base,
                por_anio=por_anio,
                nombres_norm=norms,
                nombres_raw=raws,
                inconsistente=inconsistente,
                motivo="; ".join(motivos) if motivos else "OK",
                sugerencia=sugerencia,
            )
        )

    return casos


def cruce_a_dataframe(casos: Sequence[CruceTemporada], years: Sequence[int] = FOCUS_YEARS) -> pd.DataFrame:
    rows = []
    for c in casos:
        row = {
            "id": c.id,
            "club_base": c.club_base,
            "inconsistente": c.inconsistente,
            "motivo": c.motivo,
            "sugerencia": c.sugerencia or "",
            "n_norm_distintos": len(c.nombres_norm),
            "n_raw_distintos": len(c.nombres_raw),
            "anios": ",".join(str(a) for a in c.anios_presentes()),
        }
        for y in years:
            row[str(y)] = c.celda_anio(y)
        rows.append(row)
    return pd.DataFrame(rows)


def filtrar_cruce(
    casos: Sequence[CruceTemporada],
    *,
    solo_inconsistentes: bool = True,
    min_anios: int = 2,
    buscar: str = "",
) -> List[CruceTemporada]:
    out = list(casos)
    if solo_inconsistentes:
        out = [c for c in out if c.inconsistente]
    if min_anios > 1:
        out = [c for c in out if len(c.anios_presentes()) >= min_anios]
    if buscar.strip():
        q = buscar.strip().upper()
        out = [
            c
            for c in out
            if q in c.club_base.upper()
            or any(q in r.upper() for r in c.nombres_raw)
            or any(q in n.upper() for n in c.nombres_norm)
        ]
    return out


def exportar_cruce_csv(casos: Sequence[CruceTemporada], path: Path, years: Sequence[int] = FOCUS_YEARS) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    cruce_a_dataframe(casos, years).to_csv(path, index=False, encoding="utf-8-sig", sep=";")
    return path


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    import sys

    from analisis.Ranking.seasons import PARTIDOS_CONSOLIDADO
    from mapeos.equipos_casos import cargar_partidos_consolidado

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    p = argparse.ArgumentParser(description="Exportar cruce de equipos por temporada.")
    p.add_argument("--input", type=Path, default=PARTIDOS_CONSOLIDADO)
    p.add_argument("--output", type=Path, default=Path("outputs") / "mapeo_cruce_temporadas.csv")
    p.add_argument("--solo-inconsistentes", action="store_true")
    args = p.parse_args(list(argv) if argv is not None else None)

    if not args.input.is_file():
        print(f"No existe: {args.input}", file=sys.stderr)
        return 1

    df = cargar_partidos_consolidado(args.input)
    casos = detectar_cruce_temporadas(df)
    if args.solo_inconsistentes:
        casos = filtrar_cruce(casos, solo_inconsistentes=True, min_anios=2)
    exportar_cruce_csv(casos, args.output)
    print(f"{len(casos)} filas -> {args.output}")
    return 0


__all__ = [
    "CruceTemporada",
    "NombreEnTemporada",
    "cruce_a_dataframe",
    "detectar_cruce_temporadas",
    "exportar_cruce_csv",
    "filtrar_cruce",
    "filtrar_listado",
    "inventario_temporada",
    "listado_por_temporada",
]


if __name__ == "__main__":
    import sys

    raise SystemExit(main())
