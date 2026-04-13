# -*- coding: utf-8 -*-
"""
Normaliza CSV crudos → ``Data/procesada/matches_clean.parquet`` y ``matches_clean.csv``.

Equipos sin entrada útil en ``mapeos/equipos_map.json`` → ``outputs/equipos_sin_mapeo.csv``
y ``outputs/equipos_sin_mapeo.manifest.json`` (una fila por archivo y nombre).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from mapeos.loader import cargar_mapeo_equipos, normalizar_equipo
from utils.logger import get_logger
from utils.open_csv import leer_csv_autodetect

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "Data" / "raw"
PROC_DIR = PROJECT_ROOT / "Data" / "procesada"
OUT_PARQUET = PROC_DIR / "matches_clean.parquet"
OUT_CSV = PROC_DIR / "matches_clean.csv"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
LOG_EQUIPOS_SIN_MAPEO_CSV = OUTPUTS_DIR / "equipos_sin_mapeo.csv"
LOG_EQUIPOS_SIN_MAPEO_MANIFEST = OUTPUTS_DIR / "equipos_sin_mapeo.manifest.json"

_REQUERIDAS = ("local", "visitante", "categoria", "ptsL", "ptsV")

# Placeholders que no se reportan como "sin mapeo" (no son clubes).
_IGNORAR_EQUIPO_EN_LOG = frozenset({"", "LIBRE", "NAN"})


def _clave_lookup_equipo(nombre: str) -> str:
    """Misma clave que ``normalizar_equipo`` para el lookup en el mapa."""
    return nombre.upper().strip()


def _conjunto_valores_canonicos(mapeo_equipos: dict[str, str]) -> frozenset[str]:
    """Nombres canónicos ya presentes como valores del mapa (misma normalización que el lookup)."""
    return frozenset(_clave_lookup_equipo(str(v)) for v in mapeo_equipos.values())


def _equipos_sin_mapeo_filas(
    df: pd.DataFrame,
    mapeo_equipos: dict[str, str],
    valores_canonicos: frozenset[str],
    source: Path,
) -> list[dict[str, str | int]]:
    """Filas para CSV + consola: equipos sin alias ni canónico conocido en ``equipos_map.json``."""
    if "local" not in df.columns or "visitante" not in df.columns:
        return []

    nombres = pd.concat([df["local"], df["visitante"]], ignore_index=True).astype(str).str.strip()
    claves = nombres.map(_clave_lookup_equipo)
    mask = ~claves.isin(_IGNORAR_EQUIPO_EN_LOG)
    claves = claves[mask]

    counts = claves.value_counts()
    sin_mapeo: list[tuple[str, int]] = []
    for clave, cnt in counts.items():
        if clave not in mapeo_equipos and clave not in valores_canonicos:
            sin_mapeo.append((clave, int(cnt)))

    if not sin_mapeo:
        return []

    sin_mapeo.sort(key=lambda x: -x[1])
    total_filas = sum(n for _, n in sin_mapeo)
    preview = ", ".join(f"{nom} (×{n})" for nom, n in sin_mapeo[:25])
    sufijo = f" … (+{len(sin_mapeo) - 25} nombres más)" if len(sin_mapeo) > 25 else ""
    logger.warning(
        "%s: equipos sin alias ni canónico listado en equipos_map.json — %s nombres distintos, "
        "%s apariciones en local/visitante: %s%s",
        source.name,
        len(sin_mapeo),
        total_filas,
        preview,
        sufijo,
    )
    return [
        {
            "archivo": source.name,
            "nombre_normalizado": clave,
            "apariciones": cnt,
        }
        for clave, cnt in sin_mapeo
    ]


def _escribir_log_equipos_sin_mapeo(filas: list[dict[str, str | int]]) -> None:
    """Escribe CSV + manifiesto en ``outputs/`` para editar ``mapeos/equipos_map.json``."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    generado = datetime.now(timezone.utc).isoformat()
    if filas:
        df_log = pd.DataFrame(filas)
    else:
        df_log = pd.DataFrame(columns=["archivo", "nombre_normalizado", "apariciones"])

    df_log.to_csv(LOG_EQUIPOS_SIN_MAPEO_CSV, index=False, encoding="utf-8-sig")
    manifest = {
        "generado_utc": generado,
        "csv": LOG_EQUIPOS_SIN_MAPEO_CSV.relative_to(PROJECT_ROOT).as_posix(),
        "filas": len(filas),
        "nombres_distintos": len({f["nombre_normalizado"] for f in filas}),
        "nota": "Clave sugerida en JSON: nombre_normalizado → nombre canónico deseado.",
    }
    LOG_EQUIPOS_SIN_MAPEO_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(
        "Equipos sin mapear listados en %s y %s (%s filas)",
        LOG_EQUIPOS_SIN_MAPEO_CSV.name,
        LOG_EQUIPOS_SIN_MAPEO_MANIFEST.name,
        len(filas),
    )


def inferir_genero_desde_categoria(categoria: str) -> str:
    """Heurística simple: la categoría scrapeada suele ser canónica sin género → MASCULINO."""
    c = (categoria or "").upper()
    if "MIXT" in c:
        return "MIXTO"
    if any(x in c for x in ("FEMEN", "DAMAS", "FEMINA")):
        return "FEMENINO"
    return "MASCULINO"


def _enriquecer_df(df: pd.DataFrame, mapeo_equipos: dict[str, str]) -> pd.DataFrame:
    faltan = [c for c in _REQUERIDAS if c not in df.columns]
    if faltan:
        raise ValueError(f"Faltan columnas obligatorias: {faltan}")

    out = df.copy()
    out["local"] = out["local"].astype(str).map(lambda x: normalizar_equipo(x, mapeo_equipos))
    out["visitante"] = out["visitante"].astype(str).map(
        lambda x: normalizar_equipo(x, mapeo_equipos)
    )

    out["ptsL"] = pd.to_numeric(out["ptsL"], errors="coerce").fillna(0).astype(int)
    out["ptsV"] = pd.to_numeric(out["ptsV"], errors="coerce").fillna(0).astype(int)
    out["diferencia"] = (out["ptsL"] - out["ptsV"]).abs()

    out["ganador"] = out["visitante"].where(out["ptsV"] > out["ptsL"], out["local"])
    out["perdedor"] = out["local"].where(out["ptsV"] > out["ptsL"], out["visitante"])

    out["is_forfeit"] = (out["ptsL"] == 0) & (out["ptsV"] == 0)
    out["age_group"] = out["categoria"].astype(str).str.upper().str.strip()
    out["genero"] = out["categoria"].astype(str).map(inferir_genero_desde_categoria)

    mismo = out["local"] == out["visitante"]
    if mismo.any():
        logger.warning("Filas con local==visitante: %s", int(mismo.sum()))

    empate_pts = (out["ptsL"] == out["ptsV"]) & (~out["is_forfeit"])
    if empate_pts.any():
        logger.info("Partidos empatados (mismos puntos): %s", int(empate_pts.sum()))

    return out


def collect_csv_paths_from_raw() -> list[Path]:
    if not RAW_DIR.is_dir():
        return []
    return sorted(RAW_DIR.glob("*.csv"))


def collect_csv_paths_legacy_data_root() -> list[Path]:
    data = PROJECT_ROOT / "Data"
    if not data.is_dir():
        return []
    return sorted(p for p in data.glob("*.csv") if p.is_file())


def normalize_and_write(sources: list[Path]) -> None:
    if not sources:
        logger.error("No hay archivos CSV para normalizar.")
        return

    mapeo = cargar_mapeo_equipos()
    valores_canonicos = _conjunto_valores_canonicos(mapeo)
    frames: list[pd.DataFrame] = []
    filas_sin_mapeo: list[dict[str, str | int]] = []
    for path in sources:
        logger.info("Leyendo: %s", path)
        try:
            df = leer_csv_autodetect(str(path))
            filas_sin_mapeo.extend(_equipos_sin_mapeo_filas(df, mapeo, valores_canonicos, path))
            frames.append(df)
        except Exception as exc:
            logger.error("No se pudo leer %s: %s", path, exc)

    _escribir_log_equipos_sin_mapeo(filas_sin_mapeo)

    if not frames:
        logger.error("Ningún CSV válido.")
        return

    df_all = pd.concat(frames, ignore_index=True)
    try:
        df_clean = _enriquecer_df(df_all, mapeo)
    except ValueError as exc:
        logger.error("%s", exc)
        return

    PROC_DIR.mkdir(parents=True, exist_ok=True)
    df_clean.to_parquet(OUT_PARQUET, index=False)
    df_clean.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    logger.info("Escrito %s y %s (%s filas)", OUT_PARQUET, OUT_CSV, len(df_clean))


def main() -> None:
    paths = collect_csv_paths_from_raw()
    if not paths:
        logger.warning("Data/raw vacío o inexistente; no hay nada que normalizar.")
        return
    normalize_and_write(paths)


def main_legacy_flat_csv_in_data() -> None:
    """Compatibilidad: CSV sueltos en ``Data/`` (no entra ``procesada/`` por glob)."""
    paths = collect_csv_paths_legacy_data_root()
    if not paths:
        logger.warning("No hay *.csv en la raíz de Data/.")
        return
    normalize_and_write(paths)


if __name__ == "__main__":
    main()
