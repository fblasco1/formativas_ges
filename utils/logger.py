# -*- coding: utf-8 -*-
"""
Configuración de Logger para todo el proyecto FEBAMBA ETL.
"""

import logging


def get_logger(name: str, level=logging.INFO) -> logging.Logger:
    """
    Crea y configura un logger estándar.

    Args:
        name (str): Nombre del logger.
        level (logging level): Nivel de logeo (por defecto INFO).

    Returns:
        logging.Logger: Logger configurado.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        ch = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    return logger
