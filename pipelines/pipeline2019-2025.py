import os
import sys
from datetime import date

import pandas as pd

# Agregar el directorio raíz del proyecto al sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.scraper import FebambaScraper
from utils.logger import get_logger

logger = get_logger("pipeline2019-2025")

# Lista de torneos a scrapear
torneos_a_scrapear = [
    #{
    #    "id": 16,
    #    "url": "https://competicionescabb.gesdeportiva.es/competicion.aspx?competencia=16",
    #    "Anio": 2019,
    #    "torneo": "Torneo Formativas 2019",
    #},
    #{
    #    "id": 307,
    #    "url": "https://competicionescabb.gesdeportiva.es/competicion.aspx?competencia=307",
    #    "Anio": 2022,
    #    "torneo": "TORNEO FORMATIVAS 2022",
    #},
    #{
    #    "id": 682,
    #    "url": "https://competicionescabb.gesdeportiva.es/competicion.aspx?competencia=682",
    #    "Anio": 2023,
    #    "torneo": "FORMATIVAS 2023",
    #},
    #{
    #    "id": 1178,
    #    "url": "https://competicionescabb.gesdeportiva.es/competicion.aspx?competencia=1178",
    #    "Anio": 2024,
    #    "torneo": "FORMATIVAS 2024",
    #},
    {
        "id": 1623,
        "url": "https://competicionescabb.gesdeportiva.es/competicion.aspx?competencia=1623",
        "Anio": 2025,
        "torneo": "FORMATIVAS 2025",
    },
]


def main() -> None:
    """Legacy manual: lista fija de torneos. Flujo nuevo: ``python -m pipelines.run_scraper``."""
    base = "https://competicionescabb.gesdeportiva.es"
    all_partidos = []

    for torneo in torneos_a_scrapear:
        logger.info("Scrapeando: %s", torneo.get("torneo"))
        try:
            scraper = FebambaScraper(base_url=base)
            partidos = scraper.scrap_torneo(torneo)
            all_partidos.extend(partidos)
        except Exception as exc:
            logger.exception("Error al scrapear %s: %s", torneo.get("torneo"), exc)

    if all_partidos:
        df = pd.DataFrame(all_partidos)
        raw_dir = os.path.join("Data", "raw")
        os.makedirs(raw_dir, exist_ok=True)
        output_path = os.path.join(raw_dir, f"manual_{date.today()}.csv")
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        logger.info("Archivo guardado en: %s", output_path)
    else:
        logger.warning("No se encontraron partidos para los torneos seleccionados.")


if __name__ == "__main__":
    main()
