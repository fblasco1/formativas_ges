---
name: refactor-etl-structure
description: Guía para consolidar el ETL FeBAMBA (scraper en scraper/scraper.py, entrypoint pipelines/run_scraper.py, normalización pipelines/normalize.py, inferir_anio). Usar en refactors ETL, code review de parsers o al mover FebambaScraper desde scraper/main.py.
---

# Refactor estructura ETL

## Estado objetivo (fuente de verdad)

```
gesdeportiva.json → filtrar FeBAMBA formativas
  → python -m pipelines.run_scraper
    → scraper/scraper.py (FebambaScraper)
    → Data/raw/*.csv
  → python -m pipelines.normalize
    → Data/procesada/matches_clean.parquet + matches_clean.csv
```

## Reglas críticas

1. **`inferir_anio(torneo_info["torneo"])`** — nunca `torneo_info["Anio"]` desde JSON solo.
2. **`parsers/rondas.py`**: `inferir_ronda` retorna **siempre `dict`** con claves acordadas (p. ej. ronda, llave, nivel).
3. **`parsers/*`**: funciones puras; sin imports desde `scraper/`.
4. **`corregir_nombres_postscrap.py`**: solo wrapper/legacy hacia `normalize`; salida **sin** nombres con espacios tipo `19-24 procesado.csv`.
5. Logging con `utils/logger.py`, no `print()` en código nuevo.

## Migración desde legacy

- Si `FebambaScraper` sigue en `scraper/main.py`: mantener re-export o import estable hasta actualizar todos los call sites (`pipeline2019-2025.py`, etc.).
