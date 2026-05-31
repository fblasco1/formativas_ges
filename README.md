# Analítica GES — Formativas (renivelación)

Base de código para varias **patas de análisis** desde [GES](https://competicionescabb.gesdeportiva.es/): formativas, Liga Nacional, Liga Argentina (ex-TNA), Liga Federal, Liga Femenina. Ver **`docs/VISION_PROYECTO.md`**.

**Esta rama (`Ranking_V2`):** ranking de **renivelación por tira** en competencias **formativas** FeBAMBA 2023–2026 + Streamlit.

**Rama `estadisticas`:** avance de estadísticas (entrenadores, jugadores, otras ligas) para proyectos de analítica — no mezclar con `Ranking_V2`.

## Requisitos

- Python 3.10+
- Ejecutar desde la raíz del repositorio

## Instalación

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Flujo principal

```powershell
# 1) Scrape temporada activa (2026) + consolidar + ranking tiras
python pipelines/actualizar_temporada_activa.py

# 2) Primera vez: congelar histórico 2023-2025
python -m analisis.renivelacion_tiras --congelar-historico

# 3) Dashboard principal
streamlit run streamlit_app.py
```

Actualización diaria programada: ver `docs/ACTUALIZACION_DIARIA.md`.

## Comandos útiles

| Acción | Comando |
|--------|---------|
| Scrape solo 2026 | `python pipelines/scrape_competencia.py formativas 2026` |
| Migrar CSV legacy → formativas | `python pipelines/migrar_data_formativas.py` |
| Listar competencias | `python pipelines/scrape_competencia.py --list` |
| Consolidar 23–26 | `python pipelines/consolidar_temporadas.py` |
| Renivelación completa | `python -m analisis.renivelacion_tiras` |
| Normalizar equipos | `python pipelines/normalizar_equipos.py --consolidar` |
| Mapeo de equipos | `streamlit run visualizaciones/mapeo_equipos_streamlit.py` |
| Detalle renivelación | `streamlit run visualizaciones/renivelacion_tiras_streamlit.py` |
| Tests | `pytest tests/ -q` |

## Datos en uso

Ver `docs/DATA_LAYOUT.md`. Resumen:

| Archivo | Uso |
|---------|-----|
| `Data/formativas/partidos_{2023..2026}.csv` | Partidos por temporada (preferido) |
| `Data/formativas/procesada/23-26.csv` | Consolidado (Streamlit) |
| `Data/partidos_*.csv` / `Data/procesada/23-26.csv` | Fallback legacy |
| `Data/procesada/Ranking_Tiras_Actualizado_2026.csv` | Ranking exportado |
| `Data/procesada/renivelacion/` | Caché incremental |

## Documentación

- `docs/VISION_PROYECTO.md` — ramas, competencias y roadmap
- `docs/ALCANCE_RAMA.md` — qué cubre solo `Ranking_V2`
- `docs/RENIVELACION_TIRAS.md` — algoritmo y categorías
- `docs/DEPLOY_STREAMLIT.md` — deploy en Streamlit Cloud
- `docs/DATA_LAYOUT.md` — rutas `Data/formativas/` y legacy
- `docs/ESTRUCTURA_COMPETENCIAS.md` — namespace multi-liga
- `docs/ACTUALIZACION_DIARIA.md` — scrape automático

## Estructura

```
competencias/                  # Registry GES por liga
analisis/renivelacion_tiras/   # Motor de renivelación
analisis/Ranking/              # BP, ORP, pesos (compartido)
mapeos/                        # equipos_map.json, regiones
pipelines/                     # scrape, consolidar, actualizar
visualizaciones/               # Streamlit
streamlit_app.py               # Entrada deploy
Data/                          # CSV de partidos y procesada
```

## Power Ranking por club (legacy)

El ranking antiguo por **club** (`python -m analisis.Ranking`) sigue en el código por compatibilidad, pero **no es el producto de esta rama**. El dashboard principal usa **renivelación por tira**.
