# Estructura de datos (`Data/`)

Rama **Ranking_V2** — renivelación formativas GES.

## Namespace formativas (preferido)

| Archivo | Rol |
|---------|-----|
| `Data/formativas/partidos_2023.csv` … `partidos_2026.csv` | Scrape GES por temporada |
| `Data/formativas/procesada/23-26.csv` | Consolidado 2023–2026 |

Los pipelines escriben aquí. Lectura con **fallback** a rutas legacy si aún no migraste.

## Legacy (sigue funcionando como fallback)

| Archivo | Rol |
|---------|-----|
| `Data/partidos_2023.csv` … `partidos_2026.csv` | CSV anuales previos a la migración |
| `Data/procesada/23-26.csv` | Consolidado legacy |

Migración opcional (copia sin borrar originales):

```powershell
python pipelines/migrar_data_formativas.py
```

## Salidas de renivelación y job diario

| Archivo | Rol |
|---------|-----|
| `Data/procesada/Ranking_Tiras_Actualizado_2026.csv` | Ranking renivelación |
| `Data/procesada/Ranking_Tiras_Baseline_2026.csv` | Baseline GES (opcional) |
| `Data/procesada/renivelacion/*` | Caché histórico 2023–2025 |
| `Data/procesada/ultima_actualizacion.json` | Estado del job diario |

## Otras competencias (futuro / rama `estadisticas`)

```
Data/
  formativas/...
  liga_federal/...
  liga_argentina/...
```

Ver `docs/ESTRUCTURA_COMPETENCIAS.md` y `docs/VISION_PROYECTO.md`.

## Legacy formativas (no versionar en `Ranking_V2`)

- `Data/procesada/Ranking2023-*.csv` — Power Ranking viejo por club (regenerable)

## Regenerar ranking viejo por club (solo si hace falta)

```powershell
python -m analisis.Ranking
```

Crea de nuevo `Ranking2023-2026.csv` y `{año}.csv` en `procesada/`; no los uses para el dashboard principal.
