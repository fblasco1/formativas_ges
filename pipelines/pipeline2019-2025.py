import os
import sys
import pandas as pd
from datetime import date

# Agregar el directorio raíz del proyecto al sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.main import FebambaScraper

# Temporadas en foco: 2023–2026 (activar id GES de 2026 cuando esté publicado)
torneos_a_scrapear = [
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
    {
        "id": 2015,
        "url": "https://competicionescabb.gesdeportiva.es/competicion.aspx?competencia=2015",
        "Anio": 2026,
        "torneo": "FORMATIVAS 2026",
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
            if partidos:
                df = pd.DataFrame(partidos)
                os.makedirs("Data", exist_ok=True)
                out = os.path.join("Data", f"partidos_{torneo['Anio']}.csv")
                df.to_csv(out, index=False, encoding="utf-8-sig")
                print(f"  -> {out} ({len(df)} partidos)")
        except Exception as e:
            print(f"Error al scrapear {torneo['torneo']}: {e}")

    if all_partidos:
        print(f"Total partidos scrapeados: {len(all_partidos)}")
        print("Consolidar con: python pipelines/consolidar_temporadas.py")
    else:
        print("No se encontraron partidos para los torneos seleccionados.")


if __name__ == "__main__":
    main()
