# -*- coding: utf-8 -*-
"""
Actualización automática de la temporada activa (GES → CSV → consolidado → renivelación).

Uso manual:
  python pipelines/actualizar_temporada_activa.py
  python pipelines/actualizar_temporada_activa.py --sin-scrape   # solo reprocesar CSV local

Programación diaria: ver docs/ACTUALIZACION_DIARIA.md y scripts/actualizar_diario.ps1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from analisis.Ranking.seasons import (  # noqa: E402
    FOCUS_YEARS,
    TEMPORADA_ACTIVA,
)
from competencias.paths import consolidado_write_path, partidos_anio_path  # noqa: E402
from pipelines.scrape_competencia import scrape_anios  # noqa: E402
from utils.logger import get_logger  # noqa: E402

logger = get_logger("actualizar_temporada_activa")

LOCK_PATH = ROOT / "Data" / ".actualizacion_en_curso.lock"
ESTADO_PATH = ROOT / "Data" / "procesada" / "ultima_actualizacion.json"
LOG_DIR = ROOT / "logs"


def _contar_filas_csv(path: Path) -> int:
    if not path.is_file():
        return 0
    from utils.open_csv import leer_csv_con_encoding_detectado

    df = leer_csv_con_encoding_detectado(str(path), ";")
    return len(df)


def _adquirir_lock() -> None:
    if LOCK_PATH.is_file():
        raise RuntimeError(
            f"Ya hay una actualización en curso (lock: {LOCK_PATH}). "
            "Si falló antes, borrá ese archivo a mano."
        )
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(
        json.dumps(
            {"pid": os.getpid(), "inicio": datetime.now(timezone.utc).isoformat()},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _liberar_lock() -> None:
    if LOCK_PATH.is_file():
        LOCK_PATH.unlink(missing_ok=True)


def _scrapear_temporada(anio: int) -> int:
    resultados = scrape_anios("formativas", [anio], verbose=True)
    return int(resultados.get(anio, 0))


def _normalizar_y_consolidar(anio: int) -> None:
    from pipelines.consolidar_temporadas import consolidar
    from pipelines.normalizar_equipos import normalizar_data

    logger.info("Normalizando equipos (temporada %s)", anio)
    normalizar_data(years=(anio,), verbose=True)

    logger.info("Consolidando %s–%s", FOCUS_YEARS[0], FOCUS_YEARS[-1])
    consolidar(tuple(FOCUS_YEARS), output=consolidado_write_path("formativas"))


def _renivelacion_activa() -> None:
    from analisis.renivelacion_tiras.pipeline import actualizar_2026, cache_historico_existe

    if not cache_historico_existe():
        logger.info("Sin caché histórico; congelando 2023-2025 (solo la primera vez)")
        from analisis.renivelacion_tiras.pipeline import congelar_historico

        congelar_historico(verbose=True)

    logger.info("Actualizando ranking de tiras con partidos_%s", TEMPORADA_ACTIVA)
    actualizar_2026(verbose=True)


def _guardar_estado(
    *,
    ok: bool,
    anio: int,
    partidos_antes: int,
    partidos_despues: int,
    error: str | None = None,
) -> None:
    ESTADO_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ultima_ejecucion": datetime.now(timezone.utc).isoformat(),
        "temporada_activa": anio,
        "ok": ok,
        "partidos_antes": partidos_antes,
        "partidos_despues": partidos_despues,
        "partidos_delta": partidos_despues - partidos_antes,
        "error": error,
    }
    ESTADO_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def ejecutar(
    *,
    anio: int = TEMPORADA_ACTIVA,
    scrape: bool = True,
    renivelacion: bool = True,
) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"actualizacion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(fh)

    partidos_path = partidos_anio_path("formativas", anio)
    partidos_antes = _contar_filas_csv(partidos_path)
    partidos_despues = partidos_antes

    try:
        _adquirir_lock()
        logger.info("=== Actualización temporada %s ===", anio)

        if scrape:
            partidos_despues = _scrapear_temporada(anio)
            if partidos_despues == 0 and partidos_antes == 0:
                raise RuntimeError("No hay partidos locales ni en GES")
        else:
            partidos_despues = _contar_filas_csv(partidos_path)
            if partidos_despues == 0:
                raise FileNotFoundError(f"No existe {partidos_path}")

        _normalizar_y_consolidar(anio)

        if renivelacion:
            _renivelacion_activa()

        delta = partidos_despues - partidos_antes
        if delta > 0:
            logger.info("Partidos nuevos respecto al CSV anterior: +%s", delta)
        elif delta < 0:
            logger.info("El CSV tiene %s filas menos que antes (GES corrigió datos)", -delta)
        else:
            logger.info("Misma cantidad de filas; se reprocesó por si hubo cambios de resultado")

        _guardar_estado(
            ok=True,
            anio=anio,
            partidos_antes=partidos_antes,
            partidos_despues=partidos_despues,
        )
        logger.info("Listo. Log: %s", log_file)
        return 0

    except Exception as exc:
        logger.exception("Error en actualización: %s", exc)
        _guardar_estado(
            ok=False,
            anio=anio,
            partidos_antes=partidos_antes,
            partidos_despues=partidos_despues,
            error=str(exc),
        )
        return 1

    finally:
        _liberar_lock()
        logger.removeHandler(fh)
        fh.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Scrape GES + consolidar + renivelación para la temporada activa."
    )
    p.add_argument(
        "--anio",
        type=int,
        default=TEMPORADA_ACTIVA,
        help=f"Temporada a actualizar (default: {TEMPORADA_ACTIVA}).",
    )
    p.add_argument(
        "--sin-scrape",
        action="store_true",
        help="No consultar GES; solo normalizar/consolidar/renivelar CSV local.",
    )
    p.add_argument(
        "--sin-renivelacion",
        action="store_true",
        help="No regenerar Ranking_Tiras_Actualizado.",
    )
    args = p.parse_args(argv)
    return ejecutar(
        anio=args.anio,
        scrape=not args.sin_scrape,
        renivelacion=not args.sin_renivelacion,
    )


if __name__ == "__main__":
    raise SystemExit(main())
