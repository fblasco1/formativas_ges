import os
import sys
import pandas as pd
from datetime import date

# Agregar el directorio raíz del proyecto al sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.main import FebambaScraper

# Lista de torneos a scrapear
torneos_a_scrapear = [
    {
        "id": 16,
        "url": "https://competicionescabb.gesdeportiva.es/competicion.aspx?competencia=16",
        "Anio": 2019,
        "torneo": "Torneo Formativas 2019",
    },
    {
        "id": 307,
        "url": "https://competicionescabb.gesdeportiva.es/competicion.aspx?competencia=307",
        "Anio": 2022,
        "torneo": "TORNEO FORMATIVAS 2022",
    },
    {
        "id": 682,
        "url": "https://competicionescabb.gesdeportiva.es/competicion.aspx?competencia=682",
        "Anio": 2023,
        "torneo": "FORMATIVAS 2023",
    },
    {
        "id": 1178,
        "url": "https://competicionescabb.gesdeportiva.es/competicion.aspx?competencia=1178",
        "Anio": 2024,
        "torneo": "FORMATIVAS 2024",
    },
    {
        "id": 1623,
        "url": "https://competicionescabb.gesdeportiva.es/competicion.aspx?competencia=1623",
        "Anio": 2025,
        "torneo": "FORMATIVAS 2025",
    },
]


def main():
    scraper = FebambaScraper(base_url="https://competicionescabb.gesdeportiva.es/")
    all_partidos = []

    for torneo in torneos_a_scrapear:
        print(f"Scrapeando: {torneo['torneo']} ({torneo['Anio']})")
        try:
            partidos = scraper.scrap_torneo(torneo)
            all_partidos.extend(partidos)
        except Exception as e:
            print(f"Error al scrapear {torneo['torneo']}: {e}")

    if all_partidos:
        df = pd.DataFrame(all_partidos)
        os.makedirs("Data", exist_ok=True)
        output_path = os.path.join("Data", f"{date.today()}.csv")
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"Archivo guardado en: {output_path}")
    else:
        print("No se encontraron partidos para los torneos seleccionados.")


if __name__ == "__main__":
    main()
