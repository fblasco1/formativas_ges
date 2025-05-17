# -*- coding: utf-8 -*-
"""
Requester utility para el ETL de FEBAMBA.
Maneja solicitudes HTTP GET con retries y exponential backoff.
"""

import time
import requests
from typing import Optional

from utils.logger import get_logger

logger = get_logger("Requester")

# Configuración global
SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
)


def hacer_solicitud(
    url: str, max_intentos: int = 5, timeout: int = 30
) -> Optional[bytes]:
    """
    Realiza solicitud GET con reintentos automáticos.

    Args:
        url (str): URL a solicitar.
        max_intentos (int): Número máximo de intentos (default 5).
        timeout (int): Timeout por intento en segundos (default 30).

    Returns:
        Optional[bytes]: Contenido binario de la respuesta o None si falló.
    """
    intentos = 0

    while intentos < max_intentos:
        try:
            response = SESSION.get(url, timeout=timeout)
            response.raise_for_status()
            logger.debug(f"Solicitud exitosa a {url}")
            return response.content
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"Recurso no encontrado (404) en {url}")
                return None  # No reintentar si es 404
            else:
                logger.warning(
                    f"Error HTTP {e.response.status_code} en {url}, intento {intentos + 1}/{max_intentos}"
                )
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Excepción en solicitud a {url}: {e}, intento {intentos + 1}/{max_intentos}"
            )

        intentos += 1
        if intentos < max_intentos:
            wait_time = 2**intentos  # Exponential backoff: 2s, 4s, 8s, 16s...
            logger.info(f"Esperando {wait_time}s antes de reintentar {url}...")
            time.sleep(wait_time)
        else:
            logger.error(f"Fallaron todos los {max_intentos} intentos para {url}")

    return None
