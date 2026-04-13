# -*- coding: utf-8 -*-
"""
Extrae metadatos anómalos y fusiona correcciones. ``extraer`` escribe ``*.manifest.json``;
si borrás filas del CSV de correcciones, ``fusionar`` elimina esas filas del base (salvo
``--no-eliminar-ausentes``). Mismo nombre base entre CSV y manifiesto; si no, ``--manifest``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd

from utils.logger import get_logger
from utils.open_csv import leer_csv_autodetect

logger = get_logger(__name__)

_COLS_META = ("fase", "ronda", "nivel", "zona", "grupo")
_VERIF = ("anio", "categoria", "fecha", "local", "visitante", "ptsL", "ptsV")
_NUM_VERIF = frozenset({"anio", "ptsL", "ptsV"})


def _contexto_coincide(base_val: object, corr_val: object, col: str) -> bool:
    """Compara celda de verificación entre CSV base y archivo de correcciones."""
    if pd.isna(base_val) and pd.isna(corr_val):
        return True
    if col in _NUM_VERIF:
        b = pd.to_numeric(base_val, errors="coerce")
        c = pd.to_numeric(corr_val, errors="coerce")
        if pd.isna(b) and pd.isna(c):
            return True
        if pd.notna(b) and pd.notna(c):
            return int(b) == int(c)
    return str(base_val).strip() == str(corr_val).strip()


def _marcar_anomalias(df: pd.DataFrame) -> pd.Series:
    """Máscara vectorizada por columna."""
    mask = pd.Series(False, index=df.index)
    for col, fem in (
        ("fase", True),
        ("ronda", True),
        ("nivel", False),
        ("zona", True),
        ("grupo", False),
    ):
        if col not in df.columns:
            continue
        s = df[col].astype(str).str.strip().str.lower()
        if fem:
            bad = s.isin(("", "nan")) | s.eq("desconocida")
        else:
            bad = s.isin(("", "nan")) | s.eq("desconocido")
        na = df[col].isna()
        mask = mask | bad | na
    return mask


def extraer_filas_a_corregir(
    ruta_entrada: Path,
    ruta_salida: Path,
    *,
    solo_anomalas: bool = True,
) -> int:
    """CSV con ``_row_idx`` + manifiesto; ``solo_anomalas`` filtra placeholders Desconocid*."""
    df = leer_csv_autodetect(str(ruta_entrada))
    df.insert(0, "_row_idx", range(len(df)))

    if solo_anomalas:
        m = _marcar_anomalias(df)
        out = df.loc[m].copy()
    else:
        out = df.copy()

    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(ruta_salida, index=False, encoding="utf-8-sig")
    n = len(out)

    indices = [int(x) for x in out["_row_idx"].tolist()]
    man_path = ruta_salida.with_name(ruta_salida.stem + ".manifest.json")
    payload = {
        "version": 1,
        "source_csv": str(ruta_entrada.resolve()),
        "row_indices": indices,
        "mode": "anomalias" if solo_anomalas else "todas_las_filas",
    }
    man_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Manifiesto (índices exportados): %s (%s filas)", man_path, len(indices))

    logger.info(
        "Escrito %s (%s filas%s)",
        ruta_salida,
        n,
        f", de {len(df)} totales" if solo_anomalas else "",
    )
    return n


def _cargar_manifest(
    ruta_explicita: Path | None,
    ruta_correcciones: Path,
) -> dict | None:
    """Lee JSON de manifiesto o ``None`` si no hay archivo (y no se pasó ruta obligatoria)."""
    if ruta_explicita is not None:
        if not ruta_explicita.is_file():
            raise FileNotFoundError(f"Manifiesto no encontrado: {ruta_explicita}")
        return json.loads(ruta_explicita.read_text(encoding="utf-8"))
    default = ruta_correcciones.with_name(ruta_correcciones.stem + ".manifest.json")
    if default.is_file():
        return json.loads(default.read_text(encoding="utf-8"))
    return None


def fusionar_correcciones(
    ruta_base: Path,
    ruta_correcciones: Path,
    ruta_salida: Path,
    *,
    strict: bool = True,
    ruta_manifest: Path | None = None,
    eliminar_ausentes: bool = True,
) -> int:
    """Actualiza metadatos por ``_row_idx``; con manifiesto y ``eliminar_ausentes``, borra
    índices exportados que ya no están en correcciones."""
    base = leer_csv_autodetect(str(ruta_base))
    corr = leer_csv_autodetect(str(ruta_correcciones))

    if "_row_idx" not in corr.columns:
        raise ValueError("El archivo de correcciones debe incluir la columna _row_idx.")

    faltan = [c for c in _COLS_META if c not in corr.columns]
    if faltan:
        raise ValueError(f"Faltan columnas en correcciones: {faltan}")

    manifest = _cargar_manifest(ruta_manifest, ruta_correcciones)
    to_remove: list[int] = []
    if eliminar_ausentes and manifest is not None:
        raw = manifest.get("row_indices")
        if not isinstance(raw, list):
            raise ValueError("Manifiesto inválido: falta row_indices (lista).")
        expected = {int(x) for x in raw}
        present = {int(x) for x in corr["_row_idx"].tolist()}
        extra = present - expected
        if extra:
            logger.warning(
                "_row_idx en correcciones que no estaban en el extract (se aplican igual): %s",
                sorted(extra)[:30],
            )
        to_remove = sorted(expected - present)
        if to_remove:
            logger.info(
                "Se eliminarán %s filas del CSV base (ausentes en correcciones tras extract)",
                len(to_remove),
            )
    elif eliminar_ausentes and manifest is None:
        logger.info("Sin manifiesto junto a %s: no se eliminan filas ausentes", ruta_correcciones)

    aplicadas = 0
    for _, row in corr.iterrows():
        idx = int(row["_row_idx"])
        if idx < 0 or idx >= len(base):
            logger.error("Índice fuera de rango: %s (filas base: %s)", idx, len(base))
            raise ValueError(f"_row_idx inválido: {idx}")

        if strict:
            for c in _VERIF:
                if c not in base.columns or c not in row.index:
                    continue
                b = base.at[idx, c]
                r = row[c]
                if not _contexto_coincide(b, r, c):
                    logger.error(
                        "Verificación falló en fila _row_idx=%s columna %s: base=%r corr=%r",
                        idx,
                        c,
                        b,
                        r,
                    )
                    raise ValueError(
                        "El CSV base no coincide con el contexto guardado en correcciones; "
                        "¿re-scrape o reordenó filas? Vuelva a generar el archivo de extraer."
                    )

        for c in _COLS_META:
            if c not in base.columns:
                base[c] = ""
            val = row[c]
            base.at[idx, c] = val if not (isinstance(val, float) and pd.isna(val)) else ""
        aplicadas += 1

    eliminadas = 0
    if to_remove:
        mask = [True] * len(base)
        for i in to_remove:
            if i < 0 or i >= len(base):
                logger.error("Índice a eliminar fuera de rango: %s", i)
                raise ValueError(f"_row_idx inválido para borrado: {i}")
            mask[i] = False
        base = base.iloc[mask].reset_index(drop=True)
        eliminadas = len(to_remove)

    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    base.to_csv(ruta_salida, index=False, encoding="utf-8-sig")
    logger.info(
        "Fusionadas %s correcciones, eliminadas %s filas → %s",
        aplicadas,
        eliminadas,
        ruta_salida,
    )
    return aplicadas


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Extrae partidos con metadatos anómalos y fusiona correcciones por _row_idx."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extraer", help="Genera CSV editable con filas a corregir")
    e.add_argument("entrada", type=Path, help="CSV de partidos (mismo esquema que el scraper)")
    e.add_argument(
        "-o",
        "--salida",
        type=Path,
        default=Path("outputs/correcciones_metadatos.csv"),
        help="Ruta del CSV intermedio (UTF-8 con BOM para Excel)",
    )
    e.add_argument(
        "--todas-las-filas",
        action="store_true",
        help="Incluir todas las filas (no solo anómalas); útil para plantilla completa",
    )

    f = sub.add_parser("fusionar", help="Aplica correcciones al CSV original")
    f.add_argument("base", type=Path, help="CSV original (mismo orden que al extraer)")
    f.add_argument("correcciones", type=Path, help="CSV editado tras extraer")
    f.add_argument(
        "-o",
        "--salida",
        type=Path,
        required=True,
        help="CSV de salida (no sobrescribe la base salvo que elija la misma ruta)",
    )
    f.add_argument(
        "--no-strict",
        action="store_true",
        help="No verificar anio/categoria/fecha/equipos/puntos antes de fusionar (riesgoso)",
    )
    f.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="JSON de manifiesto (por defecto: mismo nombre que correcciones + .manifest.json)",
    )
    f.add_argument(
        "--no-eliminar-ausentes",
        action="store_true",
        help="No borrar del CSV base las filas quitadas del archivo de correcciones",
    )
    return p


def main() -> None:
    args = _parser().parse_args()
    if args.cmd == "extraer":
        extraer_filas_a_corregir(
            args.entrada,
            args.salida,
            solo_anomalas=not args.todas_las_filas,
        )
    else:
        fusionar_correcciones(
            args.base,
            args.correcciones,
            args.salida,
            strict=not args.no_strict,
            ruta_manifest=args.manifest,
            eliminar_ausentes=not args.no_eliminar_ausentes,
        )


if __name__ == "__main__":
    main()
