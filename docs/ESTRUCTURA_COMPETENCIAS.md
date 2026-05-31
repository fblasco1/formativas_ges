# Estructura multi-competencia

El repo crece en **múltiples competencias** (Formativas + ligas) desde GES.
El namespace `competencias/` centraliza configuración y rutas de datos.

## Estado actual

- **Producción (`Ranking_V2`)**: Formativas (FeBAMBA) con ranking de renivelación.
- **Estadísticas** (entrenadores, jugadores, Liga Federal): rama `estadisticas`.

## Carpeta `competencias/`

```
competencias/
  registry.py       # Registro de competencias
  paths.py          # Rutas con fallback legacy formativas
  formativas/
    ges.py          # TORNEOS_FORMATIVAS (2023–2026)
  liga_nacional/    # placeholder
  liga_argentina/   # placeholder
  liga_federal/     # placeholder (avances en rama estadisticas)
  liga_femenina/    # placeholder
```

## Layout de datos

```
Data/
  formativas/
    partidos_{año}.csv
    procesada/
      23-26.csv
  liga_federal/          # futuro
    partidos_{año}.csv
```

**Fallback lectura formativas:** si no existe `Data/formativas/`, se usan
`Data/partidos_{año}.csv` y `Data/procesada/23-26.csv`.

Rankings y caché renivelación siguen en `Data/procesada/` hasta una migración explícita.

## Pipelines

| Comando | Descripción |
|---------|-------------|
| `python pipelines/scrape_competencia.py formativas 2026` | Scrape GES → `Data/formativas/` |
| `python pipelines/scrape_temporadas.py 2026` | Wrapper formativas |
| `python pipelines/normalizar_equipos.py --consolidar` | Mapeo + consolidado |
| `python pipelines/consolidar_temporadas.py` | Solo consolidar |
| `python pipelines/actualizar_temporada_activa.py` | Scrape + consolidar + renivelación |
| `python pipelines/migrar_data_formativas.py` | Copiar CSV legacy al namespace |

## Próximos pasos (otras ligas)

1. `competencias/<liga>/ges.py` con IDs/URLs GES.
2. Registrar en `competencias/registry.py`.
3. Scrape: `python pipelines/scrape_competencia.py liga_federal 2026`.
4. Pipelines de análisis en rama `estadisticas` (sin mezclar con renivelación formativas).
