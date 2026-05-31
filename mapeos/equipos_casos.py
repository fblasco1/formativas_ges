# -*- coding: utf-8 -*-
"""Detección de casos de nombres de equipos para revisar equipos_map.json."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import pandas as pd

from mapeos.loader import cargar_mapeo_equipos, clave_mapeo, normalizar_equipo

COLORES = {
    "AZUL", "BLANCO", "ROJO", "VERDE", "AMARILLO", "NEGRO", "MARRON", "CELESTE",
    "GRIS", "NARANJA", "VIOLETA", "ORO", "PLATA", "DORADO",
}


def club_base(nombre: str) -> str:
    n = re.sub(r"\s+", " ", nombre.upper().strip())
    n = re.sub(r"[\"'()]", "", n)
    n = re.sub(r"\s*\([A-Z]\)\s*$", "", n)
    parts = n.split()
    if len(parts) > 1 and len(parts[-1]) == 1 and parts[-1].isalpha():
        parts = parts[:-1]
    while parts and parts[-1] in COLORES:
        parts = parts[:-1]
    return " ".join(parts).strip() or n


@dataclass
class VarianteEquipo:
    nombre_raw: str
    nombre_norm: str
    partidos: int = 0
    temporadas: List[int] = field(default_factory=list)
    en_mapeo: bool = False
    destino_mapeo: Optional[str] = None


@dataclass
class CasoEquipo:
    id: str
    tipo: str
    club_base: str
    variantes: List[VarianteEquipo]
    sugerencia: Optional[str] = None
    nota: str = ""

    @property
    def n_variantes(self) -> int:
        return len(self.variantes)

    @property
    def nombres_raw(self) -> List[str]:
        return [v.nombre_raw for v in self.variantes]


def _años_en_df(df: pd.DataFrame) -> List[int]:
    if "anio" not in df.columns:
        return []
    return sorted({int(x) for x in pd.to_numeric(df["anio"], errors="coerce").dropna().unique()})


def cargar_partidos_consolidado(path: Path, sep: str = ";") -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            df = pd.read_csv(path, sep=sep, encoding=enc)
            break
        except UnicodeDecodeError:
            df = None
    else:
        df = pd.read_csv(path, sep=sep, encoding="latin-1", errors="replace")
    for col in ("local", "visitante"):
        if col not in df.columns:
            raise ValueError(f"Falta columna {col} en {path}")
    return df


def inventario_equipos(
    df: pd.DataFrame,
    mapeo: Optional[Dict[str, str]] = None,
) -> Dict[str, VarianteEquipo]:
    """Un registro por nombre tal como aparece en los CSV (local/visitante)."""
    mapeo = mapeo if mapeo is not None else cargar_mapeo_equipos()
    inv: Dict[str, VarianteEquipo] = {}

    def _registrar(nombre: str, anio: Optional[int]) -> None:
        if not isinstance(nombre, str) or not nombre.strip():
            return
        raw = nombre.strip()
        key = raw
        norm = normalizar_equipo(raw, mapeo)
        ck = clave_mapeo(raw)
        if key not in inv:
            inv[key] = VarianteEquipo(
                nombre_raw=raw,
                nombre_norm=norm,
                en_mapeo=ck in mapeo,
                destino_mapeo=mapeo.get(ck),
            )
        inv[key].partidos += 1
        if anio is not None and anio not in inv[key].temporadas:
            inv[key].temporadas.append(anio)

    for _, row in df.iterrows():
        try:
            anio = int(row["anio"]) if pd.notna(row.get("anio")) else None
        except (TypeError, ValueError):
            anio = None
        _registrar(row["local"], anio)
        _registrar(row["visitante"], anio)

    for v in inv.values():
        v.temporadas.sort()
    return inv


def detectar_casos(
    df: pd.DataFrame,
    mapeo: Optional[Dict[str, str]] = None,
    *,
    incluir_mapeados_ok: bool = False,
) -> List[CasoEquipo]:
    """
    Agrupa situaciones a revisar.

    Tipos:
      - club_varios_nombres: mismo club_base, 2+ nombres normalizados distintos
      - alias_sin_mapear: mismo club_base, varios raw, todos sin entrada en mapa
      - una_temporada: nombre en un solo año pero club_base compartido con multi-año
      - espacios_o_formato: mismo norm tras mapeo pero raw distintos (ya unificados en ranking)
    """
    mapeo = mapeo if mapeo is not None else cargar_mapeo_equipos()
    inv = inventario_equipos(df, mapeo)
    por_club: Dict[str, List[VarianteEquipo]] = {}
    for v in inv.values():
        por_club.setdefault(club_base(v.nombre_norm), []).append(v)

    casos: List[CasoEquipo] = []
    caso_id = 0

    for base, variantes in sorted(por_club.items(), key=lambda x: (-len(x[1]), x[0])):
        if len(variantes) < 2:
            continue
        variantes = sorted(variantes, key=lambda x: (-x.partidos, x.nombre_raw))
        norms = {v.nombre_norm.upper() for v in variantes}
        raws = {v.nombre_raw for v in variantes}
        años_por_var = {v.nombre_raw: set(v.temporadas) for v in variantes}
        multi = [v for v in variantes if len(v.temporadas) >= 2]
        una = [v for v in variantes if len(v.temporadas) == 1]

        if len(norms) >= 2:
            caso_id += 1
            sugerencia = max(variantes, key=lambda v: (len(v.temporadas), v.partidos)).nombre_norm
            sin_mapear = [v for v in variantes if not v.en_mapeo]
            tipo = "club_varios_nombres"
            nota = (
                f"{len(norms)} nombres normalizados distintos bajo «{base}». "
                "Puede ser varias categorías (A/B) o alias sin unificar."
            )
            if sin_mapear and len(sin_mapear) < len(variantes):
                nota += f" {len(sin_mapear)} variantes sin entrada en equipos_map."
            casos.append(
                CasoEquipo(
                    id=f"c{caso_id:04d}",
                    tipo=tipo,
                    club_base=base,
                    variantes=variantes,
                    sugerencia=sugerencia,
                    nota=nota,
                )
            )
            continue

        if len(raws) >= 2 and all(not v.en_mapeo for v in variantes):
            caso_id += 1
            sugerencia = variantes[0].nombre_norm
            casos.append(
                CasoEquipo(
                    id=f"c{caso_id:04d}",
                    tipo="alias_sin_mapear",
                    club_base=base,
                    variantes=variantes,
                    sugerencia=sugerencia,
                    nota="Varios textos crudos; ninguno está en equipos_map.json.",
                )
            )
            continue

        if una and multi:
            for v in una:
                caso_id += 1
                ref = max(multi, key=lambda x: (len(x.temporadas), x.partidos))
                casos.append(
                    CasoEquipo(
                        id=f"c{caso_id:04d}",
                        tipo="una_temporada",
                        club_base=base,
                        variantes=[v, ref],
                        sugerencia=ref.nombre_norm,
                        nota=(
                            f"«{v.nombre_raw}» solo en {v.temporadas[0] if v.temporadas else '?'}. "
                            f"¿Mapear a «{ref.nombre_norm}»?"
                        ),
                    )
                )

    if incluir_mapeados_ok:
        return casos

    # Quitar casos donde todos los raw ya mapean al mismo destino
    filtrados: List[CasoEquipo] = []
    for c in casos:
        destinos = {v.destino_mapeo or v.nombre_norm.upper() for v in c.variantes if v.en_mapeo}
        if c.tipo == "club_varios_nombres" and len(destinos) == 1 and all(v.en_mapeo for v in c.variantes):
            continue
        filtrados.append(c)
    return filtrados


def casos_a_dataframe(casos: Sequence[CasoEquipo]) -> pd.DataFrame:
    rows = []
    for c in casos:
        for v in c.variantes:
            rows.append(
                {
                    "caso_id": c.id,
                    "tipo": c.tipo,
                    "club_base": c.club_base,
                    "nombre_raw": v.nombre_raw,
                    "nombre_norm": v.nombre_norm,
                    "en_mapeo": v.en_mapeo,
                    "destino_mapeo": v.destino_mapeo or "",
                    "partidos": v.partidos,
                    "temporadas": ",".join(str(t) for t in v.temporadas),
                    "sugerencia": c.sugerencia or "",
                    "nota": c.nota,
                }
            )
    return pd.DataFrame(rows)


def exportar_casos_csv(casos: Sequence[CasoEquipo], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    casos_a_dataframe(casos).to_csv(path, index=False, encoding="utf-8-sig", sep=";")
    return path


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    import sys

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from analisis.Ranking.seasons import resolve_partidos_consolidado

    p = argparse.ArgumentParser(description="Exportar casos de mapeo de equipos a CSV.")
    p.add_argument("--input", type=Path, default=resolve_partidos_consolidado())
    p.add_argument(
        "--output",
        type=Path,
        default=Path("outputs") / "mapeo_equipos_casos.csv",
    )
    args = p.parse_args(list(argv) if argv is not None else None)
    if not args.input.is_file():
        print(f"No existe: {args.input}", file=sys.stderr)
        return 1
    df = cargar_partidos_consolidado(args.input)
    casos = detectar_casos(df)
    exportar_casos_csv(casos, args.output)
    print(f"{len(casos)} casos -> {args.output}")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main())
