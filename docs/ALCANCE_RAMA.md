# Alcance de la rama `Ranking_V2`

Esta rama es **solo** la pata **Formativas → ranking de renivelación por tira**.

La visión global del repo (varias competencias GES) está en `docs/VISION_PROYECTO.md`.  
El desarrollo de **estadísticas** (entrenadores, jugadores, otras ligas) va en la rama **`estadisticas`**.

## Incluido en `Ranking_V2`

- Scrape GES torneos **Formativas** 2023–2026
- Mapeo y normalización de **equipos / tiras**
- **Renivelación** por tira (Infantiles, Cadetes, Juveniles, Liga Próximo)
- Regiones SUR / OESTE / NORTE / CENTRO (interconferencia ≠ región)
- Dashboard Streamlit (`streamlit_app.py`)
- Actualización diaria (`pipelines/actualizar_temporada_activa.py`)
- Apoyo: mapeo equipos, partidos por equipo, LIBRE, comparativa institucional

## No en esta rama (sí en `estadisticas` u otras)

- Estadísticas de **entrenadores** y **jugadores**
- **Liga Federal**, **Liga Argentina** (ex-TNA), **Liga Nacional**, **Liga Femenina**
- Fixtures `fixture_*.csv`, box score, argentina.basketball

En `Ranking_V2`, `.gitignore` evita commitear por error artefactos de otras patas; **no significa** que esas features no se desarrollen — se desarrollan en su rama.
