---
name: add-tournament-year
description: Incorpora un nuevo año/torneo FeBAMBA Formativas en gesdeportiva.json (sin editarlo a mano si se regenera), pipeline de scraping y mapeos de categorías. Usar al añadir 2026+ o competencias nuevas.
---

# Nuevo torneo / año

## Datos fuente

1. Entrada en `gesdeportiva.json`: filtrar por federaciones FeBAMBA y keyword formativas (ver rule `01-data-schema.mdc`).
2. **No asumir** clave `Anio` en el JSON: inferir con `inferir_anio(nombre_torneo)` desde el nombre.

## Pipeline

1. Añadir torneo a la lista que consuma `FebambaScraper` (`pipelines/run_scraper.py` objetivo o `pipelines/pipeline2019-2025.py` mientras dure).
2. Tras scrape: CSV en `Data/raw/` (convención del proyecto) o carpeta acordada.
3. Ejecutar normalización: `python -m pipelines.normalize` (objetivo) o script legacy según exista.

## Mapeos

- Categorías nuevas en fuente → entrada en `mapeos/categorias_map.json` apuntando al **nombre canónico** acordado (ver rule 01).
- Equipos nuevos → `equipos_map.json` solo si hay variantes de nombre.

## Calidad

- Loguear categorías sin match (WARNING), no fallar silenciosamente.
- Verificar año en rango esperado y conteos de partidos vs sitio web.
